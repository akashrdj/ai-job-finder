import logging
import json
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Multi-provider LLM client with dual Gemini model support.

    Model routing:
    - GEMINI_MODEL (gemini-2.0-flash): Fast, cheap — used for company research,
      gap analysis, and other lightweight tasks.
    - GEMINI_MODEL_HEAVY (gemini-2.5-flash): Higher quality — used for
      cover letter generation, resume tailoring, and other quality-critical tasks.
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self.gemini_key = settings.GEMINI_API_KEY
        self.gemini_model_light = settings.GEMINI_MODEL           # Fast: search, research
        self.gemini_model_heavy = settings.GEMINI_MODEL_HEAVY     # Quality: drafting
        self.anthropic_key = settings.ANTHROPIC_API_KEY
        self.openai_key = settings.OPENAI_API_KEY
        self.openrouter_key = settings.OPENROUTER_API_KEY
        self.openrouter_model = settings.OPENROUTER_MODEL or "deepseek/deepseek-chat"

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        use_heavy_model: bool = False,
    ) -> str:
        """
        Generate text using configured provider with automatic fallback.

        Args:
            use_heavy_model: If True, uses GEMINI_MODEL_HEAVY for
                            higher quality output. Default False uses the light model.
        """
        if self.provider == "gemini" and self.gemini_key:
            try:
                return await self._call_gemini(system_prompt, user_prompt, use_heavy_model)
            except Exception as e:
                logger.warning(f"Gemini API call failed ({e}). Attempting OpenRouter fallback...")
                if self.openrouter_key:
                    try:
                        return await self._call_openrouter(system_prompt, user_prompt)
                    except Exception as oe:
                        logger.warning(f"OpenRouter fallback failed: {oe}. Falling back to deterministic engine.")
                else:
                    logger.warning("No OPENROUTER_API_KEY configured for fallback. Falling back to deterministic engine.")

        elif self.provider == "openrouter" and self.openrouter_key:
            try:
                return await self._call_openrouter(system_prompt, user_prompt)
            except Exception as e:
                logger.warning(f"OpenRouter API call failed: {e}. Falling back to deterministic engine.")

        elif self.provider == "anthropic" and self.anthropic_key:
            try:
                return await self._call_anthropic(system_prompt, user_prompt)
            except Exception as e:
                logger.warning(f"Anthropic API call failed: {e}. Falling back to deterministic engine.")

        elif self.provider == "openai" and self.openai_key:
            try:
                return await self._call_openai(system_prompt, user_prompt)
            except Exception as e:
                logger.warning(f"OpenAI API call failed: {e}. Falling back to deterministic engine.")

        # Default / Offline / Mock fallback
        return self._generate_fallback(system_prompt, user_prompt)

    async def _call_openrouter(self, system_prompt: str, user_prompt: str) -> str:
        """Execute chat completion call via OpenRouter API."""
        import httpx
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "HTTP-Referer": "https://github.com/akashrdj/ai-job-finder",
            "X-Title": "AI Job Finder",
            "Content-Type": "application/json"
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.openrouter_model,
            "messages": messages,
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _call_gemini(
        self, system_prompt: str, user_prompt: str, use_heavy: bool = False
    ) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.gemini_key)
        model_name = self.gemini_model_heavy if use_heavy else self.gemini_model_light
        logger.info(f"Calling Gemini model: {model_name} (heavy={use_heavy})")

        config = types.GenerateContentConfig(
            system_instruction=system_prompt
        ) if system_prompt else None

        response = await client.aio.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=config,
        )
        return response.text or ""

    async def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        import httpx
        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 1500,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}]
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        import httpx
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _generate_fallback(self, system_prompt: str, user_prompt: str) -> str:
        """Deterministic offline generator when no API keys are provided."""
        return "GENERATED_VIA_DETERMINISTIC_FALLBACK"
