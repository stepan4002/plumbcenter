"""Process manager: every long-running app action the hub started, with stop/restart and a live log tail."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import runner
from ...registry import get_app
from ..tasks import run_in_background
from ..widgets.badge import Badge
from ..widgets.toast import ToastManager

COLUMNS = ("App", "Action", "PID", "Uptime", "URL")


def format_uptime(started_at: Optional[float], now: Optional[float] = None) -> str:
    if not started_at:
        return "-"
    secs = max(0, int((now if now is not None else time.time()) - float(started_at)))
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60:02d}s"
    return f"{secs // 3600}h {(secs % 3600) // 60:02d}m"


class ProcessesPage(QWidget):
    """Live table of running processes + selected process log tail (polled, never blocks the UI)."""

    POLL_MS = 1500
    TAIL_LINES = 300

    def __init__(self, workspace_root: Path, toast: ToastManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workspace_root = Path(workspace_root)
        self._toast = toast
        self._rows: List[Dict[str, Any]] = []
        self._in_flight = False
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("Processes", self)
        title.setProperty("role", "pageTitle")
        sub = QLabel("Apps you started from the hub. Stop, restart, and watch their output live.", self)
        sub.setProperty("role", "pageSubtitle")
        col.addWidget(title)
        col.addWidget(sub)
        header.addLayout(col, 1)
        self.count_badge = Badge("0 running", "neutral", parent=self)
        header.addWidget(self.count_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setAccessibleName("Running processes")
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(210)
        self.table.itemSelectionChanged.connect(self._on_selection)
        root.addWidget(self.table)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.stop_btn = QPushButton("Stop", self)
        self.stop_btn.setProperty("variant", "danger")
        self.restart_btn = QPushButton("Restart", self)
        self.open_btn = QPushButton("Open", self)
        self.stop_btn.clicked.connect(lambda: self._act("stop"))
        self.restart_btn.clicked.connect(lambda: self._act("restart"))
        self.open_btn.clicked.connect(self._open)
        for b in (self.stop_btn, self.restart_btn, self.open_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            bar.addWidget(b)
        bar.addStretch(1)
        self.empty_label = QLabel("Nothing is running. Start an app from the Apps page.", self)
        self.empty_label.setProperty("role", "muted")
        bar.addWidget(self.empty_label)
        root.addLayout(bar)

        self.log_title = QLabel("Log", self)
        self.log_title.setProperty("role", "sectionTitle")
        root.addWidget(self.log_title)
        self.log = QPlainTextEdit(self)
        self.log.setObjectName("logOutput")
        self.log.setAccessibleName("Selected process log")
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setPlaceholderText("Select a process to tail its log.")
        root.addWidget(self.log, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self.refresh)
        self._sync_buttons()

    # -- lifecycle -----------------------------------------------------
    def set_workspace_root(self, new_root: Path) -> None:
        self._workspace_root = Path(new_root)

    def on_activated(self) -> None:
        self.refresh()
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    # -- data ----------------------------------------------------------
    def selected(self) -> Optional[Dict[str, Any]]:
        row = self.table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def refresh(self) -> None:
        if self._in_flight:
            return
        self._in_flight = True
        run_in_background(
            runner.status,
            on_success=self._apply_rows,
            on_error=lambda msg: self._toast.error(f"Could not read processes: {msg}"),
            on_done=self._refresh_done,
        )

    def _refresh_done(self) -> None:
        self._in_flight = False

    def _apply_rows(self, rows: List[Dict[str, Any]]) -> None:
        prev = self.selected()
        prev_key = (prev["app"], prev["action"]) if prev else None
        self._rows = list(rows)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        now = time.time()
        new_row = -1
        for i, r in enumerate(self._rows):
            spec = get_app(r["app"])
            cells = (spec.name if spec else r["app"], r["action"], str(r.get("pid", "")),
                     format_uptime(r.get("started_at"), now), r.get("url") or "-")
            for c, text in enumerate(cells):
                self.table.setItem(i, c, QTableWidgetItem(text))
            if prev_key == (r["app"], r["action"]):
                new_row = i
        if new_row < 0 and self._rows:
            new_row = 0
        if new_row >= 0:
            self.table.selectRow(new_row)
        self.table.blockSignals(False)
        self.count_badge.set_badge(f"{len(self._rows)} running", "success" if self._rows else "neutral")
        self.empty_label.setVisible(not self._rows)
        self._sync_buttons()
        self._update_log()

    def _on_selection(self) -> None:
        self._sync_buttons()
        self._update_log()

    def _update_log(self) -> None:
        sel = self.selected()
        if sel is None:
            self.log_title.setText("Log")
            self.log.clear()
            return
        self.log_title.setText(f"Log: {sel['app']} · {sel['action']}")
        text = runner.tail_log(sel["app"], sel["action"], lines=self.TAIL_LINES)
        if text == self.log.toPlainText():
            return
        sb = self.log.verticalScrollBar()
        follow = sb.value() >= sb.maximum() - 4
        self.log.setPlainText(text)
        if follow:
            sb.setValue(sb.maximum())

    def _sync_buttons(self) -> None:
        has = self.selected() is not None and not self._busy
        self.stop_btn.setEnabled(has)
        self.restart_btn.setEnabled(has)
        self.open_btn.setEnabled(has)

    # -- actions -------------------------------------------------------
    def _act(self, what: str) -> None:
        sel = self.selected()
        if sel is None or self._busy:
            return
        app_id, action = sel["app"], sel["action"]
        self._busy = True
        self._sync_buttons()
        if what == "stop":
            fn: Callable[..., Any] = runner.stop
            kwargs: Dict[str, Any] = {}
            verb = "Stopped"
        else:
            fn, kwargs, verb = runner.restart, {"root": self._workspace_root}, "Restarted"

        def _ok(_res: Any) -> None:
            self._toast.success(f"{verb} {app_id} ({action})")
            self.refresh()

        def _done() -> None:
            self._busy = False
            self._sync_buttons()

        run_in_background(fn, app_id, action, on_success=_ok,
                          on_error=lambda msg: self._toast.error(f"{what.title()} failed: {msg}"),
                          on_done=_done, **kwargs)

    def _open(self) -> None:
        sel = self.selected()
        if sel is None:
            return

        def _ok(res: Dict[str, Any]) -> None:
            if res.get("opened"):
                self._toast.info(f"Opened {res.get('opened')}")
            else:
                self._toast.warning("No launch URL or folder available yet.")

        run_in_background(runner.open_app, sel["app"], root=self._workspace_root, on_success=_ok,
                          on_error=lambda msg: self._toast.error(f"Open failed: {msg}"))
