from __future__ import annotations

from openai import AsyncOpenAI, OpenAI


class OpenAIAdapter:
    """Adapter for any OpenAI-compatible API (OpenAI, vLLM, 9router, etc.)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str | None = None,
    ) -> None:
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._sync = OpenAI(**kwargs)
        self._async = AsyncOpenAI(**kwargs)
        self._model = model

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 8000,
    ) -> str:
        resp = self._sync.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    async def acomplete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 8000,
    ) -> str:
        resp = await self._async.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
