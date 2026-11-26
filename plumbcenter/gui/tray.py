"""System tray quick-launch menu. The menu is built independently of the tray icon so it is testable headless."""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from ..registry import REGISTRY
from .icons import make_brand_icon


class TrayController:
    """Tray icon with: Show/Hide, per-app quick launch (installed apps only), Quit.

    `window` must offer: show_and_raise(), toggle_visibility(), navigate(key), apps_page, quit_app().
    """

    def __init__(self, window: Any) -> None:
        self.window = window
        self.menu = QMenu()
        self.tray: Optional[QSystemTrayIcon] = None
        self.menu.aboutToShow.connect(self.rebuild)
        self.rebuild()

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def attach(self) -> bool:
        """Create and show the tray icon. False when the platform has no tray."""
        if not self.available():
            return False
        self.tray = QSystemTrayIcon(make_brand_icon(), self.window)
        self.tray.setToolTip("PlumbCenter")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()
        return True

    def detach(self) -> None:
        if self.tray is not None:
            self.tray.hide()
            self.tray.deleteLater()
            self.tray = None

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.window.toggle_visibility()

    def launch_entries(self) -> List[Tuple[str, str, str]]:
        """(app_id, action_name, label) for each installed app's long-running action."""
        statuses = getattr(self.window.apps_page, "_statuses", {}) or {}
        out = []
        for spec in REGISTRY:
            st = statuses.get(spec.id)
            if not (st and st.installed):
                continue
            for act in spec.actions:
                if act.kind == "serve":
                    out.append((spec.id, act.name, f"{spec.name}: {act.label}"))
        return out

    def rebuild(self) -> None:
        m = self.menu
        m.clear()
        w = self.window
        self._add(m, "Show / hide PlumbCenter", w.toggle_visibility)
        m.addSeparator()
        entries = self.launch_entries()
        if entries:
            sub = m.addMenu("Quick launch")
            for app_id, action, label in entries:
                self._add(sub, label, lambda a=app_id, n=action: w.apps_page._on_start_action(a, n))
        else:
            empty = m.addAction("Quick launch (no installed apps)")
            empty.setEnabled(False)
        self._add(m, "Processes", lambda: (w.show_and_raise(), w.navigate("processes")))
        self._add(m, "Updates", lambda: (w.show_and_raise(), w.navigate("updates")))
        m.addSeparator()
        self._add(m, "Quit", w.quit_app)

    @staticmethod
    def _add(menu: QMenu, text: str, fn: Callable[[], Any]) -> QAction:
        act = menu.addAction(text)
        act.triggered.connect(lambda _checked=False: fn())
        return act
