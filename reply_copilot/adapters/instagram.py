"""Instagram: read comments on the owner's own recent posts via the Instagram API with Instagram Login.

Requires a Professional (Business or Creator) account and a long-lived user token in IG_ACCESS_TOKEN
with instagram_business_basic (+ instagram_business_manage_comments for comment reads/replies).
Replies go to the approval queue; the write endpoint for comment replies is deliberately not implemented.
"""
from __future__ import annotations

import os
import urllib.parse

from .. import http
from ..models import Message
from ..store import Store
from .base import AdapterError, queue_stage

BASE = "https://graph.instagram.com"


def parse_comments(comments: list[dict], my_username: str, media: dict) -> list[Message]:
    out = []
    for c in comments:
        if c.get("username", "").lower() == my_username.lower():
            continue
        replies = ((c.get("replies") or {}).get("data")) or []
        if any(r.get("username", "").lower() == my_username.lower() for r in replies):
            continue
        out.append(Message(
            id=c["id"], channel="instagram", kind="comment", sender=c.get("username", ""),
            text=c.get("text", ""), context=(media.get("caption") or "")[:300],
            received_at=c.get("timestamp", ""),
            meta={"media_id": media["id"], "permalink": media.get("permalink", "")},
        ))
    return out


class InstagramAdapter:
    name = "instagram"

    def __init__(self, token: str = "", version: str = "", media_limit: int = 5):
        self.token = token or os.environ.get("IG_ACCESS_TOKEN", "").strip()
        if not self.token:
            raise AdapterError("IG_ACCESS_TOKEN is not set (see docs/channels.md)")
        self.version = version or os.environ.get("IG_API_VERSION", "v25.0")
        self.media_limit = media_limit

    def _get(self, path: str, **params) -> dict:
        params["access_token"] = self.token
        url = f"{BASE}/{self.version}/{path}?{urllib.parse.urlencode(params)}"
        try:
            body, _ = http.request_json("GET", url, timeout=30)
        except http.HttpError as exc:  # the URL (with the token) is never in the message
            raise AdapterError(f"Instagram {path}: {exc}") from None
        return body

    def fetch(self, limit: int) -> list[Message]:
        me = self._get("me", fields="user_id,username")
        username = me.get("username", "")
        media = self._get("me/media", fields="id,caption,permalink,timestamp", limit=self.media_limit)
        out: list[Message] = []
        for m in media.get("data", []):
            comments = self._get(f"{m['id']}/comments", fields="id,text,username,timestamp,replies{username}",
                                 limit=50)
            out.extend(parse_comments(comments.get("data", []), username, m))
            if len(out) >= limit:
                break
        return out[:limit]

    def stage(self, msg: Message, reply: str, store: Store) -> str:
        return queue_stage(msg, reply, store, msg.meta.get("permalink", ""))
