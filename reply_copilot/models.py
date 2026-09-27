"""Plain data types shared by adapters, providers and the pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Message:
    """One incoming item on any channel, already reduced to what the pipeline needs.

    channel: "gmail" | "youtube" | "instagram" | "fixtures" | ...
    kind:    "email" | "comment"
    thread:  earlier turns as (who, text), who in {"them", "me"}; oldest first.
    meta:    channel-specific ids needed to stage a reply (thread id, Message-ID, comment id ...).
             Never sent to a model provider.
    """
    id: str
    channel: str
    kind: str
    sender: str
    text: str
    subject: str = ""
    context: str = ""  # e.g. the video title or post caption the comment sits under
    thread: list[tuple[str, str]] = field(default_factory=list)
    received_at: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Judgment:
    needs_reply: float
    reply_now: float
    spam: float
    abusive: float
    intent: str
    sender_wants: str
    best_action: str
    tension: float  # 0..9
    confidence: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw", None)
        return d


@dataclass
class Candidate:
    text: str
    score: float | None = None  # ranker probability, None when not ranked


@dataclass
class Usage:
    """One provider call: who, how long, how many tokens, what it cost (None = unknown price)."""
    role: str      # "judge" | "rank" | "draft"
    provider: str
    model: str
    ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0
    ok: bool = True


@dataclass
class Outcome:
    message_id: str
    pipeline: str             # "judge_first" | "draft_direct"
    decision: str             # "draft" | "skip_spam" | "skip_abusive" | "skip_no_reply" | "error"
    judgment: Judgment | None = None
    candidates: list[Candidate] = field(default_factory=list)
    best: str | None = None
    warnings: list[str] = field(default_factory=list)
    usage: list[Usage] = field(default_factory=list)

    @property
    def total_ms(self) -> int:
        return sum(u.ms for u in self.usage)

    @property
    def total_cost(self) -> float | None:
        costs = [u.cost_usd for u in self.usage]
        return None if any(c is None for c in costs) else round(sum(costs), 8)

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "pipeline": self.pipeline,
            "decision": self.decision,
            "judgment": self.judgment.to_dict() if self.judgment else None,
            "candidates": [asdict(c) for c in self.candidates],
            "best": self.best,
            "warnings": self.warnings,
            "usage": [asdict(u) for u in self.usage],
            "total_ms": self.total_ms,
            "total_cost_usd": self.total_cost,
        }
