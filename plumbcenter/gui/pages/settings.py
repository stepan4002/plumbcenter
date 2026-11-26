"""Settings page: workspace root picker, theme toggle, and hub self-update status."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import __version__, discovery
from ..tasks import run_in_background
from ..widgets.badge import Badge
from ..widgets.toast import ToastManager


class SettingsPage(QWidget):
    """Settings page for workspace root, dark/light theme, and self-update check."""

    def __init__(
        self,
        workspace_root: Path,
        theme_name: str,
        toast: ToastManager,
        on_workspace_changed: Callable[[str], None],
        on_theme_changed: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._workspace_root = Path(workspace_root)
        self._theme_name = theme_name
        self._toast = toast
        self._on_workspace_changed = on_workspace_changed
        self._on_theme_changed = on_theme_changed

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 16)
        root.setSpacing(14)

        title = QLabel("Settings", self)
        title.setProperty("role", "pageTitle")
        subtitle = QLabel("Customize your Plumbnote workspace location, appearance, and update status.", self)
        subtitle.setProperty("role", "pageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 8, 16)
        layout.setSpacing(16)

        # === Workspace Root Card ===
        ws_panel = QFrame(content)
        ws_panel.setProperty("panel", True)
        ws_layout = QVBoxLayout(ws_panel)
        ws_layout.setContentsMargins(18, 16, 18, 16)
        ws_layout.setSpacing(10)

        ws_title = QLabel("Workspace Root", ws_panel)
        ws_title.setProperty("role", "sectionTitle")
        ws_desc = QLabel(
            "Directory where Plumbnote app repositories are discovered and cloned.",
            ws_panel,
        )
        ws_desc.setProperty("role", "muted")
        ws_layout.addWidget(ws_title)
        ws_layout.addWidget(ws_desc)

        ws_row = QHBoxLayout()
        ws_row.setSpacing(8)
        self.workspace_input = QLineEdit(str(self._workspace_root), ws_panel)
        self.workspace_input.setPlaceholderText("Path to workspace folder")
        ws_row.addWidget(self.workspace_input, 1)

        browse_btn = QPushButton("Browse...", ws_panel)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_workspace)
        ws_row.addWidget(browse_btn)

        apply_btn = QPushButton("Apply", ws_panel)
        apply_btn.setProperty("variant", "primary")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.clicked.connect(self._apply_workspace_input)
        ws_row.addWidget(apply_btn)

        reset_btn = QPushButton("Reset default", ws_panel)
        reset_btn.setProperty("variant", "ghost")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_workspace)
        ws_row.addWidget(reset_btn)

        ws_layout.addLayout(ws_row)
        layout.addWidget(ws_panel)

        # === Appearance Card ===
        theme_panel = QFrame(content)
        theme_panel.setProperty("panel", True)
        theme_layout = QVBoxLayout(theme_panel)
        theme_layout.setContentsMargins(18, 16, 18, 16)
        theme_layout.setSpacing(10)

        theme_title = QLabel("Appearance", theme_panel)
        theme_title.setProperty("role", "sectionTitle")
        theme_desc = QLabel(
            "Switch between Dark and Light themes. Preference is persisted automatically.",
            theme_panel,
        )
        theme_desc.setProperty("role", "muted")
        theme_layout.addWidget(theme_title)
        theme_layout.addWidget(theme_desc)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(10)

        self.dark_btn = QPushButton("Dark theme", theme_panel)
        self.dark_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dark_btn.clicked.connect(lambda: self._select_theme("dark"))
        theme_row.addWidget(self.dark_btn)

        self.light_btn = QPushButton("Light theme", theme_panel)
        self.light_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.light_btn.clicked.connect(lambda: self._select_theme("light"))
        theme_row.addWidget(self.light_btn)

        theme_row.addStretch(1)
        theme_layout.addLayout(theme_row)
        layout.addWidget(theme_panel)

        # === Self-Update Card ===
        update_panel = QFrame(content)
        update_panel.setProperty("panel", True)
        upd_layout = QVBoxLayout(update_panel)
        upd_layout.setContentsMargins(18, 16, 18, 16)
        upd_layout.setSpacing(10)

        upd_header = QHBoxLayout()
        upd_title = QLabel("PlumbCenter Updates", update_panel)
        upd_title.setProperty("role", "sectionTitle")
        upd_header.addWidget(upd_title)
        upd_header.addStretch(1)

        self.update_badge = Badge(f"v{__version__}", "info", parent=update_panel)
        upd_header.addWidget(self.update_badge)
        upd_layout.addLayout(upd_header)

        self.update_status_label = QLabel(
            f"Installed version: v{__version__}. Click 'Check for updates' to compare with GitHub releases.",
            update_panel,
        )
        self.update_status_label.setProperty("role", "muted")
        self.update_status_label.setWordWrap(True)
        upd_layout.addWidget(self.update_status_label)

        upd_actions = QHBoxLayout()
        self.check_update_btn = QPushButton("Check for updates", update_panel)
        self.check_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_update_btn.clicked.connect(self.check_self_update)
        upd_actions.addWidget(self.check_update_btn)
        upd_actions.addStretch(1)
        upd_layout.addLayout(upd_actions)

        layout.addWidget(update_panel)
        layout.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.sync_theme(theme_name)

    def sync_theme(self, theme_name: str) -> None:
        self._theme_name = theme_name
        self.dark_btn.setProperty("variant", "primary" if theme_name == "dark" else "default")
        self.light_btn.setProperty("variant", "primary" if theme_name == "light" else "default")
        for btn in (self.dark_btn, self.light_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def sync_workspace_root(self, path: Path) -> None:
        self._workspace_root = Path(path)
        self.workspace_input.setText(str(self._workspace_root))

    def _select_theme(self, theme_name: str) -> None:
        self._on_theme_changed(theme_name)
        self.sync_theme(theme_name)

    def _browse_workspace(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Plumbnote Workspace Root",
            str(self._workspace_root),
        )
        if chosen:
            self.workspace_input.setText(chosen)
            self._apply_workspace_input()

    def _apply_workspace_input(self) -> None:
        raw = self.workspace_input.text().strip()
        if not raw:
            self._toast.warning("Workspace path cannot be empty.")
            return
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            self._toast.warning(f"Folder does not exist yet: {p}")
        self._on_workspace_changed(str(p))
        self._toast.success(f"Workspace root set to {p}")

    def _reset_workspace(self) -> None:
        default_root = discovery.hub_root()
        self.workspace_input.setText(str(default_root))
        self._on_workspace_changed(str(default_root))
        self._toast.info(f"Workspace root reset to {default_root}")

    def check_self_update(self) -> None:
        self.check_update_btn.setEnabled(False)
        self.update_status_label.setText("Checking GitHub releases...")
        root_path = self._workspace_root

        def _work() -> dict:
            fn = getattr(discovery, "self_status", None)
            if callable(fn):
                return fn(root_path)
            return {
                "current_version": __version__,
                "latest_release": None,
                "update_available": False,
                "error": "self_status check not available yet",
            }

        def _on_ok(res: Any) -> None:
            if not isinstance(res, dict):
                self.update_status_label.setText(str(res))
                return
            current = res.get("current_version") or res.get("version") or __version__
            latest = res.get("latest_release") or res.get("latest")
            err = res.get("error")
            if err:
                self.update_badge.set_badge("Offline / Unknown", "warning")
                self.update_status_label.setText(f"Current: v{current} · Could not reach GitHub ({err})")
            elif res.get("update_available") and latest:
                self.update_badge.set_badge(f"Update {latest}", "warning")
                self.update_status_label.setText(f"Current: v{current} · Latest release: {latest}")
                self._toast.info(f"PlumbCenter {latest} is available.")
            else:
                self.update_badge.set_badge("Up to date", "success")
                extra = f" · Latest release: {latest}" if latest else ""
                self.update_status_label.setText(f"Current: v{current}{extra}")

        def _on_err(msg: str) -> None:
            self.update_badge.set_badge("Check failed", "danger")
            self.update_status_label.setText(f"Update check failed: {msg}")

        run_in_background(
            _work,
            on_success=_on_ok,
            on_error=_on_err,
            on_done=lambda: self.check_update_btn.setEnabled(True),
        )
