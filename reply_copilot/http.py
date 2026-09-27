"""Tiny JSON-over-HTTPS client on the standard library, with backoff and secret-safe errors.

Tests replace `transport` to run without a network.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable

from .privacy import redact_secrets

# transport(method, url, headers, body_bytes, timeout) -> (status, headers_dict, body_bytes)
Transport = Callable[[str, str, dict, bytes | None, float], tuple[int, dict, bytes]]

RETRY_STATUS = {408, 429, 500, 502, 503, 504, 529}


class HttpError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(redact_secrets(message))
        self.status = status


def _urllib_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read() or b""


transport: Transport = _urllib_transport


def request_json(method: str, url: str, *, headers: dict | None = None, body: dict | None = None,
                 timeout: float = 30.0, retries: int = 3, sleep=None) -> tuple[dict, int]:
    """Send a JSON request; return (parsed body, elapsed ms of the successful attempt)."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
    sleep = sleep or time.sleep
    last = ""
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        try:
            status, resp_headers, raw = transport(method, url, hdrs, data, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            status, resp_headers, raw, last = 0, {}, b"", f"network error: {exc}"
        ms = round((time.perf_counter() - t0) * 1000)
        if 200 <= status < 300:
            return (json.loads(raw.decode("utf-8")) if raw else {}), ms
        if status:
            last = f"HTTP {status}: {raw.decode('utf-8', 'replace')[:300]}"
        if status and status not in RETRY_STATUS:
            raise HttpError(f"{method} {url.split('?')[0]} failed, {last}", status)
        if attempt < retries:
            wait = resp_headers.get("retry-after") or resp_headers.get("Retry-After")
            try:
                sleep(min(float(wait), 30.0) if wait else 2 ** attempt)
            except ValueError:
                sleep(2 ** attempt)
    raise HttpError(f"{method} {url.split('?')[0]} failed after {retries + 1} attempts, {last}",
                    status or None)
