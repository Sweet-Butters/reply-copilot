"""OAuth for Google APIs as an installed (desktop) app. Tokens live outside the repo.

Needs: pip install google-api-python-client google-auth-oauthlib
The client secret JSON path comes from GOOGLE_CLIENT_SECRET_FILE; this module never prints tokens.
"""
from __future__ import annotations

import os
from pathlib import Path

from .base import AdapterError


def load_credentials(name: str, scopes: list[str], token_dir: Path, *, interactive: bool = False):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        raise AdapterError("pip install google-api-python-client google-auth-oauthlib") from None

    token_path = token_dir / f"{name}.json"
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save(token_path, creds)
            return creds
        except Exception as exc:  # google.auth.exceptions.RefreshError and friends
            if not interactive:
                raise AdapterError(f"{name} token refresh failed ({type(exc).__name__}); "
                                   f"run: python -m reply_copilot auth {name}") from None
    if not interactive:
        raise AdapterError(f"no {name} token yet; run: python -m reply_copilot auth {name}")

    secret = os.environ.get("GOOGLE_CLIENT_SECRET_FILE", "").strip()
    if not secret or not Path(secret).exists():
        raise AdapterError("set GOOGLE_CLIENT_SECRET_FILE to your OAuth desktop client JSON")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(secret, scopes)
    creds = flow.run_local_server(port=0, open_browser=True)
    _save(token_path, creds)
    return creds


def _save(path: Path, creds) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
