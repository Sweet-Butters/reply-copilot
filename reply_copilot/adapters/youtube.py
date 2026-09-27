"""YouTube: read new comment threads on the owner's own channel; replies go to the approval queue.

Read-only scope. Quota: commentThreads.list and videos.list cost 1 unit each (10,000/day default).
Posting a reply (comments.insert, 50 units, youtube.force-ssl) is deliberately not implemented.
"""
from __future__ import annotations

from ..models import Message
from ..store import Store
from .base import AdapterError, queue_stage

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def parse_threads(items: list[dict], my_channel_id: str) -> list[Message]:
    """commentThreads.list items -> Messages, skipping my own comments and threads I already answered."""
    out = []
    for it in items:
        top = it["snippet"]["topLevelComment"]
        s = top["snippet"]
        author = (s.get("authorChannelId") or {}).get("value", "")
        if author == my_channel_id:
            continue
        replies = (it.get("replies") or {}).get("comments", [])
        if any((r["snippet"].get("authorChannelId") or {}).get("value") == my_channel_id for r in replies):
            continue
        out.append(Message(
            id=top["id"], channel="youtube", kind="comment",
            sender=s.get("authorDisplayName", ""), text=s.get("textOriginal") or s.get("textDisplay", ""),
            received_at=s.get("publishedAt", ""),
            meta={"video_id": s.get("videoId") or it["snippet"].get("videoId", ""), "thread_id": it["id"]},
        ))
    return out


class YouTubeAdapter:
    name = "youtube"

    def __init__(self, token_dir, channel_id: str = "", service=None, interactive: bool = False):
        if service is None:
            from .google_auth import load_credentials
            creds = load_credentials("youtube", SCOPES, token_dir, interactive=interactive)
            try:
                from googleapiclient.discovery import build
            except ImportError:
                raise AdapterError("pip install google-api-python-client") from None
            service = build("youtube", "v3", credentials=creds, cache_discovery=False)
        self.svc = service
        if not channel_id:
            mine = self.svc.channels().list(part="id", mine=True).execute().get("items", [])
            if not mine:
                raise AdapterError("this Google account has no YouTube channel")
            channel_id = mine[0]["id"]
        self.channel_id = channel_id

    def fetch(self, limit: int) -> list[Message]:
        resp = self.svc.commentThreads().list(
            part="snippet,replies", allThreadsRelatedToChannelId=self.channel_id,
            order="time", textFormat="plainText", maxResults=min(max(limit, 1), 100),
        ).execute()
        msgs = parse_threads(resp.get("items", []), self.channel_id)[:limit]
        ids = sorted({m.meta["video_id"] for m in msgs if m.meta.get("video_id")})
        titles = {}
        for i in range(0, len(ids), 50):
            vids = self.svc.videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute()
            titles.update({v["id"]: v["snippet"]["title"] for v in vids.get("items", [])})
        for m in msgs:
            m.context = titles.get(m.meta.get("video_id", ""), "")
        return msgs

    def stage(self, msg: Message, reply: str, store: Store) -> str:
        link = f"https://www.youtube.com/watch?v={msg.meta.get('video_id', '')}&lc={msg.id}"
        return queue_stage(msg, reply, store, link)
