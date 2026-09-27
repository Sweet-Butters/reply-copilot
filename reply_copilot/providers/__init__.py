"""Build the judge and drafter named in Settings. Missing keys fall back to mocks unless strict."""
from __future__ import annotations

from ..config import Settings
from .base import Drafter, Judge, ProviderError
from .mock import MockDrafter, MockJudge

JUDGES = ("typesafe", "openrouter", "vercel", "opencode", "mock")
DRAFTERS = ("anthropic", "deepseek", "openrouter", "openai", "mock")


def build_judge(s: Settings, *, force_mock: bool = False, strict: bool = False,
                notes: list[str] | None = None) -> Judge:
    if force_mock or s.judge == "mock":
        return MockJudge()
    try:
        from .typesafe import JevJudge
        return JevJudge(s.judge, s.jev_model, s.timeout)
    except ProviderError as exc:
        if strict:
            raise
        if notes is not None:
            notes.append(f"judge {s.judge}: {exc}; using mock judge")
        return MockJudge()


def build_drafter(s: Settings, *, force_mock: bool = False, strict: bool = False,
                  notes: list[str] | None = None) -> Drafter:
    if force_mock or s.drafter == "mock":
        return MockDrafter()
    try:
        if s.drafter == "anthropic":
            from .anthropic import AnthropicDrafter
            return AnthropicDrafter(s.draft_model, max(s.timeout, 60))
        from .openai_compat import OpenAICompatDrafter
        return OpenAICompatDrafter(s.drafter, s.draft_model, max(s.timeout, 60))
    except ProviderError as exc:
        if strict:
            raise
        if notes is not None:
            notes.append(f"drafter {s.drafter}: {exc}; using mock drafter")
        return MockDrafter()


__all__ = ["build_judge", "build_drafter", "Judge", "Drafter", "ProviderError", "JUDGES", "DRAFTERS"]
