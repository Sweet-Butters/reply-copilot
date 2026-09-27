"""Channel registry: name -> factory(settings, interactive)."""
from __future__ import annotations

from ..config import Settings
from .base import Adapter, AdapterError


def _fixtures(s: Settings, interactive: bool):
    from .fixtures import FixturesAdapter
    return FixturesAdapter()


def _gmail(s: Settings, interactive: bool):
    from .gmail import GmailAdapter
    return GmailAdapter(s.token_dir, s.owner_email, interactive=interactive)


def _youtube(s: Settings, interactive: bool):
    import os

    from .youtube import YouTubeAdapter
    return YouTubeAdapter(s.token_dir, os.environ.get("YOUTUBE_CHANNEL_ID", "").strip(), interactive=interactive)


def _instagram(s: Settings, interactive: bool):
    from .instagram import InstagramAdapter
    return InstagramAdapter()


CHANNELS = {"fixtures": _fixtures, "gmail": _gmail, "youtube": _youtube, "instagram": _instagram}


def build_adapter(name: str, s: Settings, interactive: bool = False) -> Adapter:
    if name not in CHANNELS:
        raise AdapterError(f"unknown channel {name!r}; use one of {sorted(CHANNELS)}")
    return CHANNELS[name](s, interactive)


__all__ = ["build_adapter", "CHANNELS", "Adapter", "AdapterError"]
