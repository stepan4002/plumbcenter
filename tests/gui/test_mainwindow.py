"""Tests for MainWindow construction, sidebar navigation, theme persistence, and settings round-trip."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from plumbcenter.gui.mainwindow import MainWindow, NAV_ITEMS
from tests.gui.conftest import wait_for_background


def test_mainwindow_builds_and_navigates(qapp, isolated_settings, temp_workspace, provider_store):
    isolated_settings.setValue("workspace/root", str(temp_workspace))
    win = MainWindow(settings=isolated_settings, provider_store=provider_store)
    win.show()
    wait_for_background()

    try:
        assert win.windowTitle().startswith("PlumbCenter")
        assert len(win.nav_buttons) == len(NAV_ITEMS) == 6
        assert win.stack.currentWidget() is win.apps_page

        for key, _label, _tip in NAV_ITEMS:
            win.nav_buttons[key].click()
            wait_for_background(40)
            assert win.stack.currentWidget() is win._pages[key]
            assert win.nav_buttons[key].property("active") is True
    finally:
        win.close()


def test_theme_toggle_persists_across_restarts(qapp, tmp_path: Path, temp_workspace, provider_store):
    ini = tmp_path / "theme_persist.ini"
    s1 = QSettings(str(ini), QSettings.Format.IniFormat)
    s1.setValue("workspace/root", str(temp_workspace))

    win1 = MainWindow(settings=s1, provider_store=provider_store)
    assert win1.current_theme == "dark"
    win1.toggle_theme()
    assert win1.current_theme == "light"
    win1.close()

    s2 = QSettings(str(ini), QSettings.Format.IniFormat)
    win2 = MainWindow(settings=s2, provider_store=provider_store)
    try:
        assert win2.current_theme == "light"
        win2.set_theme("dark")
        assert win2.current_theme == "dark"
    finally:
        win2.close()


def test_settings_workspace_round_trip(qapp, tmp_path: Path, temp_workspace, provider_store):
    ini = tmp_path / "settings_rt.ini"
    settings = QSettings(str(ini), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings, provider_store=provider_store)
    win.show()
    wait_for_background()

    try:
        win.navigate("settings")
        win.settings_page.workspace_input.setText(str(temp_workspace))
        win.settings_page._apply_workspace_input()
        wait_for_background()

        assert win.workspace_root == temp_workspace.resolve()
        assert str(temp_workspace.resolve()) in win.status_workspace_label.text()

        # Verify persisted in QSettings
        reloaded = QSettings(str(ini), QSettings.Format.IniFormat)
        assert Path(str(reloaded.value("workspace/root"))).resolve() == temp_workspace.resolve()
    finally:
        win.close()
