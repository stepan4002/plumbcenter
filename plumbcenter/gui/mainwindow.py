"""Main window for PlumbCenter: Creative-Cloud-style left sidebar + stacked pages."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QByteArray, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, shared_settings
from ..discovery import hub_root
from ..registry import REGISTRY
from .icons import make_brand_icon, make_brand_pixmap, make_nav_icon
from .pages.apps import AppsPage
from .pages.diagnostics import DiagnosticsPage
from .pages.processes import ProcessesPage
from .pages.providers import ProvidersPage
from .pages.settings import SettingsPage
from .pages.updates import UpdatesPage
from .tray import TrayController
from .theme import build_stylesheet, get_tokens
from .widgets.palette import Command, CommandPalette
from .widgets.toast import ToastManager


NAV_ITEMS: List[Tuple[str, str, str]] = [
    ("apps", "Apps", "Manage, install, and launch Plumbnote apps (Ctrl+1)"),
    ("processes", "Processes", "Stop, restart, and tail running apps (Ctrl+2)"),
    ("providers", "Providers", "Configure AI providers and per-app defaults (Ctrl+3)"),
    ("updates", "Updates", "Check GitHub Releases and update apps (Ctrl+4)"),
    ("settings", "Settings", "Workspace root, theme, and hub updates (Ctrl+5)"),
    ("diagnostics", "Diagnostics", "Environment checks and app health report (Ctrl+6)"),
]


class MainWindow(QMainWindow):
    """Creative-Cloud-style desktop hub main window."""

    THEME_POLL_MS = 1000

    theme_changed = Signal(str)
    workspace_changed = Signal(str)

    def __init__(
        self,
        settings: Optional[QSettings] = None,
        provider_store=None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings or QSettings("Plumbnote", "PlumbCenter")
        self._theme: str = str(self.settings.value("ui/theme", "dark") or "dark").lower()
        if self._theme not in ("dark", "light"):
            self._theme = "dark"
        shared_theme = shared_settings.load_theme()      # the shared file wins so sibling apps stay in sync
        if shared_theme:
            self._theme = shared_theme
        self._tray: Optional[TrayController] = None

        saved_root = self.settings.value("workspace/root", "")
        self._workspace_root: Path = Path(str(saved_root)).resolve() if saved_root else hub_root()

        self.setWindowTitle("PlumbCenter — Plumbnote Desktop Hub")
        self.setWindowIcon(make_brand_icon())
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)

        central = QWidget(self)
        central.setObjectName("centralRoot")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # === Left Sidebar ===
        self.sidebar = QFrame(central)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(14, 18, 14, 14)
        sb_layout.setSpacing(8)

        # Brand block
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        logo_lbl = QLabel(self.sidebar)
        logo_lbl.setPixmap(make_brand_pixmap(36))
        logo_lbl.setFixedSize(36, 36)
        brand_row.addWidget(logo_lbl)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        title_lbl = QLabel("PlumbCenter", self.sidebar)
        title_lbl.setObjectName("brandTitle")
        sub_lbl = QLabel("Plumbnote Hub", self.sidebar)
        sub_lbl.setObjectName("brandSubtitle")
        brand_text.addWidget(title_lbl)
        brand_text.addWidget(sub_lbl)
        brand_row.addLayout(brand_text, 1)
        sb_layout.addLayout(brand_row)

        divider = QFrame(self.sidebar)
        divider.setObjectName("sidebarDivider")
        sb_layout.addSpacing(6)
        sb_layout.addWidget(divider)
        sb_layout.addSpacing(6)

        # Nav buttons
        self.nav_buttons: Dict[str, QPushButton] = {}
        for idx, (key, label, tip) in enumerate(NAV_ITEMS):
            btn = QPushButton(f"  {label}", self.sidebar)
            btn.setProperty("navItem", True)
            btn.setProperty("active", False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _checked=False, k=key: self.navigate(k))
            sb_layout.addWidget(btn)
            self.nav_buttons[key] = btn

            shortcut = QShortcut(QKeySequence(f"Ctrl+{idx + 1}"), self)
            shortcut.activated.connect(lambda k=key: self.navigate(k))

        sb_layout.addStretch(1)

        # Sidebar footer: quick theme toggle + version
        self.theme_toggle_btn = QPushButton("", self.sidebar)
        self.theme_toggle_btn.setProperty("variant", "ghost")
        self.theme_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_toggle_btn.setToolTip("Toggle dark / light theme (Ctrl+T)")
        self.theme_toggle_btn.setAccessibleName("Toggle theme")
        self.theme_toggle_btn.clicked.connect(self.toggle_theme)
        sb_layout.addWidget(self.theme_toggle_btn)

        theme_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        theme_shortcut.activated.connect(self.toggle_theme)

        ver_lbl = QLabel(f"v{__version__}", self.sidebar)
        ver_lbl.setProperty("role", "muted")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_layout.addWidget(ver_lbl)

        body.addWidget(self.sidebar)

        # === Stacked Pages ===
        self.toast = ToastManager(central)

        self.stack = QStackedWidget(central)
        self.apps_page = AppsPage(
            workspace_root=self._workspace_root,
            toast=self.toast,
            provider_store=provider_store,
            on_open_providers=lambda _app_id: self.navigate("providers"),
            parent=self.stack,
        )
        self.providers_page = ProvidersPage(
            toast=self.toast,
            provider_store=provider_store,
            on_defaults_changed=self.apps_page.refresh,
            parent=self.stack,
        )
        self.settings_page = SettingsPage(
            workspace_root=self._workspace_root,
            theme_name=self._theme,
            toast=self.toast,
            on_workspace_changed=self.set_workspace_root,
            on_theme_changed=self.set_theme,
            parent=self.stack,
        )
        self.processes_page = ProcessesPage(
            workspace_root=self._workspace_root,
            toast=self.toast,
            parent=self.stack,
        )
        self.updates_page = UpdatesPage(
            workspace_root=self._workspace_root,
            toast=self.toast,
            parent=self.stack,
        )
        self.diagnostics_page = DiagnosticsPage(
            workspace_root=self._workspace_root,
            toast=self.toast,
            provider_store=provider_store,
            parent=self.stack,
        )

        self._pages: Dict[str, QWidget] = {
            "apps": self.apps_page,
            "processes": self.processes_page,
            "providers": self.providers_page,
            "updates": self.updates_page,
            "settings": self.settings_page,
            "diagnostics": self.diagnostics_page,
        }
        for key, _label, _tip in NAV_ITEMS:
            self.stack.addWidget(self._pages[key])

        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

        # === Bottom Status Bar ===
        self.status_bar_frame = QFrame(central)
        self.status_bar_frame.setObjectName("statusBar")
        self.status_bar_frame.setFixedHeight(30)
        st_layout = QHBoxLayout(self.status_bar_frame)
        st_layout.setContentsMargins(16, 0, 16, 0)
        self.status_workspace_label = QLabel(f"Workspace: {self._workspace_root}", self.status_bar_frame)
        self.status_workspace_label.setProperty("role", "muted")
        self.status_workspace_label.setMinimumWidth(0)
        st_layout.addWidget(self.status_workspace_label, 1)

        self.status_hint_label = QLabel("Ctrl+K palette · Ctrl+1..6 navigate · Ctrl+T theme", self.status_bar_frame)
        self.status_hint_label.setProperty("role", "muted")
        st_layout.addWidget(self.status_hint_label)
        outer.addWidget(self.status_bar_frame)

        # Apply initial theme and page
        self._active_page = "apps"
        self.apply_theme(self._theme)
        self.navigate("apps")

        palette_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        palette_shortcut.activated.connect(self.open_palette)
        self._restore_geometry()

        # Live theme sync: adopt a theme another Plumbnote app writes to the shared settings file.
        self._shared_mtime = shared_settings.mtime()
        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(self.THEME_POLL_MS)
        self._theme_timer.timeout.connect(self.poll_shared_theme)
        self._theme_timer.start()

    @property
    def current_theme(self) -> str:
        return self._theme

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def navigate(self, page_key: str) -> None:
        if page_key not in self._pages:
            return
        self._active_page = page_key
        self.stack.setCurrentWidget(self._pages[page_key])
        tokens = get_tokens(self._theme)
        for key, btn in self.nav_buttons.items():
            is_active = key == page_key
            btn.setProperty("active", is_active)
            btn.setIcon(make_nav_icon(key, tokens.accent if is_active else tokens.text_muted))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        page = self._pages[page_key]
        if hasattr(page, "on_activated"):
            page.on_activated()

    def set_theme(self, theme_name: str, write_shared: bool = True) -> None:
        normalized = "light" if str(theme_name).lower() == "light" else "dark"
        if normalized == self._theme:
            return
        self._theme = normalized
        self.settings.setValue("ui/theme", normalized)
        self.settings.sync()
        if write_shared:
            if not shared_settings.save_theme(normalized):
                self.toast.warning("Could not write settings.json; other apps will not follow the theme.")
            self._shared_mtime = shared_settings.mtime()
        self.apply_theme(normalized)
        self.settings_page.sync_theme(normalized)
        self.theme_changed.emit(normalized)

    def toggle_theme(self) -> None:
        self.set_theme("light" if self._theme == "dark" else "dark")

    def apply_theme(self, theme_name: str) -> None:
        qss = build_stylesheet(theme_name)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)
        else:
            self.setStyleSheet(qss)

        tokens = get_tokens(theme_name)
        if theme_name == "dark":
            self.theme_toggle_btn.setText("  Light mode")
            self.theme_toggle_btn.setIcon(make_nav_icon("theme_light", tokens.text_secondary))
        else:
            self.theme_toggle_btn.setText("  Dark mode")
            self.theme_toggle_btn.setIcon(make_nav_icon("theme_dark", tokens.text_secondary))

        for key, btn in self.nav_buttons.items():
            is_active = key == self._active_page
            btn.setIcon(make_nav_icon(key, tokens.accent if is_active else tokens.text_muted))

    def set_workspace_root(self, new_root: str) -> None:
        path = Path(new_root).resolve()
        self._workspace_root = path
        self.settings.setValue("workspace/root", str(path))
        self.settings.sync()
        self.status_workspace_label.setText(f"Workspace: {path}")
        self.apps_page.set_workspace_root(path)
        self.diagnostics_page.set_workspace_root(path)
        self.processes_page.set_workspace_root(path)
        self.updates_page.set_workspace_root(path)
        self.settings_page.sync_workspace_root(path)
        self.workspace_changed.emit(str(path))

    # -- shared theme -------------------------------------------------
    def poll_shared_theme(self) -> None:
        """Adopt a theme written by another app (cheap: one stat per tick, read only on change)."""
        m = shared_settings.mtime()
        if m == self._shared_mtime:
            return
        self._shared_mtime = m
        theme = shared_settings.load_theme()
        if theme and theme != self._theme:
            self.set_theme(theme, write_shared=False)

    # -- geometry -----------------------------------------------------
    def _restore_geometry(self) -> None:
        geo = self.settings.value("window/geometry")
        if isinstance(geo, (QByteArray, bytes)) and geo:
            self.restoreGeometry(geo)
        state = self.settings.value("window/splitter/processes")
        if isinstance(state, (QByteArray, bytes)) and state:
            self.processes_page.splitter.restoreState(state)

    def save_geometry(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/splitter/processes", self.processes_page.splitter.saveState())
        self.settings.sync()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.save_geometry()
        self._theme_timer.stop()
        if self._tray is not None:
            self._tray.detach()
        super().closeEvent(event)

    # -- tray / visibility --------------------------------------------
    def enable_tray(self) -> bool:
        if self._tray is None:
            self._tray = TrayController(self)
        return self._tray.attach()

    def show_and_raise(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def toggle_visibility(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_and_raise()

    def quit_app(self) -> None:
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    # -- command palette ----------------------------------------------
    def build_commands(self) -> List[Command]:
        cmds: List[Command] = []
        for key, label, _tip in NAV_ITEMS:
            cmds.append(Command(f"Go to {label}", lambda k=key: self.navigate(k), "Navigate"))
        cmds.append(Command("Toggle dark / light theme", self.toggle_theme, "Theme", "switch mode"))
        cmds.append(Command("Use dark theme", lambda: self.set_theme("dark"), "Theme"))
        cmds.append(Command("Use light theme", lambda: self.set_theme("light"), "Theme"))
        cmds.append(Command("Refresh apps", self.apps_page.refresh, "Apps", "rescan"))
        cmds.append(Command("Check for updates",
                            lambda: (self.navigate("updates"), self.updates_page.check()), "Updates"))
        cmds.append(Command("Check provider health",
                            lambda: (self.navigate("providers"), self.providers_page.check_health()), "Providers"))
        cmds.append(Command("Export diagnostics bundle...",
                            lambda: (self.navigate("diagnostics"), self.diagnostics_page.export_bundle()),
                            "Diagnostics", "redacted zip json support"))
        statuses = getattr(self.apps_page, "_statuses", {}) or {}
        for spec in REGISTRY:
            st = statuses.get(spec.id)
            if not (st and st.installed):
                continue
            cmds.append(Command(f"Open {spec.name} folder", lambda a=spec.id: self.apps_page._on_open_folder(a), "App"))
            for act in spec.actions:
                if act.kind == "serve":
                    cmds.append(Command(f"Start {spec.name}: {act.label}",
                                        lambda a=spec.id, n=act.name: self.apps_page._on_start_action(a, n), "App"))
        cmds.append(Command("Quit PlumbCenter", self.quit_app, "App"))
        return cmds

    def open_palette(self) -> CommandPalette:
        dlg = CommandPalette(self.build_commands(), self)
        dlg.show()
        dlg.input.setFocus()
        self._palette = dlg
        return dlg
