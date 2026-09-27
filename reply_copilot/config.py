"""Settings from environment variables only. Keys are never read from files."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except ValueError:
        return default


@dataclass
class Thresholds:
    skip_no_reply_below: float = 0.35  # needs_reply below this -> no draft
    spam_above: float = 0.7
    abusive_above: float = 0.7
    hand_write_tension: float = 7.0    # tension at or above this -> warn "write this one yourself"


@dataclass
class Settings:
    judge: str = "typesafe"
    drafter: str = "anthropic"
    jev_model: str = ""
    draft_model: str = ""
    owner_name: str = ""
    owner_email: str = ""
    owner_style: str = ""
    data_dir: Path = ROOT / "data"
    token_dir: Path = Path.home() / ".reply-copilot" / "tokens"
    thresholds: Thresholds = field(default_factory=Thresholds)
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            judge=_env("REPLY_JUDGE", "typesafe").lower(),
            drafter=_env("REPLY_DRAFTER", "anthropic").lower(),
            jev_model=_env("JEV_MODEL"),
            draft_model=_env("DRAFT_MODEL"),
            owner_name=_env("OWNER_NAME"),
            owner_email=_env("OWNER_EMAIL").lower(),
            owner_style=_env("OWNER_STYLE", "정중하지만 짧게. 존댓말."),
            data_dir=Path(_env("REPLY_DATA_DIR") or ROOT / "data"),
            token_dir=Path(_env("REPLY_TOKEN_DIR") or Path.home() / ".reply-copilot" / "tokens"),
            thresholds=Thresholds(
                skip_no_reply_below=_float("SKIP_NO_REPLY_BELOW", 0.35),
                spam_above=_float("SPAM_ABOVE", 0.7),
                abusive_above=_float("ABUSIVE_ABOVE", 0.7),
                hand_write_tension=_float("HAND_WRITE_TENSION", 7.0),
            ),
            timeout=_float("REPLY_TIMEOUT", 30.0),
        )
