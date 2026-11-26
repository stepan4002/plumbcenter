"""Secret-redacted diagnostics bundle (.json or .zip) for support requests.

Redaction is layered: (1) every API key the hub holds is removed by exact value, (2) common secret
shapes are scrubbed by pattern (provider key prefixes, Bearer tokens, ``#auth=`` launch tokens,
``key=value`` pairs), (3) the user's home directory is replaced by ``~``. The bundle never reads
a key into a field; keys are only used to build the scrubber.
"""

from __future__ import annotations

import json
import platform
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import __version__, discovery, runner, shared_settings
from .providers.catalog import PROVIDERS

__all__ = ["Redactor", "build_bundle", "export_bundle"]

_PATTERNS = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer ***"),
    (re.compile(r"#auth=[0-9A-Za-z._-]+"), "#auth=***"),
    (re.compile(r"\b(?:sk|pk|gsk|xai|rk)[-_][A-Za-z0-9_-]{12,}"), "***"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"), "***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "***"),
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)(\s*[=:]\s*)(?!\*\*\*)[^\s\"',;&]+"),
     r"\1\2***"),
)
MAX_LOG_CHARS = 20000


class Redactor:
    def __init__(self, secrets: Iterable[str] = (), home: Optional[Path] = None) -> None:
        # Longest first so a key that contains another is replaced whole.
        self._secrets = sorted({s for s in secrets if s and len(s) >= 4}, key=len, reverse=True)
        h = Path(home) if home else Path.home()
        self._homes = sorted({str(h), str(h).replace("\\", "/")}, key=len, reverse=True)

    def text(self, value: str) -> str:
        for s in self._secrets:
            value = value.replace(s, "***")
        for rx, repl in _PATTERNS:
            value = rx.sub(repl, value)
        for h in self._homes:
            if h and h not in ("/", "\\"):
                value = value.replace(h, "~")
        return value

    def obj(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {self.text(str(k)): self.obj(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.obj(v) for v in value]
        return value


def _collect_secrets(store) -> List[str]:
    keys: List[str] = []
    if store is None:
        return keys
    for spec in PROVIDERS:
        try:
            k = store.get_key(spec.id)
        except Exception:  # noqa: BLE001 - an unreadable keyring must not block diagnostics
            k = None
        if k:
            keys.append(k)
    return keys


def _provider_summary(store) -> List[Dict[str, Any]]:
    if store is None:
        return []
    out = []
    try:
        for c in store.list():
            out.append({"id": c.id, "enabled": c.enabled, "has_key": c.has_key,
                        "base_url": c.base_url, "default_model": c.default_model})
        return out
    except Exception as exc:  # noqa: BLE001
        return [{"error": exc.__class__.__name__}]


def _safe(fn, default):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return default if default is not None else {"error": exc.__class__.__name__}


def build_bundle(root=None, store=None, tail_lines: int = 200) -> Dict[str, Any]:
    """Collect the report. Everything in the returned dict is already redacted."""
    red = Redactor(_collect_secrets(store))
    statuses = _safe(lambda: discovery.scan(root), [])
    apps = []
    for st in statuses:
        health = _safe(lambda st=st: runner.health(st.id, root=root), {"state": "error"})
        apps.append({"id": st.id, "installed": st.installed, "version": st.version, "branch": st.branch,
                     "commit": st.commit, "dirty": st.dirty, "path": st.path, "health": health})
    procs = _safe(runner.status, [])
    logs: Dict[str, str] = {}
    for p in procs:
        text = _safe(lambda p=p: runner.tail_log(p["app"], p["action"], lines=tail_lines), "")
        logs[f"{p['app']}-{p['action']}"] = text[-MAX_LOG_CHARS:]
    shared = shared_settings.read_settings()
    bundle = {
        "bundle_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
        "plumbcenter": __version__,
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": sys.version.split()[0],
        "workspace": str(root) if root else str(discovery.hub_root()),
        "apps": apps,
        "processes": procs,
        "providers": _provider_summary(store),
        "provider_defaults": _safe(lambda: dict(store.defaults()), {}) if store is not None else {},
        "shared_settings": shared,
        "logs": logs,
        "redaction": {"keys_scrubbed": len(red._secrets), "note": "API keys are never included."},
    }
    return red.obj(bundle)


def export_bundle(dest, root=None, store=None) -> Dict[str, Any]:
    """Write the bundle to ``dest``: ``.zip`` (report.json + one file per log) or ``.json``.

    Returns {"path", "format", "bytes"}.
    """
    dest = Path(dest)
    bundle = build_bundle(root=root, store=store)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffix.lower() == ".zip":
        logs = bundle.pop("logs", {})
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("report.json", json.dumps(bundle, indent=2, ensure_ascii=False) + "\n")
            for name, text in logs.items():
                safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
                zf.writestr(f"logs/{safe}.log", text)
            zf.writestr("README.txt", "PlumbCenter diagnostics bundle. API keys, tokens and your home "
                                      "directory path are redacted. Review before sharing.\n")
        fmt = "zip"
    else:
        dest = dest.with_suffix(".json") if dest.suffix.lower() != ".json" else dest
        dest.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        fmt = "json"
    return {"path": str(dest), "format": fmt, "bytes": dest.stat().st_size}
