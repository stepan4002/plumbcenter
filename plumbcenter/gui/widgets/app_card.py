"""Creative-Cloud-style application card widget for the Apps hub."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...discovery import AppStatus
from ...registry import AppSpec
from ..icons import make_app_tile
from .badge import Badge


_STAGE_TONES = {
    "released": "info",
    "preview": "warning",
    "design": "neutral",
}

_HEALTH_TONES = {
    "ok": ("Healthy", "success"),
    "warn": ("Warning", "warning"),
    "error": ("Error", "danger"),
    "missing": ("Not installed", "neutral"),
}


class AppCard(QFrame):
    """Card representing a single Plumbnote app with status badges and actions."""

    install_clicked = Signal(str)
    update_clicked = Signal(str)
    setup_clicked = Signal(str)
    run_clicked = Signal(str, str)        # app_id, action_name
    start_clicked = Signal(str, str)      # app_id, action_name
    stop_clicked = Signal(str, str)       # app_id, action_name
    logs_clicked = Signal(str, str)       # app_id, action_name
    open_folder_clicked = Signal(str)
    open_running_clicked = Signal(str)
    provider_chip_clicked = Signal(str)

    def __init__(self, spec: AppSpec, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self._busy = False
        self._running_action: Optional[str] = None
        self._running_url: Optional[str] = None
        self._status: Optional[AppStatus] = None

        self.setProperty("card", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(320)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(10)

        # Top row: monogram tile + title + badges
        top = QHBoxLayout()
        top.setSpacing(12)

        self.icon_label = QLabel(self)
        self.icon_label.setPixmap(make_app_tile(spec.id, 44))
        self.icon_label.setFixedSize(44, 44)
        top.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        self.name_label = QLabel(spec.name, self)
        self.name_label.setProperty("role", "cardTitle")
        name_row.addWidget(self.name_label)
        name_row.addStretch(1)

        self.stage_badge = Badge(
            spec.stage.capitalize(),
            _STAGE_TONES.get(spec.stage, "neutral"),
            tooltip=f"Release stage: {spec.stage}",
            parent=self,
        )
        name_row.addWidget(self.stage_badge)
        title_col.addLayout(name_row)

        badges_row = QHBoxLayout()
        badges_row.setSpacing(6)
        self.health_badge = Badge("Checking...", "neutral", parent=self)
        badges_row.addWidget(self.health_badge)

        self.version_badge = Badge("—", "neutral", parent=self)
        self.version_badge.setVisible(False)
        badges_row.addWidget(self.version_badge)

        self.running_badge = Badge("Running", "success", parent=self)
        self.running_badge.setVisible(False)
        badges_row.addWidget(self.running_badge)

        badges_row.addStretch(1)
        title_col.addLayout(badges_row)
        top.addLayout(title_col, 1)
        root.addLayout(top)

        # Tagline
        self.tagline_label = QLabel(spec.tagline, self)
        self.tagline_label.setProperty("role", "cardBody")
        self.tagline_label.setWordWrap(True)
        self.tagline_label.setMinimumHeight(34)
        root.addWidget(self.tagline_label)

        # Meta row: git branch/status + AI provider chip
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)

        self.meta_label = QLabel("Not installed", self)
        self.meta_label.setProperty("role", "muted")
        self.meta_label.setWordWrap(False)
        meta_row.addWidget(self.meta_label, 1)

        self.provider_btn = QPushButton("AI: Unassigned", self)
        self.provider_btn.setProperty("variant", "ghost")
        self.provider_btn.setProperty("size", "sm")
        self.provider_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.provider_btn.setToolTip("Click to configure default AI provider for this app")
        self.provider_btn.clicked.connect(lambda: self.provider_chip_clicked.emit(self.spec.id))
        meta_row.addWidget(self.provider_btn, 0)
        root.addLayout(meta_row)

        # Progress bar (shown only during background ops)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        # Primary & secondary actions row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(5)

        self.install_btn = QPushButton("Install", self)
        self.install_btn.setProperty("variant", "primary")
        self.install_btn.setProperty("size", "sm")
        self.install_btn.setToolTip(f"Clone {spec.repo} into workspace")
        self.install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_btn.clicked.connect(lambda: self.install_clicked.emit(self.spec.id))
        actions_row.addWidget(self.install_btn)

        self.primary_action_btn = QPushButton("Run", self)
        self.primary_action_btn.setProperty("variant", "primary")
        self.primary_action_btn.setProperty("size", "sm")
        self.primary_action_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.primary_action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_action_btn.clicked.connect(self._on_primary_action)
        actions_row.addWidget(self.primary_action_btn)

        self.demo_btn = QPushButton("Demo", self)
        self.demo_btn.setProperty("size", "sm")
        self.demo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.demo_btn.clicked.connect(self._on_demo_action)
        actions_row.addWidget(self.demo_btn)

        self.stop_btn = QPushButton("Stop", self)
        self.stop_btn.setProperty("variant", "danger")
        self.stop_btn.setProperty("size", "sm")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.clicked.connect(self._on_stop_action)
        actions_row.addWidget(self.stop_btn)

        actions_row.addStretch(1)

        self.update_btn = QPushButton("Update", self)
        self.update_btn.setProperty("size", "sm")
        self.update_btn.setToolTip("Git fetch and fast-forward pull")
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.clicked.connect(lambda: self.update_clicked.emit(self.spec.id))
        actions_row.addWidget(self.update_btn)

        self.setup_btn = QPushButton("Set up", self)
        self.setup_btn.setProperty("size", "sm")
        self.setup_btn.setToolTip("Create .venv and install requirements.txt if present")
        self.setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setup_btn.clicked.connect(lambda: self.setup_clicked.emit(self.spec.id))
        actions_row.addWidget(self.setup_btn)

        self.logs_btn = QPushButton("Logs", self)
        self.logs_btn.setProperty("variant", "ghost")
        self.logs_btn.setProperty("size", "sm")
        self.logs_btn.setToolTip("View live process logs")
        self.logs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logs_btn.clicked.connect(self._on_logs_action)
        actions_row.addWidget(self.logs_btn)

        self.folder_btn = QPushButton("Folder", self)
        self.folder_btn.setProperty("variant", "ghost")
        self.folder_btn.setProperty("size", "sm")
        self.folder_btn.setToolTip("Open local checkout folder")
        self.folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_btn.clicked.connect(lambda: self.open_folder_clicked.emit(self.spec.id))
        actions_row.addWidget(self.folder_btn)

        root.addLayout(actions_row)

        self._serve_action = next((a for a in spec.actions if a.kind == "serve"), None)
        self._run_action = next((a for a in spec.actions if a.kind == "run"), None)
        self._apply_visibility(installed=False)

    def set_busy(self, busy: bool, status_text: Optional[str] = None) -> None:
        self._busy = busy
        self.progress.setVisible(busy)
        if status_text:
            self.meta_label.setText(status_text)
        for btn in (
            self.install_btn,
            self.primary_action_btn,
            self.demo_btn,
            self.stop_btn,
            self.update_btn,
            self.setup_btn,
        ):
            btn.setEnabled(not busy)

    def update_state(
        self,
        status: AppStatus,
        health: Optional[Dict[str, Any]] = None,
        running_proc: Optional[Dict[str, Any]] = None,
        provider_label: Optional[str] = None,
    ) -> None:
        self._status = status
        self._running_action = running_proc.get("action") if running_proc else None
        self._running_url = running_proc.get("url") if running_proc else None

        # Health badge
        if health and isinstance(health, dict):
            state = health.get("state", "ok" if status.installed else "missing")
            reasons = health.get("reasons") or []
            label, tone = _HEALTH_TONES.get(state, (state.capitalize(), "neutral"))
            tip = "\n".join(reasons) if reasons else f"Health: {label}"
            self.health_badge.set_badge(label, tone, tip)
        else:
            if status.installed:
                if status.dirty:
                    self.health_badge.set_badge("Modified", "warning", "Uncommitted changes in git checkout")
                else:
                    self.health_badge.set_badge("Installed", "success", f"Installed at {status.path}")
            else:
                self.health_badge.set_badge("Not installed", "neutral", "Not cloned in workspace")

        # Version badge
        if status.installed and status.version:
            ver_text = status.version if status.version.startswith("v") else f"v{status.version}"
            self.version_badge.set_badge(ver_text, "neutral", f"Commit {status.commit or 'unknown'}")
            self.version_badge.setVisible(True)
        else:
            self.version_badge.setVisible(False)

        # Running badge
        self.running_badge.setVisible(bool(self._running_action))
        if self._running_url:
            self.running_badge.setToolTip(f"Running at {self._running_url}")

        # Metadata text
        if not self._busy:
            if status.installed:
                parts = []
                if status.branch:
                    parts.append(f"branch: {status.branch}")
                if status.dirty:
                    parts.append("dirty")
                if self._running_url:
                    parts.append(self._running_url)
                self.meta_label.setText(" · ".join(parts) if parts else (status.path or "Installed"))
                self.meta_label.setToolTip(status.path or "")
            else:
                self.meta_label.setText(f"Repo: {status.repo}")
                self.meta_label.setToolTip(status.web_url)

        # Provider chip
        if provider_label:
            self.provider_btn.setText(f"AI: {provider_label}")
        else:
            self.provider_btn.setText("AI: Default")

        self._apply_visibility(installed=status.installed)

    def _apply_visibility(self, installed: bool) -> None:
        is_running = bool(self._running_action)
        self.install_btn.setVisible(not installed)
        self.update_btn.setVisible(installed)
        self.setup_btn.setVisible(installed)
        self.folder_btn.setVisible(installed)
        self.stop_btn.setVisible(installed and is_running)
        self.logs_btn.setVisible(installed and (self._serve_action is not None))

        if not installed:
            self.primary_action_btn.setVisible(False)
            self.demo_btn.setVisible(False)
            return

        if self._serve_action is not None:
            self.primary_action_btn.setVisible(True)
            if is_running:
                self.primary_action_btn.setText("Open")
                self.primary_action_btn.setToolTip("Open running app")
            else:
                self.primary_action_btn.setText(self._serve_action.label)
                self.primary_action_btn.setToolTip(f"Start {self._serve_action.name}")
            self.demo_btn.setVisible(self._run_action is not None)
            if self._run_action:
                self.demo_btn.setText("Demo")
                self.demo_btn.setToolTip(self._run_action.label)
        elif self._run_action is not None:
            self.primary_action_btn.setVisible(True)
            self.primary_action_btn.setText(self._run_action.label)
            self.primary_action_btn.setToolTip(f"Execute {self._run_action.name}")
            self.demo_btn.setVisible(False)
        else:
            self.primary_action_btn.setVisible(False)
            self.demo_btn.setVisible(False)

    def _on_primary_action(self) -> None:
        if self._running_action:
            self.open_running_clicked.emit(self.spec.id)
        elif self._serve_action is not None:
            self.start_clicked.emit(self.spec.id, self._serve_action.name)
        elif self._run_action is not None:
            self.run_clicked.emit(self.spec.id, self._run_action.name)

    def _on_demo_action(self) -> None:
        if self._run_action is not None:
            self.run_clicked.emit(self.spec.id, self._run_action.name)

    def _on_stop_action(self) -> None:
        if self._running_action:
            self.stop_clicked.emit(self.spec.id, self._running_action)

    def _on_logs_action(self) -> None:
        action_name = self._running_action or (self._serve_action.name if self._serve_action else "demo")
        self.logs_clicked.emit(self.spec.id, action_name)
