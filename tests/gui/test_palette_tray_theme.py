"""Command palette, geometry persistence, shared theme sync, tray menu, diagnostics export (offscreen)."""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThreadPool
from PySide6.QtTest import QTest

from plumbcenter import shared_settings
from plumbcenter.gui.mainwindow import MainWindow, NAV_ITEMS
from plumbcenter.gui.tray import TrayController
from plumbcenter.gui.widgets.palette import Command, CommandPalette, filter_commands, fuzzy_score


def _pump(app, cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        QThreadPool.globalInstance().waitForDone(20)
        if cond():
            return True
        time.sleep(0.02)
    app.processEvents()
    return cond()


def _window(settings, workspace, store):
    settings.setValue("workspace/root", str(workspace))
    return MainWindow(settings=settings, provider_store=store)


# ---- palette ---------------------------------------------------------------

def test_fuzzy_score_prefers_contiguous_and_rejects_non_subsequence():
    assert fuzzy_score("", "anything") == 0
    assert fuzzy_score("proc", "Go to Processes") < fuzzy_score("gtp", "Go to Processes")
    assert fuzzy_score("gtp", "Go to Processes") is not None      # scattered subsequence still matches
    assert fuzzy_score("zzz", "Go to Processes") is None


def test_filter_commands_ranks_and_is_stable():
    hits = []
    cmds = [Command("Refresh apps", lambda: None, "Apps"), Command("Go to Apps", lambda: None, "Navigate"),
            Command("Quit", lambda: None)]
    assert [c.title for c in filter_commands(cmds, "apps")] == ["Go to Apps", "Refresh apps"]   # earlier hit first
    assert [c.title for c in filter_commands(cmds, "")] == ["Refresh apps", "Go to Apps", "Quit"]
    kw = [Command("Zeta", lambda: None, "Theme", "switch mode"), Command("Switch tabs", lambda: None)]
    assert [c.title for c in filter_commands(kw, "switch")] == ["Switch tabs", "Zeta"]     # title beats keyword
    assert filter_commands(cmds, "qqq") == [] and not hits


def test_palette_filters_navigates_and_runs_on_enter(qapp):
    ran = []
    cmds = [Command("Alpha", lambda: ran.append("a")), Command("Beta", lambda: ran.append("b")),
            Command("Gamma", lambda: ran.append("g"))]
    dlg = CommandPalette(cmds)
    dlg.show()
    assert dlg.visible_titles() == ["Alpha", "Beta", "Gamma"]
    QTest.keyClicks(dlg.input, "gam")
    assert dlg.visible_titles() == ["Gamma"]
    dlg.input.clear()
    QTest.keyClick(dlg.input, Qt.Key.Key_Down)
    assert dlg.list.currentRow() == 1
    QTest.keyClick(dlg.input, Qt.Key.Key_Up)
    QTest.keyClick(dlg.input, Qt.Key.Key_Up)             # wraps to last
    assert dlg.list.currentRow() == 2
    QTest.keyClick(dlg, Qt.Key.Key_Return)
    assert ran == ["g"] and not dlg.isVisible()


def test_palette_empty_result_enter_is_a_noop(qapp):
    ran = []
    dlg = CommandPalette([Command("Alpha", lambda: ran.append(1))])
    dlg.show()
    QTest.keyClicks(dlg.input, "zzz")
    QTest.keyClick(dlg, Qt.Key.Key_Return)
    assert ran == [] and dlg.isVisible()


def test_ctrl_k_opens_palette_with_every_page_and_runs_a_command(qapp, isolated_settings, temp_workspace, provider_store):
    win = _window(isolated_settings, temp_workspace, provider_store)
    win.show()
    try:
        dlg = win.open_palette()
        titles = dlg.visible_titles()
        for _k, label, _t in NAV_ITEMS:
            assert f"Go to {label}" in titles
        assert {"Toggle dark / light theme", "Check for updates", "Export diagnostics bundle...", "Quit PlumbCenter"} <= set(titles)
        QTest.keyClicks(dlg.input, "go to proc")
        assert dlg.visible_titles()[0] == "Go to Processes"
        QTest.keyClick(dlg, Qt.Key.Key_Return)
        assert win.stack.currentWidget() is win.processes_page
        # the real shortcut also builds a palette
        win.open_palette().close()
    finally:
        win.close()


def test_palette_lists_launch_commands_only_for_installed_apps(qapp, isolated_settings, temp_workspace, provider_store):
    win = _window(isolated_settings, temp_workspace, provider_store)
    win.show()
    try:
        assert _pump(qapp, lambda: "plumbcheck" in win.apps_page._statuses)
        titles = [c.title for c in win.build_commands()]
        assert "Start PlumbCheck: Start Studio" in titles and "Open PlumbCheck folder" in titles
        assert not any("PlumbCode" in t for t in titles)          # not installed in the temp workspace
    finally:
        win.close()


# ---- geometry --------------------------------------------------------------

def test_window_and_splitter_geometry_persist_across_windows(qapp, tmp_path, temp_workspace, provider_store):
    ini = str(tmp_path / "geo.ini")
    s1 = QSettings(ini, QSettings.Format.IniFormat)
    w1 = _window(s1, temp_workspace, provider_store)
    w1.show()
    w1.resize(900, 650)      # differs from the 1180x760 default; offscreen screen is only 800 wide
    w1.processes_page.splitter.setSizes([120, 480])
    w1.close()
    s1.sync()
    assert s1.value("window/geometry") and s1.value("window/splitter/processes")

    w2 = _window(QSettings(ini, QSettings.Format.IniFormat), temp_workspace, provider_store)
    w2.show()
    try:
        assert (w2.width(), w2.height()) == (900, 650)
        saved = s1.value("window/splitter/processes")
        assert bytes(w2.processes_page.splitter.saveState()) == bytes(saved)   # restored, not default
    finally:
        w2.close()


def test_corrupt_saved_geometry_is_ignored(qapp, isolated_settings, temp_workspace, provider_store):
    isolated_settings.setValue("window/geometry", b"garbage")
    isolated_settings.setValue("window/splitter/processes", b"garbage")
    win = _window(isolated_settings, temp_workspace, provider_store)
    win.show()
    try:
        assert win.width() > 0
    finally:
        win.close()


# ---- shared theme ----------------------------------------------------------

def test_theme_switch_writes_shared_settings_and_keeps_foreign_keys(qapp, isolated_settings, temp_workspace, provider_store):
    shared_settings.settings_path().parent.mkdir(parents=True, exist_ok=True)
    shared_settings.settings_path().write_text(json.dumps({"version": 1, "theme": "dark", "plumbdoctor": {"x": 1}}), encoding="utf-8")
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        assert win.current_theme == "dark"
        win.set_theme("light")
        data = json.loads(shared_settings.settings_path().read_text(encoding="utf-8"))
        assert data["theme"] == "light" and data["plumbdoctor"] == {"x": 1}
        win.toggle_theme()
        assert shared_settings.load_theme() == "dark"
    finally:
        win.close()


def test_shared_theme_wins_at_startup(qapp, isolated_settings, temp_workspace, provider_store):
    isolated_settings.setValue("ui/theme", "dark")
    shared_settings.save_theme("light")
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        assert win.current_theme == "light"
    finally:
        win.close()


def test_external_theme_change_is_adopted_live_without_rewriting(qapp, isolated_settings, temp_workspace, provider_store):
    shared_settings.save_theme("dark")
    win = _window(isolated_settings, temp_workspace, provider_store)
    win.show()
    seen = []
    win.theme_changed.connect(seen.append)
    try:
        before = qapp.styleSheet()
        time.sleep(0.01)
        shared_settings.save_theme("light")                    # another Plumbnote app flips the theme
        win.poll_shared_theme()
        assert win.current_theme == "light" and seen == ["light"]
        assert qapp.styleSheet() != before                     # stylesheet actually re-applied
        assert win.settings_page.sync_theme is not None
        mtime = shared_settings.mtime()
        win.poll_shared_theme()                                # no change -> no work, no rewrite
        assert shared_settings.mtime() == mtime and seen == ["light"]
        # the timer drives it too
        shared_settings.save_theme("dark")
        assert _pump(qapp, lambda: win.current_theme == "dark", timeout=5)
    finally:
        win.close()


def test_garbage_in_shared_file_does_not_change_theme(qapp, isolated_settings, temp_workspace, provider_store):
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        shared_settings.settings_path().write_text("{broken", encoding="utf-8")
        start = win.current_theme
        win.poll_shared_theme()
        assert win.current_theme == start
    finally:
        win.close()


# ---- tray ------------------------------------------------------------------

def test_tray_menu_quick_launch_and_actions(qapp, isolated_settings, temp_workspace, provider_store, monkeypatch):
    win = _window(isolated_settings, temp_workspace, provider_store)
    win.show()
    try:
        assert _pump(qapp, lambda: "plumbcheck" in win.apps_page._statuses)
        tray = TrayController(win)
        assert ("plumbcheck", "studio", "PlumbCheck: Start Studio") in tray.launch_entries()
        assert all(a != "plumbdoctor" for a, _n, _l in tray.launch_entries())       # demo is not long-running
        labels = [a.text() for a in tray.menu.actions() if a.text()]
        assert labels[0] == "Show / hide PlumbCenter" and labels[-1] == "Quit"
        assert "Quick launch" in labels and "Processes" in labels and "Updates" in labels

        started = []
        monkeypatch.setattr(win.apps_page, "_on_start_action", lambda a, n: started.append((a, n)))
        tray.rebuild()
        sub = next(a for a in tray.menu.actions() if a.text() == "Quick launch").menu()
        sub.actions()[0].trigger()
        assert started == [("plumbcheck", "studio")]

        next(a for a in tray.menu.actions() if a.text() == "Processes").trigger()
        assert win.stack.currentWidget() is win.processes_page
        next(a for a in tray.menu.actions() if a.text() == "Show / hide PlumbCenter").trigger()
        assert not win.isVisible()
        win.toggle_visibility()
        assert win.isVisible()
    finally:
        win.close()


def test_tray_menu_with_nothing_installed(qapp, isolated_settings, tmp_path, provider_store):
    empty = tmp_path / "empty"
    empty.mkdir()
    win = _window(isolated_settings, empty, provider_store)
    try:
        tray = TrayController(win)
        assert tray.launch_entries() == []
        disabled = [a for a in tray.menu.actions() if a.text().startswith("Quick launch")]
        assert disabled and not disabled[0].isEnabled()
    finally:
        win.close()


def test_enable_tray_is_safe_without_a_system_tray(qapp, isolated_settings, temp_workspace, provider_store):
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        result = win.enable_tray()
        assert result == TrayController.available()
        win.close()                                              # detaches cleanly either way
    finally:
        win.close()


# ---- diagnostics export ----------------------------------------------------

def test_diagnostics_page_exports_redacted_zip(qapp, isolated_settings, temp_workspace, provider_store, tmp_path):
    key = "sk-gui-SENTINEL-0123456789abcdef"
    provider_store.configure("openai", api_key=key, enabled=True)
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        page = win.diagnostics_page
        out = tmp_path / "bundle.zip"
        assert page.export_btn.accessibleName() == "Export diagnostics bundle"
        page.export_bundle(str(out))
        assert _pump(qapp, lambda: out.exists() and page.export_btn.isEnabled())
        assert page.last_export["format"] == "zip"
        with zipfile.ZipFile(out) as zf:
            assert all(key not in zf.read(n).decode("utf-8") for n in zf.namelist())
            report = json.loads(zf.read("report.json"))
        assert next(p for p in report["providers"] if p["id"] == "openai")["has_key"] is True
    finally:
        win.close()


def test_diagnostics_export_failure_is_reported_not_raised(qapp, isolated_settings, temp_workspace, provider_store, tmp_path):
    win = _window(isolated_settings, temp_workspace, provider_store)
    try:
        page = win.diagnostics_page
        blocker = tmp_path / "file"
        blocker.write_text("x")
        page.export_bundle(str(blocker / "sub" / "b.zip"))      # parent is a file -> OSError in worker
        assert _pump(qapp, lambda: page.export_btn.isEnabled())
        assert not hasattr(page, "last_export")
    finally:
        win.close()
