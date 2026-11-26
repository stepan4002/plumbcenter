"""Application entrypoint for PlumbCenter native PySide6 desktop hub."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from .icons import make_brand_icon
from .mainwindow import MainWindow


def _ensure_offscreen_fonts() -> None:
    """Register system TTF fonts when running under Qt offscreen platform on Windows."""
    if os.name != "nt" or os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
        return
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if not fonts_dir.is_dir():
        return
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "consola.ttf"):
        p = fonts_dir / name
        if p.is_file():
            QFontDatabase.addApplicationFont(str(p))


def create_application(argv: Optional[Sequence[str]] = None) -> QApplication:
    """Create or reuse the QApplication with HiDPI and Plumbnote org metadata."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
    _ensure_offscreen_fonts()
    app.setOrganizationName("Plumbnote")
    app.setApplicationName("PlumbCenter")
    app.setApplicationDisplayName("PlumbCenter")
    app.setWindowIcon(make_brand_icon())
    return app


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Launch the PlumbCenter desktop hub."""
    args = list(argv) if argv is not None else list(sys.argv)
    smoke = "--smoke-test" in args
    app = create_application([a for a in args if a != "--smoke-test"])
    settings = QSettings("Plumbnote", "PlumbCenter")
    window = MainWindow(settings=settings)
    window.show()
    if smoke:  # launch check used by packaging/smoke_exe.ps1: show, then exit 0
        QTimer.singleShot(1500, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
