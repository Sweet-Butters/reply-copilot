"""Drafting through any OpenAI-compatible /chat/completions endpoint (DeepSeek, OpenRouter, OpenAI)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from .. import http
from ..models import Message, Usage
from .base import ProviderError, build_prompt, parse_candidates


@dataclass(frozen=True)
class Endpoint:
    base: str
    key_env: str
    default_model: str  # "" = the user must set DRAFT_MODEL


ENDPOINTS = {
    # Model names are defaults only; check the provider's model list and override with DRAFT_MODEL.
    "deepseek": Endpoint("https://api.deepseek.com", "DEEPSEEK_API_KEY", "deepseek-chat"),
    "openrouter": Endpoint("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "deepseek/deepseek-chat-v3.1"),
    "openai": Endpoint("https://api.openai.com/v1", "OPENAI_API_KEY", ""),
}


def _price(name: str) -> float | None:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return None


class OpenAICompatDrafter:
    def __init__(self, provider: str, model: str = "", timeout: float = 60.0):
        if provider not in ENDPOINTS:
            raise ProviderError(f"unknown drafter {provider!r}")
        self.ep = ENDPOINTS[provider]
        self.name = provider
        self.model = model or self.ep.default_model
        if not self.model:
            raise ProviderError(f"set DRAFT_MODEL for the {provider} drafter")
        self._key = os.environ.get(self.ep.key_env, "").strip()
        if not self._key:
            raise ProviderError(f"{self.ep.key_env} is not set")
        self.timeout = timeout

    def draft(self, msg: Message, guidance: str | None, owner: dict) -> tuple[list[str], Usage]:
        system, user = build_prompt(msg, guidance, owner)
        try:
            body, ms = http.request_json(
                "POST", f"{self.ep.base}/chat/completions", timeout=self.timeout,
                headers={"Authorization": f"Bearer {self._key}"},
                body={"model": self.model, "max_tokens": 900, "temperature": 0.8,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]},
            )
        except http.HttpError as exc:
            raise ProviderError(str(exc)) from None
        try:
            content = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderError("draft response has no choices") from None
        u = body.get("usage") or {}
        tin, tout = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
        pin, pout = _price("DRAFT_PRICE_IN"), _price("DRAFT_PRICE_OUT")
        cost = None if pin is None or pout is None else round((tin * pin + tout * pout) / 1e6, 8)
        return parse_candidates(content), Usage("draft", self.name, body.get("model") or self.model, ms,
                                                tin, tout, cost)
