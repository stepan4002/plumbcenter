"""Cheap authenticated connection tests. urllib only.

The API key is sent only to the host of the configured base URL. Redirects to
any other host are refused. The key is removed from every result message.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit

__all__ = ["TestResult", "test_connection"]

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


@dataclass
class TestResult:
    __test__ = False  # not a pytest class
    ok: bool
    status: str
    message: str
    latency_ms: int
    quota: Optional[str] = None   # human-readable credit/limit line, only when the provider exposes one


def _redact(message: str, api_key: Optional[str]) -> str:
    if api_key and message and api_key in message:
        return message.replace(api_key, "***")
    return message


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _check_url(url: str) -> Optional[str]:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.username or parts.password:
        return "base_url must not include credentials"
    if not host:
        return "base_url is missing a host"
    if parts.scheme == "https":
        return None
    if parts.scheme == "http" and host in _LOOPBACK:
        return None
    if parts.scheme == "http":
        return "http is only allowed for a loopback host"
    return "base_url must use https"


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects only when the host does not change."""

    def __init__(self, origin: str) -> None:
        super().__init__()
        self.origin = origin.lower()

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _host(newurl) != self.origin:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _endpoint(spec, base_url: str) -> Tuple[str, Dict[str, str], str]:
    """Return (url, headers-without-key, note).

    Headers that carry the key are added by the caller so this function can be
    tested without a secret. `note` is a user-visible caveat, or "".
    """
    kind = getattr(spec, "test_kind", "openai")
    provider_id = getattr(spec, "id", "")
    root = base_url.rstrip("/")
    note = ""
    headers = {"Accept": "application/json", "User-Agent": "plumbcenter"}

    if kind == "ollama":
        return root + "/api/tags", headers, note
    if kind == "anthropic":
        path = "/models" if root.endswith("/v1") else "/v1/models"
        headers["anthropic-version"] = "2023-06-01"
        return root + path, headers, note
    if kind == "gemini":
        # x-goog-api-key is the documented header. The key is not placed in the query.
        return root + "/models", headers, note
    if provider_id == "openrouter":
        # GET /api/v1/key is the documented authenticated check. /models is public.
        return root + "/key", headers, note
    if provider_id == "kilo":
        # VERIFY: https://kilo.ai/gateway documents GET /models with no authentication.
        note = "Kilo documents GET /models as a public list, so a 200 does not prove the key."
    if provider_id == "zai":
        # VERIFY: https://docs.z.ai/api-reference/introduction documents Bearer auth and
        # POST /chat/completions. It does not publish a models-list GET. This probe uses
        # the OpenAI-compatible GET {base}/models on the documented base URL.
        note = "Z.ai does not publish a models-list GET; this probes GET /models."
    return root + "/models", headers, note


def _auth_headers(spec, api_key: str) -> Dict[str, str]:
    kind = getattr(spec, "test_kind", "openai")
    if kind == "ollama" or not api_key:
        return {}
    if kind == "anthropic":
        return {"x-api-key": api_key}
    if kind == "gemini":
        return {"x-goog-api-key": api_key}
    return {"Authorization": "Bearer " + api_key}


def _openrouter_quota(body: bytes) -> Optional[str]:
    """OpenRouter GET /key returns {"data": {"usage", "limit", "limit_remaining"}} (USD credits)."""
    try:
        data = (json.loads(body.decode("utf-8", "replace")) or {}).get("data") or {}
        usage, limit, left = data.get("usage"), data.get("limit"), data.get("limit_remaining")
        if limit is None:
            return f"${float(usage):.2f} used, no spend limit" if usage is not None else None
        remaining = float(left) if left is not None else float(limit) - float(usage or 0)
        return f"${remaining:.2f} left of ${float(limit):.2f}"
    except (ValueError, TypeError, AttributeError):
        return None


def test_connection(spec, api_key, base_url=None, timeout=10.0) -> TestResult:
    """Probe `spec` with a cheap GET. HTTP failures return ok=False and do not raise."""
    key = str(api_key).strip() if api_key else ""
    try:
        timeout_s = float(timeout)
    except (TypeError, ValueError):
        return TestResult(False, "bad_timeout", "timeout must be a number", 0)
    if timeout_s <= 0:
        return TestResult(False, "bad_timeout", "timeout must be positive", 0)

    needs_key = bool(getattr(spec, "needs_key", True))
    if needs_key and not key:
        return TestResult(False, "no_key", "API key is required", 0)

    url_base = (base_url or getattr(spec, "base_url", "") or "").strip()
    if not url_base:
        return TestResult(False, "no_url", "base_url is required", 0)
    problem = _check_url(url_base)
    if problem:
        return TestResult(False, "bad_url", _redact(problem, key), 0)

    target, headers, note = _endpoint(spec, url_base)
    if _host(target) != _host(url_base):
        return TestResult(False, "bad_url", "probe host does not match base_url", 0)
    headers = dict(headers)
    headers.update(_auth_headers(spec, key))

    request = urllib.request.Request(target, headers=headers, method="GET")
    opener = urllib.request.build_opener(_SameHostRedirect(_host(url_base)))
    started = time.monotonic()
    body = b""
    try:
        with opener.open(request, timeout=timeout_s) as response:
            status = int(getattr(response, "status", 0) or response.getcode() or 0)
            body = response.read(4096)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        try:
            exc.read(2048)
        except Exception:
            pass
    except Exception as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        text = _redact(str(exc) or exc.__class__.__name__, key)
        return TestResult(False, "error", text or "connection failed", elapsed)

    elapsed = int((time.monotonic() - started) * 1000)
    ok = 200 <= status < 300
    message = "Connection ok" if ok else f"HTTP {status}"
    if ok and note:
        message = message + ". " + note
    quota = _openrouter_quota(body) if ok and getattr(spec, "id", "") == "openrouter" else None
    return TestResult(ok, str(status), _redact(message, key), elapsed, quota)
