"""Shared theme file contract and the secret-redacted diagnostics bundle."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from plumbcenter import diagnostics_bundle as db
from plumbcenter import shared_settings
from plumbcenter.providers.secrets import MemoryBackend
from plumbcenter.providers.store import ProviderStore

KEY = "sk-bundle-SENTINEL-0123456789abcdef"


# ---- shared settings -------------------------------------------------------

def test_theme_roundtrip_and_path(tmp_path):
    assert shared_settings.settings_path(tmp_path) == tmp_path.resolve() / "settings.json"
    assert shared_settings.load_theme(tmp_path) is None
    assert shared_settings.save_theme("light", tmp_path) is True
    assert shared_settings.load_theme(tmp_path) == "light"
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data == {"version": 1, "theme": "light"}


def test_save_preserves_keys_owned_by_other_apps(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"version": 1, "theme": "dark", "plumbstudio": {"zoom": 3}}), encoding="utf-8")
    shared_settings.save_theme("light", tmp_path)
    data = shared_settings.read_settings(tmp_path)
    assert data["plumbstudio"] == {"zoom": 3} and data["theme"] == "light"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("content", ["", "not json", "[1,2]", '{"theme": "neon"}', '{"theme": 5}'])
def test_bad_files_are_ignored_not_fatal(tmp_path, content):
    (tmp_path / "settings.json").write_text(content, encoding="utf-8")
    assert shared_settings.load_theme(tmp_path) is None
    assert shared_settings.save_theme("dark", tmp_path) is True      # repaired on next write
    assert shared_settings.load_theme(tmp_path) == "dark"


def test_invalid_theme_rejected_and_unwritable_home_returns_false(tmp_path):
    with pytest.raises(ValueError):
        shared_settings.save_theme("neon", tmp_path)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert shared_settings.save_theme("dark", blocker / "sub") is False


def test_theme_value_is_case_insensitive(tmp_path):
    (tmp_path / "settings.json").write_text('{"theme": " LIGHT "}', encoding="utf-8")
    assert shared_settings.load_theme(tmp_path) == "light"


# ---- redaction -------------------------------------------------------------

def test_redactor_scrubs_known_keys_patterns_and_home():
    home = Path("C:/Users/someone")
    r = db.Redactor([KEY], home=home)
    text = (f"key={KEY} Authorization: Bearer abcdef1234567890 url http://127.0.0.1:5/#auth=deadbeef01 "
            f"api_key=hunter2hunter2 sk-other-ABCDEFGHIJKLMNOP AIzaSyA1234567890123456789012 "
            f"ghp_abcdefghijklmnopqrstuvwxyz0123 at C:\\Users\\someone\\proj and C:/Users/someone/proj")
    out = r.text(text)
    for leaked in (KEY, "abcdef1234567890", "deadbeef01", "hunter2hunter2", "ABCDEFGHIJKLMNOP",
                   "AIzaSy", "ghp_abcdef", "someone"):
        assert leaked not in out, leaked
    assert "~" in out


def test_redactor_walks_nested_objects_including_keys():
    r = db.Redactor([KEY])
    out = r.obj({"a": [KEY, {"b": KEY}], KEY: 1, "n": 5})
    assert KEY not in json.dumps(out) and out["n"] == 5


# ---- bundle ----------------------------------------------------------------

def _store(tmp_path):
    s = ProviderStore(home=tmp_path / "home", secrets=MemoryBackend())
    s.configure("openai", api_key=KEY, enabled=True)
    s.set_default("plumbdoctor", "openai")
    return s


def test_bundle_never_contains_the_key_and_lists_providers(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(db.runner, "status", lambda app_id=None: [
        {"app": "plumbcheck", "action": "studio", "pid": 1, "url": None}])
    monkeypatch.setattr(db.runner, "tail_log", lambda a, b, lines=50: f"boot token={KEY}\nopen http://127.0.0.1:1/#auth=cafebabe99")
    b = db.build_bundle(root=tmp_path, store=store)
    blob = json.dumps(b)
    assert KEY not in blob and "cafebabe99" not in blob
    openai = next(p for p in b["providers"] if p["id"] == "openai")
    assert openai["has_key"] is True and "key" not in {k for k in openai if k != "has_key"}
    assert b["provider_defaults"] == {"plumbdoctor": "openai"}
    assert b["redaction"]["keys_scrubbed"] == 1
    assert "plumbcheck-studio" in b["logs"]
    assert len(b["apps"]) == 7


def test_bundle_survives_a_failing_keyring(tmp_path):
    class Broken(MemoryBackend):
        def get(self, name):
            raise RuntimeError("keyring locked")

    store = ProviderStore(home=tmp_path / "h", secrets=Broken())
    assert db.build_bundle(root=tmp_path, store=store)["bundle_version"] == 1
    assert db.build_bundle(root=tmp_path, store=None)["providers"] == []


def test_export_zip_and_json(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(db.runner, "status", lambda app_id=None: [
        {"app": "plumbcheck", "action": "studio", "pid": 1, "url": None}])
    monkeypatch.setattr(db.runner, "tail_log", lambda a, b, lines=50: f"secret {KEY}")
    z = db.export_bundle(tmp_path / "out" / "b.zip", root=tmp_path, store=store)
    assert z["format"] == "zip" and z["bytes"] > 0
    with zipfile.ZipFile(z["path"]) as zf:
        names = set(zf.namelist())
        assert {"report.json", "README.txt", "logs/plumbcheck-studio.log"} <= names
        assert all(KEY not in zf.read(n).decode("utf-8") for n in names)
        assert "logs" not in json.loads(zf.read("report.json"))
    j = db.export_bundle(tmp_path / "b.json", root=tmp_path, store=store)
    assert j["format"] == "json" and KEY not in Path(j["path"]).read_text(encoding="utf-8")
    other = db.export_bundle(tmp_path / "b.txt", root=tmp_path, store=store)     # unknown ext -> json
    assert other["path"].endswith(".json")
