"""Drafting with Claude through the official Anthropic SDK (optional dependency: pip install anthropic)."""
from __future__ import annotations

import os
import time

from ..models import Message, Usage
from ..privacy import redact_secrets
from .base import ProviderError, build_prompt, parse_candidates

DEFAULT_MODEL = "claude-opus-5"
# USD per million tokens (input, output), Anthropic first-party list prices as of 2026-09.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class AnthropicDrafter:
    name = "anthropic"

    def __init__(self, model: str = "", timeout: float = 60.0):
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ImportError:
            raise ProviderError("pip install anthropic to use the anthropic drafter") from None
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(timeout=timeout, max_retries=2)
        self.model = model or DEFAULT_MODEL

    def draft(self, msg: Message, guidance: str | None, owner: dict) -> tuple[list[str], Usage]:
        system, user = build_prompt(msg, guidance, owner)
        t0 = time.perf_counter()
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=2048, system=system,
                messages=[{"role": "user", "content": user}],
                # Short, routine writing: low effort keeps latency and cost down.
                extra_body={"output_config": {"effort": "low"}},
            )
        except self._anthropic.APIStatusError as exc:
            raise ProviderError(redact_secrets(f"Claude HTTP {exc.status_code}: {exc.message}")) from None
        except self._anthropic.APIConnectionError as exc:
            raise ProviderError(redact_secrets(f"Claude connection error: {exc}")) from None
        ms = round((time.perf_counter() - t0) * 1000)
        if resp.stop_reason == "refusal":
            raise ProviderError("Claude declined to draft this message")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        tin, tout = resp.usage.input_tokens, resp.usage.output_tokens
        price = PRICES.get(self.model)
        cost = round((tin * price[0] + tout * price[1]) / 1e6, 8) if price else None
        return parse_candidates(text), Usage("draft", self.name, self.model, ms, tin, tout, cost)
