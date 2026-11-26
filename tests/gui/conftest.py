"""Shared fixtures for offscreen PySide6 GUI tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtTest import QTest

from plumbcenter.gui.app import create_application


@pytest.fixture(scope="session")
def qapp():
    app = create_application(["plumbcenter-test"])
    yield app


@pytest.fixture()
def isolated_settings(tmp_path: Path) -> QSettings:
    ini_path = tmp_path / "plumbcenter-settings.ini"
    return QSettings(str(ini_path), QSettings.Format.IniFormat)


@pytest.fixture(scope="session")
def temp_workspace(tmp_path_factory) -> Path:
    """Create a temp workspace with two fake git checkouts (plumbcheck, plumbdoctor)."""
    ws = tmp_path_factory.mktemp("workspace")

    # Create a real minimal git repo for plumbcheck with package.json
    pc = ws / "plumbcheck"
    pc.mkdir()
    (pc / "package.json").write_text('{"name": "plumbcheck", "version": "1.2.3"}\n', encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(pc), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@plumbnote.dev"], cwd=str(pc), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(pc), capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(pc), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(pc), capture_output=True, check=True)

    # Create a real minimal git repo for plumbdoctor
    pd = ws / "plumbdoctor"
    pd.mkdir()
    (pd / "README.md").write_text("# PlumbDoctor\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(pd), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@plumbnote.dev"], cwd=str(pd), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(pd), capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(pd), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(pd), capture_output=True, check=True)

    return ws


def wait_for_background(ms: int = 120, timeout_ms: int = 30000) -> None:
    """Flush QThreadPool and Qt event loop cleanly in offscreen tests."""
    QThreadPool.globalInstance().waitForDone(timeout_ms)
    QTest.qWait(ms)


@pytest.fixture()
def provider_store(tmp_path: Path, monkeypatch):
    """Return a real ProviderStore backed by MemoryBackend in a temp PLUMBNOTE_HOME.

    If plumbcenter.providers has not landed yet, falls back to a spec-compliant
    in-memory store writing atomic ~/.plumbnote/providers.json without keys.
    """
    plumbnote_home = tmp_path / "plumbnote_home"
    plumbnote_home.mkdir()
    monkeypatch.setenv("PLUMBNOTE_HOME", str(plumbnote_home))

    try:
        from plumbcenter.providers.secrets import MemoryBackend
        from plumbcenter.providers.store import ProviderStore

        return ProviderStore(home=plumbnote_home, secrets=MemoryBackend())
    except ImportError:
        import json
        from dataclasses import dataclass
        from plumbcenter.gui.pages.providers import _FALLBACK_PROVIDERS

        @dataclass
        class _Cfg:
            id: str
            enabled: bool
            base_url: str
            default_model: str
            has_key: bool

        class _StubStore:
            def __init__(self, home: Path):
                self.home = home
                self.path = home / "providers.json"
                self._keys: Dict[str, str] = {}
                self._data: Dict[str, dict] = {"version": 1, "providers": {}, "defaults": {}}

            def _save(self) -> None:
                tmp = self.path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)

            def list(self) -> List[_Cfg]:
                out = []
                for spec in _FALLBACK_PROVIDERS:
                    saved = self._data["providers"].get(spec.id, {})
                    out.append(
                        _Cfg(
                            id=spec.id,
                            enabled=bool(saved.get("enabled", False)),
                            base_url=saved.get("base_url", spec.base_url),
                            default_model=saved.get("default_model", spec.default_model),
                            has_key=spec.id in self._keys,
                        )
                    )
                return out

            def configure(self, pid, api_key=None, base_url=None, default_model=None, enabled=None):
                spec = next(s for s in _FALLBACK_PROVIDERS if s.id == pid)
                entry = self._data["providers"].setdefault(
                    pid,
                    {
                        "enabled": False,
                        "base_url": spec.base_url,
                        "default_model": spec.default_model,
                        "secret": "keyring",
                    },
                )
                if api_key is not None:
                    self._keys[pid] = api_key
                if base_url is not None:
                    entry["base_url"] = base_url
                if default_model is not None:
                    entry["default_model"] = default_model
                if enabled is not None:
                    entry["enabled"] = bool(enabled)
                self._save()

            def clear_key(self, pid):
                self._keys.pop(pid, None)

            def get_key(self, pid) -> Optional[str]:
                return self._keys.get(pid)

            def set_default(self, app_id, provider_id):
                if provider_id is None:
                    self._data["defaults"].pop(app_id, None)
                else:
                    self._data["defaults"][app_id] = provider_id
                self._save()

            def defaults(self) -> Dict[str, str]:
                return dict(self._data["defaults"])

        return _StubStore(plumbnote_home)
