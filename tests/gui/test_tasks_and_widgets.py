"""Tests for non-blocking background tasks, badges, toasts, and log viewer."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from plumbcenter.gui.tasks import run_in_background
from plumbcenter.gui.widgets.badge import Badge
from plumbcenter.gui.widgets.log_view import LogViewerDialog
from plumbcenter.gui.widgets.toast import ToastManager


def test_background_task_does_not_block_event_loop(qapp):
    ticks = []
    results = []

    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()

    def slow_work():
        time.sleep(0.22)
        return "done-async"

    run_in_background(slow_work, on_success=lambda r: results.append(r))

    # Event loop stays responsive while slow_work runs on QThreadPool
    deadline = time.monotonic() + 3.0
    while not results and time.monotonic() < deadline:
        QTest.qWait(25)

    timer.stop()
    assert results == ["done-async"]
    assert len(ticks) >= 3, f"Expected UI timer to tick during background task, got {len(ticks)}"


def test_badge_and_toast_widgets(qapp):
    host = QWidget()
    host.resize(640, 480)
    host.show()

    try:
        badge = Badge("Healthy", "success", parent=host)
        assert badge.text() == "Healthy"
        assert badge.property("badgeTone") == "success"
        badge.set_badge("Error", "danger", "Something broke")
        assert badge.text() == "Error"
        assert badge.property("badgeTone") == "danger"
        assert badge.toolTip() == "Something broke"

        toasts = ToastManager(host)
        item = toasts.success("Saved!", duration_ms=0)
        assert item.isVisible()
        assert len(toasts._toasts) == 1
        item.dismiss()
        QTest.qWait(20)
        assert len(toasts._toasts) == 0
    finally:
        host.close()


def test_log_viewer_displays_initial_and_live_logs(qapp, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PLUMBCENTER_STATE", str(tmp_path))
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True)
    log_file = logs_dir / "plumbcheck-studio.log"
    log_file.write_text("line 1\nline 2\n", encoding="utf-8")

    dlg = LogViewerDialog(
        app_id="plumbcheck",
        app_name="PlumbCheck",
        action_name="studio",
        is_live=True,
    )
    dlg.show()
    QTest.qWait(50)

    try:
        assert "line 1" in dlg.output.toPlainText()
        assert "line 2" in dlg.output.toPlainText()
        log_file.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
        dlg.refresh_logs()
        assert "line 3" in dlg.output.toPlainText()
    finally:
        dlg.close()
