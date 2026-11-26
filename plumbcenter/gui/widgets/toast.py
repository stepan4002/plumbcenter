"""Floating non-blocking toast notifications for PlumbCenter."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class _ToastItem(QFrame):
    def __init__(
        self,
        message: str,
        tone: str = "info",
        duration_ms: int = 4000,
        parent: Optional[QWidget] = None,
        on_closed=None,
    ) -> None:
        super().__init__(parent)
        self._on_closed = on_closed
        self.setProperty("toast", True)
        self.setProperty("toastTone", tone)
        self.setMinimumWidth(280)
        self.setMaximumWidth(440)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(10)

        self.label = QLabel(message, self)
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)

        close_btn = QPushButton("×", self)
        close_btn.setProperty("variant", "ghost")
        close_btn.setFixedSize(24, 24)
        close_btn.setToolTip("Dismiss notification")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.dismiss)
        layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        if duration_ms > 0:
            self._timer.start(duration_ms)

    def dismiss(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self.hide()
        if self._on_closed:
            self._on_closed(self)
        self.deleteLater()


class ToastManager(QObject):
    """Stacks transient toast cards in the bottom-right corner of a host widget."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._toasts: List[_ToastItem] = []
        self._host.installEventFilter(self)

    def show_toast(self, message: str, tone: str = "info", duration_ms: int = 4200) -> _ToastItem:
        toast = _ToastItem(
            message=message,
            tone=tone,
            duration_ms=duration_ms,
            parent=self._host,
            on_closed=self._remove,
        )
        toast.adjustSize()
        toast.show()
        toast.raise_()
        self._toasts.append(toast)
        self._reposition()
        return toast

    def info(self, message: str, duration_ms: int = 3800) -> _ToastItem:
        return self.show_toast(message, "info", duration_ms)

    def success(self, message: str, duration_ms: int = 3800) -> _ToastItem:
        return self.show_toast(message, "success", duration_ms)

    def warning(self, message: str, duration_ms: int = 5000) -> _ToastItem:
        return self.show_toast(message, "warning", duration_ms)

    def error(self, message: str, duration_ms: int = 6000) -> _ToastItem:
        return self.show_toast(message, "danger", duration_ms)

    def _remove(self, toast: _ToastItem) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reposition()

    def _reposition(self) -> None:
        margin_x = 20
        margin_y = 44
        gap = 8
        y = self._host.height() - margin_y
        for toast in reversed(self._toasts):
            toast.adjustSize()
            w = min(max(toast.sizeHint().width(), 280), 440)
            h = toast.sizeHint().height()
            x = max(12, self._host.width() - w - margin_x)
            y -= h
            toast.setGeometry(x, max(12, y), w, h)
            toast.raise_()
            y -= gap

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._host and event.type() == QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(watched, event)
