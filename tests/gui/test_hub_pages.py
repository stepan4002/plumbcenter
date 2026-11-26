"""Processes, Updates, and provider-health UI. Offscreen; no network, no real processes."""

from __future__ import annotations

import time

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from plumbcenter import runner, updater
from plumbcenter.gui.mainwindow import MainWindow
from plumbcenter.gui.pages.processes import format_uptime
from plumbcenter.providers.health import HealthEntry


def _pump(app, cond, timeout=10.0):
    """Process events and sleep (QTest.qWait starves worker threads in headless runs)."""
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        QThreadPool.globalInstance().waitForDone(20)
        if cond():
            return True
        time.sleep(0.02)
    app.processEvents()
    return cond()


def _window(isolated_settings, temp_workspace, provider_store):
    isolated_settings.setValue("workspace/root", str(temp_workspace))
    return MainWindow(settings=isolated_settings, provider_store=provider_store)


def test_format_uptime():
    assert format_uptime(None) == "-"
    assert format_uptime(100, now=130) == "30s"
    assert format_uptime(0.5, now=125.5) == "2m 05s"
    assert format_uptime(1, now=3 * 3600 + 7 * 60 + 1) == "3h 07m"


def test_processes_page_lists_stops_and_restarts(qapp, isolated_settings, temp_workspace, provider_store, monkeypatch):
    rows = [{"app": "plumbcheck", "action": "studio", "pid": 4242, "running": True,
             "started_at": time.time() - 90, "url": "http://127.0.0.1:5000", "log": None}]
    calls = []
    monkeypatch.setattr(runner, "status", lambda app_id=None: list(rows))
    monkeypatch.setattr(runner, "tail_log", lambda a, b, lines=50: "listening on 5000")
    monkeypatch.setattr(runner, "stop", lambda a, b: calls.append(("stop", a, b)) or rows.clear())
    monkeypatch.setattr(runner, "restart", lambda a, b, root=None: calls.append(("restart", a, b)) or {})
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        page = win.processes_page
        win.navigate("processes")
        assert _pump(qapp, lambda: page.table.rowCount() == 1)
        assert page.table.item(0, 0).text() == "PlumbCheck"
        assert page.table.item(0, 2).text() == "4242"
        assert page.count_badge.text() == "1 running"
        assert "listening on 5000" in page.log.toPlainText()
        assert page.stop_btn.isEnabled() and page.restart_btn.isEnabled()

        page.restart_btn.click()
        assert _pump(qapp, lambda: ("restart", "plumbcheck", "studio") in calls)

        assert _pump(qapp, lambda: page.restart_btn.isEnabled())
        page.stop_btn.click()
        assert _pump(qapp, lambda: ("stop", "plumbcheck", "studio") in calls)
        assert _pump(qapp, lambda: page.table.rowCount() == 0)
        assert not page.stop_btn.isEnabled()
        assert page.count_badge.text() == "0 running"
        assert not page.empty_label.isHidden()
    finally:
        win.close()


def _status(app_id, name, installed, current, latest, state, available=False):
    rel = updater.ReleaseInfo(f"stepan4002/{app_id}", f"v{latest}", latest, f"https://github.com/stepan4002/{app_id}/releases/tag/v{latest}") if latest else None
    return updater.UpdateStatus(app_id, name, installed, current, latest, rel.url if rel else None, available, state, state, rel)


def test_updates_page_check_and_one_click_update(qapp, isolated_settings, temp_workspace, provider_store):
    applied = []
    sweep = [
        _status("plumbcenter", "PlumbCenter", True, "1.0.0", "1.1.0", "update", True),
        _status("plumbdoctor", "PlumbDoctor", True, "1.0.0", "1.0.0", "up-to-date"),
        _status("plumbgate", "PlumbGate", False, None, "1.0.0", "unknown"),
        _status("plumbscout", "PlumbScout", True, "0.1.0", None, "error"),
    ]
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        page = win.updates_page
        page._checker = lambda root: sweep
        page._apply = lambda app_id, root=None: applied.append(app_id) or {"ok": True, "action": "updated"}
        win.navigate("updates")                       # first visit triggers a check
        assert _pump(qapp, lambda: len(page._rows) == 4)
        assert page.summary_badge.text() == "1 update available"

        hub = page._rows["plumbcenter"]
        assert hub.action_btn.text() == "Download" and hub.action_btn.isEnabled()
        assert not page._rows["plumbdoctor"].action_btn.isEnabled()          # already current
        assert page._rows["plumbgate"].action_btn.text() == "Install"
        assert page._rows["plumbgate"].action_btn.isEnabled()                # missing app can be installed
        assert not page._rows["plumbscout"].notes_btn.isEnabled()            # no release url
        assert page._rows["plumbscout"].badge.text() == "Check failed"

        page._rows["plumbgate"].action_btn.click()
        assert _pump(qapp, lambda: applied == ["plumbgate"])
    finally:
        win.close()


def test_updates_page_reports_unreachable_github(qapp, isolated_settings, temp_workspace, provider_store):
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        page = win.updates_page
        page._checker = lambda root: [_status("plumbcenter", "PlumbCenter", True, "1.0.0", None, "error")]
        page.check()
        assert _pump(qapp, lambda: page.summary_badge.text() == "GitHub unreachable")
    finally:
        win.close()


def test_provider_health_card(qapp, isolated_settings, temp_workspace, provider_store):
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        page = win.providers_page
        entries = [HealthEntry("openai", "OpenAI", "ok", 120),
                   HealthEntry("openrouter", "OpenRouter", "ok", 80, "Connection ok", "$4.50 left of $10.00"),
                   HealthEntry("groq", "Groq", "fail", 9, "HTTP 401"),
                   HealthEntry("kilo", "Kilo", "skipped", 0, "Not enabled")]
        page.check_health(pinger=lambda store: entries)
        assert _pump(qapp, lambda: page.health_badge.text().startswith("2 ok"))
        assert page.health_badge.text() == "2 ok · 1 failing"
        text = page.health_detail.text()
        assert "OpenRouter: 80 ms" in text and "$4.50 left of $10.00" in text
        assert "HTTP 401" in text and "Kilo: Not enabled" in text
        assert page.health_btn.isEnabled()

        page.show_health([])
        assert page.health_badge.text() == "Nothing to ping"
    finally:
        win.close()
