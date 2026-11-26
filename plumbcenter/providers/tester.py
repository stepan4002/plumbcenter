"""Cheap authenticated connection tests. urllib only.

Phase 0 ships the contract. Per-provider requests are filled in after each
endpoint is checked against the provider's official docs. Nothing here may
place the API key in ``message`` or raise it in an exception string.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["TestResult", "test_connection"]


@dataclass
class TestResult:
    ok: bool
    status: str
    message: str
    latency_ms: int


def _redact(message: str, api_key: Optional[str]) -> str:
    if api_key and api_key in message:
        return message.replace(api_key, "***")
    return message


def test_connection(spec, api_key, base_url=None, timeout=10.0) -> TestResult:
    """Probe ``spec`` at ``base_url`` (catalog default when omitted).

    Returns a result and does not raise for HTTP failures. Network errors come
    back as ``ok=False``. The key is sent only to the configured provider host
    once the real probes land; this stub makes no request.
    """
    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        return TestResult(False, "bad_timeout", "timeout must be a number", 0)
    if timeout <= 0:
        return TestResult(False, "bad_timeout", "timeout must be positive", 0)

    needs_key = bool(getattr(spec, "needs_key", True))
    key = (str(api_key).strip() if api_key else "")
    if needs_key and not key:
        return TestResult(False, "no_key", "API key is required", 0)

    url = base_url or getattr(spec, "base_url", "") or ""
    if not url:
        return TestResult(False, "no_url", "base_url is required", 0)

    # VERIFY: replace this stub with the official models/tags request for spec.test_kind.
    # Do not log or return `key`.
    _ = (url, timeout, key)
    return TestResult(
        False,
        "not_implemented",
        _redact("Connection test is not implemented yet", key or None),
        0,
    )
