"""Programmatic vector icons and app monogram tiles rendered with QPainter.

Zero external binary dependencies at runtime; scales cleanly on HiDPI displays.
"""

from __future__ import annotations

from typing import Dict, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from .theme import BRAND_ACCENT

# Distinct Creative-Cloud-style 2-letter monograms + accent palettes per app
APP_VISUALS: Dict[str, Tuple[str, str, str]] = {
    "plumbcheck": ("Pc", "#0ea5e9", "#79ccf3"),
    "plumbcode": ("Cd", "#6366f1", "#a5b4fc"),
    "plumbdoctor": ("Dr", "#10b981", "#6ee7b7"),
    "plumbgate": ("Gt", "#f59e0b", "#fcd34d"),
    "plumbscout": ("Sc", "#ec4899", "#f9a8d4"),
    "plumbstudio": ("St", "#8b5cf6", "#c4b5fd"),
    "plumbbridge": ("Br", "#14b8a6", "#5eead4"),
}


def make_brand_pixmap(size: int = 40) -> QPixmap:
    """Render the PlumbCenter brand icon (rounded tile + geometric plumb-bob)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    rect = QRectF(1, 1, size - 2, size - 2)
    radius = size * 0.24
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#0d2233"))
    grad.setColorAt(1.0, QColor("#153a54"))
    p.setBrush(grad)
    p.setPen(QPen(QColor(BRAND_ACCENT), max(1.2, size * 0.045)))
    p.drawRoundedRect(rect, radius, radius)

    # Plumb-bob diamond + vertical line
    cx = size / 2.0
    pen = QPen(QColor(BRAND_ACCENT), max(1.5, size * 0.065), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(cx, size * 0.18), QPointF(cx, size * 0.36))

    path = QPainterPath()
    path.moveTo(cx, size * 0.34)
    path.lineTo(size * 0.72, size * 0.56)
    path.lineTo(cx, size * 0.82)
    path.lineTo(size * 0.28, size * 0.56)
    path.closeSubpath()
    p.setBrush(QColor(BRAND_ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(path)

    # Inner highlight dot
    p.setBrush(QColor("#0d2233"))
    p.drawEllipse(QPointF(cx, size * 0.56), size * 0.075, size * 0.075)
    p.end()
    return pm


def make_brand_icon() -> QIcon:
    """Return a multi-resolution QIcon for the application window."""
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_brand_pixmap(sz))
    return icon


def make_app_tile(app_id: str, size: int = 44) -> QPixmap:
    """Render a Creative-Cloud-style rounded monogram tile for a Plumbnote app."""
    code, c1, c2 = APP_VISUALS.get(app_id.lower(), (app_id[:2].title(), "#3b82f6", BRAND_ACCENT))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    rect = QRectF(1, 1, size - 2, size - 2)
    radius = size * 0.24
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor(c1))
    grad.setColorAt(1.0, QColor(c2))

    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(rect, radius, radius)

    # Subtle dark inner overlay for crisp contrast
    p.setBrush(QColor(10, 15, 25, 115))
    p.drawRoundedRect(QRectF(3, 3, size - 6, size - 6), radius * 0.8, radius * 0.8)

    font = QFont("Segoe UI", max(10, int(size * 0.34)), QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(QColor("#ffffff"))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, code)
    p.end()
    return pm


def make_nav_icon(kind: str, color: str, size: int = 18) -> QIcon:
    """Render crisp geometric sidebar navigation icons."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    if kind == "apps":
        # 2x2 grid
        g = s * 0.16
        w = s * 0.28
        for r in range(2):
            for c in range(2):
                x = g + c * (w + s * 0.12)
                y = g + r * (w + s * 0.12)
                p.drawRoundedRect(QRectF(x, y, w, w), 2.0, 2.0)
    elif kind == "providers":
        # Spark / key-plug node
        p.drawEllipse(QPointF(s * 0.35, s * 0.5), s * 0.18, s * 0.18)
        p.drawLine(QPointF(s * 0.53, s * 0.5), QPointF(s * 0.86, s * 0.5))
        p.drawLine(QPointF(s * 0.72, s * 0.5), QPointF(s * 0.72, s * 0.68))
        p.drawLine(QPointF(s * 0.84, s * 0.5), QPointF(s * 0.84, s * 0.65))
    elif kind == "settings":
        # Sliders
        for y_frac, knob_x in ((0.28, 0.36), (0.50, 0.68), (0.72, 0.44)):
            y = s * y_frac
            p.drawLine(QPointF(s * 0.16, y), QPointF(s * 0.84, y))
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(s * knob_x, y), s * 0.08, s * 0.08)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif kind == "diagnostics":
        # Pulse waveform
        path = QPainterPath()
        path.moveTo(s * 0.12, s * 0.54)
        path.lineTo(s * 0.30, s * 0.54)
        path.lineTo(s * 0.42, s * 0.22)
        path.lineTo(s * 0.58, s * 0.78)
        path.lineTo(s * 0.70, s * 0.46)
        path.lineTo(s * 0.88, s * 0.46)
        p.drawPath(path)
    elif kind == "theme_dark":
        # Crescent moon
        p.drawArc(QRectF(s * 0.2, s * 0.2, s * 0.6, s * 0.6), 40 * 16, 260 * 16)
    elif kind == "theme_light":
        # Sun
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.18, s * 0.18)
        for dx, dy in ((0, -0.34), (0, 0.34), (-0.34, 0), (0.34, 0)):
            p.drawLine(
                QPointF(s * (0.5 + dx * 0.72), s * (0.5 + dy * 0.72)),
                QPointF(s * (0.5 + dx), s * (0.5 + dy)),
            )
    else:
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.3, s * 0.3)

    p.end()
    return QIcon(pm)
