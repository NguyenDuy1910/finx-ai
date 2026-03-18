"""Embedding provider abstraction with an OpenAI implementation.

Keeping a thin ABC here makes it straightforward to swap providers
(e.g. local sentence-transformers, Cohere) without touching the pipeline.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

log = logging.getLogger("finx-data.ingest.embedder")

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0   # seconds; doubles each attempt

# OpenAI hard limit: 300 000 tokens per embeddings request.
_MAX_TOKENS_PER_REQUEST = 250_000

# Per-text token limit for OpenAI embedding models (all current models share this).
_MAX_TOKENS_PER_TEXT = 8191

# Chars-per-token estimate for batch-splitting.
# Vietnamese is ~2 chars/token; English ~4. Use 2 to be safe for mixed content.
_CHARS_PER_TOKEN = 2

# Try to load tiktoken for accurate token counting.
# Falls back to the char-based estimate if not installed.
try:
    import tiktoken as _tiktoken
    _TOKENIZER = _tiktoken.get_encoding("cl100k_base")  # works for all text-embedding-3-* models
except Exception:
    _TOKENIZER = None


def _token_count(text: str) -> int:
    """Return token count using tiktoken when available, else a conservative estimate."""
    if _TOKENIZER is not None:
        return len(_TOKENIZER.encode(text, disallowed_special=()))
    return max(1, len(text) // _CHARS_PER_TOKEN)


def truncate_to_token_limit(text: str, max_tokens: int = _MAX_TOKENS_PER_TEXT) -> str:
    """Truncate *text* so it fits within *max_tokens*.

    Uses tiktoken for exact truncation when available; otherwise binary-searches
    the character boundary using the conservative estimate.
    """
    if _TOKENIZER is not None:
        tokens = _TOKENIZER.encode(text, disallowed_special=())
        if len(tokens) <= max_tokens:
            return text
        return _TOKENIZER.decode(tokens[:max_tokens])

    # Char-based fallback: start at the conservative estimate and walk back
    # in 256-char steps until the estimate fits.
    limit_chars = max_tokens * _CHARS_PER_TOKEN
    candidate = text[:limit_chars]
    while _token_count(candidate) > max_tokens and len(candidate) > 256:
        candidate = candidate[: int(len(candidate) * 0.9)]
    return candidate


class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts.  Returns one vector per input text."""
        ...

    @property
    @abstractmethod
    def dim(self) -> int:
        """Vector dimension produced by this provider."""
        ...


class OpenAIEmbedder(EmbeddingProvider):
    """Dense embeddings via the OpenAI Embeddings API.

    Retries up to 3 times on transient errors (rate limit, server errors)
    with exponential back-off.
    """

    def __init__(self, model: str = "text-embedding-3-small", expected_dim: int = 1536) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("openai package is required for OpenAIEmbedder") from exc

        self._client = OpenAI()
        self._model = model
        self._expected_dim = expected_dim

    @property
    def dim(self) -> int:
        return self._expected_dim

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed texts, automatically splitting into token-budget sub-batches.

        A single OpenAI embeddings request is capped at 300 000 tokens.
        This method splits the input into sub-batches that stay under
        _MAX_TOKENS_PER_REQUEST and concatenates the results, preserving order.
        """
        if not texts:
            return []

        # Split into sub-batches that fit within the token budget
        sub_batches: list[list[str]] = []
        current: list[str] = []
        current_tokens = 0

        for text in texts:
            estimated = max(1, len(text) // _CHARS_PER_TOKEN)
            if current and current_tokens + estimated > _MAX_TOKENS_PER_REQUEST:
                sub_batches.append(current)
                current = []
                current_tokens = 0
            current.append(text)
            current_tokens += estimated

        if current:
            sub_batches.append(current)

        if len(sub_batches) > 1:
            log.debug(
                "Splitting %d texts into %d sub-batches to stay under token limit",
                len(texts),
                len(sub_batches),
            )

        all_vectors: list[list[float]] = []
        for sub in sub_batches:
            all_vectors.extend(self._embed_single_request(sub))

        return all_vectors

    def _embed_single_request(self, texts: list[str]) -> list[list[float]]:
        """Send one API request with retry.

        Texts are pre-truncated to _MAX_TOKENS_PER_TEXT before the call.
        On a context_length_exceeded error (can happen when tiktoken is not
        installed and the estimate is slightly off), the texts are truncated
        more aggressively and retried once before giving up.
        """
        # Always truncate each text to the model's per-input limit before sending.
        safe_texts = [truncate_to_token_limit(t) for t in texts]

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.embeddings.create(
                    input=safe_texts,
                    model=self._model,
                )
                vectors = [item.embedding for item in response.data]

                # Validate dimension on the first real call
                if vectors and len(vectors[0]) != self._expected_dim:
                    raise ValueError(
                        f"Embedding dimension mismatch: expected {self._expected_dim}, "
                        f"got {len(vectors[0])} from model '{self._model}'. "
                        "Update QdrantIngestConfig.embedding_dim to match."
                    )

                log.debug("Embedded %d texts with %s", len(safe_texts), self._model)
                return vectors

            except Exception as exc:
                # Surface dimension mismatches immediately — never transient
                if isinstance(exc, ValueError):
                    raise

                msg = str(exc)
                if "maximum context length" in msg or "context_length_exceeded" in msg:
                    # Truncation was not aggressive enough (tiktoken unavailable).
                    # Halve the limit and retry once.
                    if attempt == 1:
                        tighter = _MAX_TOKENS_PER_TEXT // 2
                        log.warning(
                            "context_length_exceeded despite truncation. "
                            "Re-truncating to %d tokens and retrying.",
                            tighter,
                        )
                        safe_texts = [truncate_to_token_limit(t, tighter) for t in texts]
                        continue
                    raise

                if attempt == _MAX_RETRIES:
                    raise

                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                log.warning(
                    "Embedding attempt %d/%d failed (%s). Retrying in %.1fs…",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)

        return []  # unreachable — kept for type checker
