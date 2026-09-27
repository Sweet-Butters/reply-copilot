"""Gmail: read new mail in the owner's own inbox, save the chosen reply as a draft.

Scopes: gmail.readonly (read) + gmail.compose (drafts.create). Google offers no drafts-only scope;
gmail.compose also permits sending, but this module has no code path that sends.
"""
from __future__ import annotations

import base64
import html
import re
from email.message import EmailMessage
from email.utils import parseaddr

from ..models import Message
from ..store import Store
from .base import AdapterError

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/gmail.compose"]
DEFAULT_QUERY = "in:inbox is:unread newer_than:3d -category:promotions -category:social -category:forums"


def _headers(payload: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _body_text(payload: dict) -> str:
    """Prefer text/plain; fall back to text/html with tags stripped."""
    plain, htm = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            htm.append(_decode(data))
        for p in part.get("parts", []) or []:
            walk(p)

    walk(payload)
    if plain:
        return "\n".join(plain)
    if htm:
        text = re.sub(r"(?is)<(script|style).*?</\1>", "", "\n".join(htm))
        text = re.sub(r"(?i)<br\s*/?>|</p>", "\n", text)
        return html.unescape(re.sub(r"<[^>]+>", "", text))
    return ""


def parse_message(raw: dict) -> Message:
    """Gmail users.messages.get(format=full) JSON -> Message."""
    payload = raw.get("payload", {})
    h = _headers(payload)
    return Message(
        id=raw["id"], channel="gmail", kind="email",
        sender=h.get("from", ""), subject=h.get("subject", ""), text=_body_text(payload),
        received_at=h.get("date", ""),
        meta={"thread_id": raw.get("threadId"), "message_id_header": h.get("message-id", ""),
              "references": h.get("references", ""), "reply_to": h.get("reply-to", ""),
              "list_unsubscribe": bool(h.get("list-unsubscribe"))},
    )


def build_draft(msg: Message, reply: str, owner_email: str = "") -> dict:
    """Body for users.drafts.create: a reply in the same thread, addressed to the sender."""
    em = EmailMessage()
    to = msg.meta.get("reply_to") or msg.sender
    em["To"] = to
    if owner_email:
        em["From"] = owner_email
    subject = msg.subject or ""
    em["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}".strip()
    mid = msg.meta.get("message_id_header")
    if mid:
        em["In-Reply-To"] = mid
        em["References"] = f"{msg.meta.get('references', '')} {mid}".strip()
    em.set_content(reply)
    raw = base64.urlsafe_b64encode(em.as_bytes()).decode("ascii")
    body: dict = {"message": {"raw": raw}}
    if msg.meta.get("thread_id"):
        body["message"]["threadId"] = msg.meta["thread_id"]
    return body


class GmailAdapter:
    name = "gmail"

    def __init__(self, token_dir, owner_email: str = "", query: str = DEFAULT_QUERY,
                 service=None, interactive: bool = False):
        self.owner_email = owner_email.lower()
        self.query = query
        if service is None:
            from .google_auth import load_credentials
            creds = load_credentials("gmail", SCOPES, token_dir, interactive=interactive)
            try:
                from googleapiclient.discovery import build
            except ImportError:
                raise AdapterError("pip install google-api-python-client") from None
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self.svc = service

    def fetch(self, limit: int) -> list[Message]:
        listing = self.svc.users().messages().list(userId="me", q=self.query, maxResults=limit).execute()
        out = []
        for ref in listing.get("messages", []) or []:
            raw = self.svc.users().messages().get(userId="me", id=ref["id"], format="full").execute()
            msg = parse_message(raw)
            if self.owner_email and parseaddr(msg.sender)[1].lower() == self.owner_email:
                continue  # my own message
            out.append(msg)
        return out

    def stage(self, msg: Message, reply: str, store: Store) -> str:
        """Save as a Gmail draft (the only write this adapter makes)."""
        draft = self.svc.users().drafts().create(userId="me", body=build_draft(msg, reply, self.owner_email)).execute()
        return f"Gmail draft {draft.get('id', '?')}"
