"""What leaves the machine: trim quoted history and signatures, mask contact details, hide secrets.

prepare() is the only way message text reaches a model provider.
"""
from __future__ import annotations

import os
import re

MAX_CHARS = 2000

SECRET_ENV_VARS = (
    "TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY", "AI_GATEWAY_API_KEY", "OPENCODE_API_KEY", "IG_ACCESS_TOKEN",
)

# A line that starts the quoted part of a reply; everything from it on is dropped.
_QUOTE_HEADERS = [
    re.compile(r"^On .{3,200} wrote:\s*$"),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.I),
    re.compile(r"^-{2,}\s*원본 메시지\s*-{2,}"),
    re.compile(r"^-{2,}\s*Forwarded message\s*-{2,}", re.I),
    re.compile(r"^\d{4}[년.\-/]\s*\d{1,2}[월.\-/]\s*\d{1,2}.{0,40}(작성|님이 작성|wrote)"),
    re.compile(r"^(From|보낸 사람)\s*:\s*.+"),
]
# A line that starts the signature; everything from it on is dropped.
_SIGNATURE_STARTS = [
    re.compile(r"^--\s*$"),
    re.compile(r"^_{5,}\s*$"),
    re.compile(r"^(Sent from my|Get Outlook for|iPhone에서 보냄|Galaxy에서 보냄|모바일에서 보냄)"),
]
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\d)(\+?82[-\s]?)?0?1[016789][-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)"
                    r"|(?<!\d)0\d{1,2}[-\s.]\d{3,4}[-\s.]\d{4}(?!\d)")
_URL_TOKEN = re.compile(r"([?&](token|key|sig|signature|auth)=)[^&\s]+", re.I)


def strip_quoted(text: str) -> str:
    out = []
    for line in text.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if s.startswith(">"):
            continue
        if any(p.search(s) for p in _QUOTE_HEADERS) or any(p.search(s) for p in _SIGNATURE_STARTS):
            break
        out.append(line)
    return "\n".join(out).strip()


def mask_contacts(text: str) -> str:
    text = _EMAIL.sub("[EMAIL]", text)
    text = _PHONE.sub("[PHONE]", text)
    return _URL_TOKEN.sub(r"\1[REDACTED]", text)


def display_name(sender: str) -> str:
    """'홍길동 <hong@x.ac.kr>' -> '홍길동'; a bare address -> '[EMAIL]'."""
    m = re.match(r'\s*"?([^"<]+?)"?\s*<[^>]+>\s*$', sender or "")
    if m:
        return m.group(1).strip()
    return mask_contacts(sender or "").strip()


def prepare(text: str, max_chars: int = MAX_CHARS) -> str:
    """Clean text for a provider: no quoted history, no signature, no addresses or phone numbers."""
    cleaned = mask_contacts(strip_quoted(text or ""))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned[:max_chars]


def redact_secrets(text: object) -> str:
    """Replace any live key value found in text; use on every error message before printing."""
    s = str(text)
    for name in SECRET_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if len(value) >= 6:
            s = s.replace(value, "[REDACTED]")
    return s
