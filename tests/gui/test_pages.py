"""Tests for Apps, Providers, Settings, and Diagnostics pages."""

from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path

from plumbcenter.gui.mainwindow import MainWindow
from plumbcenter.registry import REGISTRY
from tests.gui.conftest import wait_for_background


def test_apps_page_reflects_temp_workspace(qapp, isolated_settings, temp_workspace, provider_store):
    isolated_settings.setValue("workspace/root", str(temp_workspace))
    win = MainWindow(settings=isolated_settings, provider_store=provider_store)
    win.show()
    wait_for_background(150)

    try:
        apps = win.apps_page
        assert len(apps._cards) == len(REGISTRY) == 7
        assert "2/7 installed" in apps.summary_badge.text()

        pc_card = apps._cards["plumbcheck"]
        assert pc_card.install_btn.isHidden() is True
        assert pc_card.version_badge.text() == "v1.2.3"

        code_card = apps._cards["plumbcode"]
        assert code_card.install_btn.isHidden() is False

        # Filter to installed only -> 2 visible
        apps._set_filter("installed")
        visible = [c for c in apps._cards.values() if not c.isHidden()]
        assert len(visible) == 2
    finally:
        win.close()


def test_providers_save_test_and_defaults_without_leaking_key(
    qapp, isolated_settings, temp_workspace, provider_store, monkeypatch
):
    sentinel_key = "sk-SENTINEL-NEVER-WRITE-TO-JSON-998877"
    isolated_settings.setValue("workspace/root", str(temp_workspace))
    win = MainWindow(settings=isolated_settings, provider_store=provider_store)
    win.show()
    win.navigate("providers")
    wait_for_background()

    try:
        page = win.providers_page
        openai_card = page._cards["openai"]
        ollama_card = page._cards["ollama"]

        # Only Ollama has an editable base URL
        assert openai_card.url_input.isReadOnly() is True
        assert ollama_card.url_input.isReadOnly() is False

        # Save OpenAI with sentinel key
        openai_card.enable_cb.setChecked(True)
        openai_card.key_input.setText(sentinel_key)
        openai_card.model_input.setText("gpt-4.1-mini")
        openai_card.save_btn.click()
        wait_for_background()

        # Key field MUST be cleared and NEVER echoed back
        assert openai_card.key_input.text() == ""
        assert sentinel_key not in openai_card.key_input.placeholderText()
        assert openai_card.key_badge.text() == "Key saved"
        assert provider_store.get_key("openai") == sentinel_key

        # Assign per-app default
        combo = page._default_combos["plumbcheck"]
        idx = combo.findData("openai")
        assert idx >= 0
        combo.setCurrentIndex(idx)
        wait_for_background()

        # Verify providers.json is valid JSON and NEVER contains the sentinel key
        plumbnote_home = Path(provider_store.home if hasattr(provider_store, "home") else provider_store._home)
        json_file = plumbnote_home / "providers.json"
        assert json_file.is_file()
        raw_text = json_file.read_text(encoding="utf-8")
        assert sentinel_key not in raw_text
        data = json.loads(raw_text)
        assert data["defaults"]["plumbcheck"] == "openai"
        assert data["providers"]["openai"]["enabled"] is True

        # Mock tester.test_connection and click Test connection
        @dataclass
        class _FakeTestResult:
            ok: bool
            status: int
            message: str
            latency_ms: int

        fake_tester = types.SimpleNamespace(
            test_connection=lambda spec, api_key, base_url=None, timeout=10.0: _FakeTestResult(
                ok=(api_key == sentinel_key), status=200, message="Authenticated", latency_ms=42
            )
        )
        fake_pkg = types.ModuleType("plumbcenter.providers")
        fake_pkg.tester = fake_tester
        monkeypatch.setitem(sys.modules, "plumbcenter.providers", fake_pkg)
        monkeypatch.setitem(sys.modules, "plumbcenter.providers.tester", fake_tester)

        openai_card.test_btn.click()
        wait_for_background(150)
        assert "Authenticated" in openai_card.test_status_label.text()
        assert "42 ms" in openai_card.test_status_label.text()
        assert sentinel_key not in openai_card.test_status_label.text()
    finally:
        win.close()


def test_diagnostics_page_populates_and_copies_report(
    qapp, isolated_settings, temp_workspace, provider_store, monkeypatch
):
    from plumbcenter.gui.pages import diagnostics as diag_mod

    monkeypatch.setattr(diag_mod, "_probe_cmd", lambda cmd: f"{cmd[0]} mock-1.0")
    isolated_settings.setValue("workspace/root", str(temp_workspace))
    win = MainWindow(settings=isolated_settings, provider_store=provider_store)
    win.show()
    win.navigate("diagnostics")
    wait_for_background(250)

    try:
        diag = win.diagnostics_page
        assert diag.table.rowCount() == len(REGISTRY)
        report = diag.format_report_text()
        assert "PlumbCenter Diagnostics Report" in report
        assert "PlumbCheck" in report
        diag.copy_report()
        assert qapp.clipboard().text() == report
    finally:
        win.close()
