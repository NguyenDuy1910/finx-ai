from __future__ import annotations

import asyncio

import google.generativeai as genai


class GoogleAdapter:
    """Adapter for Google Gemini models."""

    def __init__(self, api_key: str, model: str) -> None:
        genai.configure(api_key=api_key)
        self._model_name = model

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 8000,
    ) -> str:
        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system,
        )
        resp = model.generate_content(
            user,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return resp.text or ""

    async def acomplete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 8000,
    ) -> str:
        return await asyncio.to_thread(
            self.complete, system, user, temperature=temperature, max_tokens=max_tokens
        )
