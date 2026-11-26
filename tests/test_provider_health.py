"""Provider health ping + quota summary. The tester is faked: no network, no real keys."""

from __future__ import annotations

from plumbcenter.providers import health
from plumbcenter.providers.secrets import MemoryBackend
from plumbcenter.providers.store import ProviderStore
from plumbcenter.providers.tester import TestResult, _openrouter_quota

SENTINEL = "sk-health-SENTINEL-0123456789"


def _store(tmp_path):
    return ProviderStore(home=tmp_path, secrets=MemoryBackend())


def test_ping_all_only_pings_enabled_configured_providers(tmp_path):
    store = _store(tmp_path)
    store.configure("openai", api_key=SENTINEL, enabled=True)
    store.configure("groq", api_key=SENTINEL, enabled=False)       # has key but disabled
    store.configure("anthropic", enabled=True)                      # enabled, no key
    store.configure("ollama", enabled=True)                         # local, needs no key
    pinged = []

    def tester(cfg, key, base_url=None, timeout=8.0):
        pinged.append((cfg.id, key))
        return TestResult(cfg.id != "ollama", "200" if cfg.id != "ollama" else "error", "msg", 40)

    entries = {e.id: e for e in health.ping_all(store, tester=tester)}
    assert sorted(i for i, _ in pinged) == ["ollama", "openai"]
    assert entries["openai"].state == "ok" and entries["openai"].latency_ms == 40
    assert entries["ollama"].state == "fail"
    assert entries["groq"].state == "skipped" and entries["groq"].message == "Not enabled"
    assert entries["anthropic"].message == "No API key saved"
    assert len(entries) == 8
    # The key never leaks into any entry.
    assert SENTINEL not in repr(entries)


def test_ping_all_survives_a_crashing_tester(tmp_path):
    store = _store(tmp_path)
    store.configure("openai", api_key=SENTINEL, enabled=True)

    def tester(*a, **k):
        raise RuntimeError(SENTINEL)

    e = {x.id: x for x in health.ping_all(store, tester=tester)}["openai"]
    assert e.state == "fail" and SENTINEL not in e.message


def test_quota_is_not_invented(tmp_path):
    store = _store(tmp_path)
    store.configure("openai", api_key=SENTINEL, enabled=True)
    store.configure("openrouter", api_key=SENTINEL, enabled=True)

    def tester(cfg, key, base_url=None, timeout=8.0):
        return TestResult(True, "200", "Connection ok", 10, "$4.50 left of $10.00" if cfg.id == "openrouter" else None)

    e = {x.id: x for x in health.ping_all(store, tester=tester)}
    assert e["openai"].quota == health.QUOTA_NOT_EXPOSED
    assert e["openrouter"].quota == "$4.50 left of $10.00"


def test_summarize():
    es = [health.HealthEntry("a", "A", "ok", 100), health.HealthEntry("b", "B", "ok", 300),
          health.HealthEntry("c", "C", "fail", 5), health.HealthEntry("d", "D", "skipped")]
    s = health.summarize(es)
    assert (s["ok"], s["failed"], s["skipped"], s["avg_latency_ms"], s["slowest"]) == (2, 1, 1, 200, "b")
    assert health.summarize([])["avg_latency_ms"] == 0


def test_openrouter_quota_parsing():
    assert _openrouter_quota(b'{"data":{"usage":1.5,"limit":10,"limit_remaining":8.5}}') == "$8.50 left of $10.00"
    assert _openrouter_quota(b'{"data":{"usage":2,"limit":null}}') == "$2.00 used, no spend limit"
    assert _openrouter_quota(b"not json") is None
    assert _openrouter_quota(b'{"data":{}}') is None
