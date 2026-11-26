"""Semantic pill badge widget styled via theme QSS tokens."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class Badge(QLabel):
    """Compact pill badge supporting semantic tones: success, warning, danger, info, neutral."""

    def __init__(
        self,
        text: str = "",
        tone: str = "neutral",
        tooltip: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("badge", True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.set_tone(tone)
        if tooltip:
            self.setToolTip(tooltip)

    def set_tone(self, tone: str) -> None:
        self.setProperty("badgeTone", tone)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_badge(self, text: str, tone: str, tooltip: Optional[str] = None) -> None:
        self.setText(text)
        self.set_tone(tone)
        if tooltip is not None:
            self.setToolTip(tooltip)
