"""Jev judge over any of its four doors. Same body everywhere: {"model", "state", "questions"}.

- typesafe:   POST https://api.typesafe.ai/v1/systemone          (docs.typesafe.ai/api)
- openrouter: POST https://openrouter.ai/api/alpha/decisions       (as used by jev-chat-windows)
- vercel:     POST https://ai-gateway.vercel.sh/typesafe/v1/systemone  (jarvis README; unverified here)
- opencode:   POST https://opencode.ai/zen/v1/systemone             (jarvis README; unverified here)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .. import http
from ..models import Judgment, Message, Usage
from ..questions import RANK_KEYS, build_state, judge_questions, rank_question
from .base import ProviderError, judgment_from_answers

PRICE_PER_MTOK_IN = 0.042  # USD, input only; output is free (docs.typesafe.ai/models, Sep 2026)


@dataclass(frozen=True)
class Door:
    url: str
    key_env: str
    default_model: str


DOORS = {
    "typesafe": Door("https://api.typesafe.ai/v1/systemone", "TYPESAFE_API_KEY", "jev-latest"),
    "openrouter": Door("https://openrouter.ai/api/alpha/decisions", "OPENROUTER_API_KEY", "typesafe/jev-1.13"),
    "vercel": Door("https://ai-gateway.vercel.sh/typesafe/v1/systemone", "AI_GATEWAY_API_KEY", "typesafe-ai/jev"),
    "opencode": Door("https://opencode.ai/zen/v1/systemone", "OPENCODE_API_KEY", "jev-1.13"),
}


def key_for(door: str) -> str:
    return os.environ.get(DOORS[door].key_env, "").strip()


class JevJudge:
    def __init__(self, door: str = "typesafe", model: str = "", timeout: float = 30.0):
        if door not in DOORS:
            raise ProviderError(f"unknown Jev door {door!r}; use one of {sorted(DOORS)}")
        self.door = DOORS[door]
        self.name = f"jev:{door}"
        self.model = model or self.door.default_model
        self.timeout = timeout
        if not key_for(door):
            raise ProviderError(f"{self.door.key_env} is not set")
        self._key = key_for(door)

    def _ask(self, state: dict, questions: dict, role: str) -> tuple[dict, Usage]:
        try:
            body, ms = http.request_json(
                "POST", self.door.url, timeout=self.timeout,
                headers={"Authorization": f"Bearer {self._key}"},
                body={"model": self.model, "state": state, "questions": questions},
            )
        except http.HttpError as exc:
            raise ProviderError(str(exc)) from None
        tokens = int((body.get("usage") or {}).get("input_tokens") or 0)
        usage = Usage(role=role, provider=self.name, model=body.get("model") or self.model, ms=ms,
                      input_tokens=tokens, cost_usd=round(tokens / 1e6 * PRICE_PER_MTOK_IN, 8))
        if "answers" not in body:
            raise ProviderError("Jev response has no answers")
        return body["answers"], usage

    def judge(self, msg: Message) -> tuple[Judgment, Usage]:
        answers, usage = self._ask(build_state(msg), judge_questions(), "judge")
        try:
            return judgment_from_answers(answers), usage
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"unexpected Jev answer shape: {exc}") from None

    def rank(self, msg: Message, candidates: list[str]) -> tuple[list[float], Usage]:
        answers, usage = self._ask(build_state(msg), rank_question(candidates), "rank")
        probs = (answers.get("best_reply") or {}).get("probabilities") or {}
        return [float(probs.get(k, 0.0)) for k in RANK_KEYS[: len(candidates)]], usage
