"""Shared test helpers: fake HTTP transport and env isolation."""
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reply_copilot import http  # noqa: E402

KEY_VARS = ["TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY", "AI_GATEWAY_API_KEY", "OPENCODE_API_KEY", "IG_ACCESS_TOKEN"]


@contextmanager
def env(**values):
    saved = {k: os.environ.get(k) for k in set(KEY_VARS) | set(values)}
    for k in KEY_VARS:
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in values.items() if v is not None})
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class FakeTransport:
    """Replays queued (status, body) responses and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers,
                           "body": json.loads(body.decode("utf-8")) if body else None})
        status, payload = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        return status, {}, raw


@contextmanager
def fake_http(*responses):
    fake = FakeTransport(*responses)
    saved = http.transport
    http.transport = fake
    try:
        yield fake
    finally:
        http.transport = saved
