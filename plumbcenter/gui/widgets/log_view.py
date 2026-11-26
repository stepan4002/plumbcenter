"""Live log viewer dialog that polls runner.tail_log every 500 ms."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import runner
from .badge import Badge


class LogViewerDialog(QDialog):
    """Non-blocking live log viewer for a running or completed app action."""

    POLL_INTERVAL_MS = 500

    def __init__(
        self,
        app_id: str,
        app_name: str,
        action_name: str,
        initial_text: str = "",
        is_live: bool = True,
        on_stop: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.app_id = app_id
        self.action_name = action_name
        self._on_stop = on_stop
        self._last_text = ""

        self.setWindowTitle(f"{app_name} — {action_name} logs")
        self.resize(780, 480)
        self.setMinimumSize(540, 320)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel(f"{app_name} · {action_name}", self)
        title.setProperty("role", "sectionTitle")
        header.addWidget(title)

        self.status_badge = Badge("Live" if is_live else "Output", "success" if is_live else "info", parent=self)
        header.addWidget(self.status_badge)
        header.addStretch(1)

        self.autoscroll_cb = QCheckBox("Auto-scroll", self)
        self.autoscroll_cb.setChecked(True)
        header.addWidget(self.autoscroll_cb)

        copy_btn = QPushButton("Copy", self)
        copy_btn.setProperty("size", "sm")
        copy_btn.setToolTip("Copy log output to clipboard")
        copy_btn.clicked.connect(self._copy_logs)
        header.addWidget(copy_btn)

        self.stop_btn = QPushButton("Stop process", self)
        self.stop_btn.setProperty("variant", "danger")
        self.stop_btn.setProperty("size", "sm")
        self.stop_btn.setVisible(is_live and on_stop is not None)
        self.stop_btn.clicked.connect(self._handle_stop)
        header.addWidget(self.stop_btn)

        root.addLayout(header)

        # Log output
        self.output = QPlainTextEdit(self)
        self.output.setObjectName("logOutput")
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setPlaceholderText("Waiting for output...")
        root.addWidget(self.output, 1)

        # Footer
        footer = QHBoxLayout()
        self.info_label = QLabel("Polling every 500 ms" if is_live else "Static command output", self)
        self.info_label.setProperty("role", "muted")
        footer.addWidget(self.info_label)
        footer.addStretch(1)

        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        if initial_text:
            self.set_log_text(initial_text)

        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh_logs)
        if is_live:
            self.refresh_logs()
            self._timer.start()

    def set_log_text(self, text: str) -> None:
        if text == self._last_text:
            return
        self._last_text = text
        sb = self.output.verticalScrollBar()
        was_at_bottom = sb.value() >= sb.maximum() - 4
        self.output.setPlainText(text)
        if self.autoscroll_cb.isChecked() and was_at_bottom:
            sb.setValue(sb.maximum())

    def refresh_logs(self) -> None:
        text = runner.tail_log(self.app_id, self.action_name, lines=400)
        if text:
            self.set_log_text(text)
        running = any(
            p.get("app") == self.app_id and p.get("action") == self.action_name
            for p in runner.status(self.app_id)
        )
        if running:
            self.status_badge.set_badge("Running", "success")
            self.stop_btn.setEnabled(True)
        else:
            self.status_badge.set_badge("Stopped", "neutral")
            self.stop_btn.setEnabled(False)

    def _copy_logs(self) -> None:
        QApplication.clipboard().setText(self.output.toPlainText())
        self.info_label.setText("Copied to clipboard")

    def _handle_stop(self) -> None:
        if self._on_stop:
            self._on_stop()
            self.refresh_logs()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)
