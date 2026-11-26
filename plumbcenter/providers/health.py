"""Provider health ping and quota summary.

Pings only providers the user enabled and configured (a key present, or none
needed). Each ping is the same cheap authenticated GET the Test button uses.
Quota is shown only where a provider exposes it (OpenRouter); other providers
report "not exposed" rather than a made-up number.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .catalog import PROVIDERS
from .tester import test_connection

__all__ = ["HealthEntry", "ping_all", "summarize"]

QUOTA_NOT_EXPOSED = "not exposed by provider API"


@dataclass
class HealthEntry:
    id: str
    name: str
    state: str                      # "ok" | "fail" | "skipped"
    latency_ms: int = 0
    message: str = ""
    quota: str = QUOTA_NOT_EXPOSED


def _ping_one(cfg, key: Optional[str], tester: Callable, timeout: float) -> HealthEntry:
    entry = HealthEntry(cfg.id, cfg.name, "skipped")
    if not cfg.enabled:
        entry.message = "Not enabled"
        return entry
    if cfg.needs_key and not key:
        entry.message = "No API key saved"
        return entry
    try:
        res = tester(cfg, key or "", base_url=cfg.base_url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - one provider must not break the sweep
        entry.state, entry.message = "fail", f"ping failed: {exc.__class__.__name__}"
        return entry
    entry.state = "ok" if res.ok else "fail"
    entry.latency_ms = int(res.latency_ms)
    entry.message = res.message
    if getattr(res, "quota", None):
        entry.quota = res.quota
    return entry


def ping_all(store, tester: Callable = test_connection, timeout: float = 8.0) -> List[HealthEntry]:
    """Ping every enabled+configured provider in parallel; result order follows the catalog."""
    configs = {c.id: c for c in store.list()}
    ordered = [configs[p.id] for p in PROVIDERS if p.id in configs]
    keys: Dict[str, Optional[str]] = {c.id: (store.get_key(c.id) if c.has_key else None) for c in ordered}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_ping_one, c, keys[c.id], tester, timeout) for c in ordered]
        return [f.result() for f in futures]


def summarize(entries: List[HealthEntry]) -> Dict[str, Any]:
    ok = [e for e in entries if e.state == "ok"]
    failed = [e for e in entries if e.state == "fail"]
    skipped = [e for e in entries if e.state == "skipped"]
    return {
        "ok": len(ok),
        "failed": len(failed),
        "skipped": len(skipped),
        "avg_latency_ms": int(sum(e.latency_ms for e in ok) / len(ok)) if ok else 0,
        "slowest": max(ok, key=lambda e: e.latency_ms).id if ok else None,
    }
