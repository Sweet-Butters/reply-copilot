"""The adapter contract. A new channel is one file implementing these two methods.

fetch(limit) -> new incoming messages addressed to the owner (read-only calls only)
stage(msg, reply, store) -> put the chosen reply where the owner will review it; never send it.
    Returns a short human-readable note ("Gmail draft r-123", "queue #4").
"""
from __future__ import annotations

from typing import Protocol

from ..models import Message
from ..store import Store


class Adapter(Protocol):
    name: str

    def fetch(self, limit: int) -> list[Message]: ...

    def stage(self, msg: Message, reply: str, store: Store) -> str: ...


class AdapterError(Exception):
    pass


def queue_stage(msg: Message, reply: str, store: Store, link: str = "") -> str:
    """Default staging for comment channels: the local approval queue."""
    qid = store.enqueue(msg.channel, msg.id, reply, sender=msg.sender, original=msg.text, link=link)
    return f"queue #{qid}"
