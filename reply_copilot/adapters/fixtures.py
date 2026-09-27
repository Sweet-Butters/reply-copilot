"""Fictional messages from eval/fixtures/*.json, for dry runs and the eval harness."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import ROOT
from ..models import Message
from ..store import Store
from .base import queue_stage

FIXTURE_DIR = ROOT / "eval" / "fixtures"


def load_fixtures(directory: Path = FIXTURE_DIR) -> list[dict]:
    items: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items.extend(data if isinstance(data, list) else [data])
    return items


def to_message(item: dict) -> Message:
    return Message(
        id=item["id"], channel=item.get("channel", "fixtures"), kind=item["kind"],
        sender=item["sender"], text=item["text"], subject=item.get("subject", ""),
        context=item.get("context", ""), thread=[tuple(t) for t in item.get("thread", [])],
        received_at=item.get("received_at", ""), meta={"fixture": True},
    )


class FixturesAdapter:
    name = "fixtures"

    def __init__(self, directory: Path = FIXTURE_DIR):
        self.directory = directory

    def fetch(self, limit: int) -> list[Message]:
        return [to_message(i) for i in load_fixtures(self.directory)[:limit]]

    def stage(self, msg: Message, reply: str, store: Store) -> str:
        return queue_stage(msg, reply, store)
