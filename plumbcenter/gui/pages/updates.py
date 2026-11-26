"""Updates page: GitHub Releases check for PlumbCenter and every Plumbnote app, with one-click update."""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import updater
from ..tasks import run_in_background
from ..widgets.badge import Badge
from ..widgets.toast import ToastManager

_TONES = {"update": "warning", "up-to-date": "success", "error": "danger",
          "no-release": "neutral", "unknown": "info"}
_LABELS = {"update": "Update available", "up-to-date": "Up to date", "error": "Check failed",
           "no-release": "No release", "unknown": "Latest known"}


class UpdateRow(QFrame):
    def __init__(self, status: "updater.UpdateStatus", on_update: Callable[[str], None],
                 on_notes: Callable[[str], None], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.status = status
        self.setProperty("panel", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(status.name, self)
        name.setStyleSheet("font-weight: 600;")
        detail = QLabel(status.message or "", self)
        detail.setProperty("role", "muted")
        detail.setWordWrap(True)
        col.addWidget(name)
        col.addWidget(detail)
        lay.addLayout(col, 1)

        inst = f"Installed {status.current}" if status.current else ("Installed" if status.installed else "Not installed")
        ver = QLabel(f"{inst}  ·  Latest {status.latest or '-'}", self)
        ver.setProperty("role", "muted")
        lay.addWidget(ver)

        self.badge = Badge(_LABELS.get(status.state, status.state), _TONES.get(status.state, "neutral"), parent=self)
        self.badge.setToolTip(status.message)
        lay.addWidget(self.badge)

        self.notes_btn = QPushButton("Release notes", self)
        self.notes_btn.setProperty("variant", "ghost")
        self.notes_btn.setEnabled(bool(status.release_url))
        self.notes_btn.clicked.connect(lambda: on_notes(status.release_url or ""))
        lay.addWidget(self.notes_btn)

        is_hub = status.app_id == updater.HUB_ID
        label = "Download" if is_hub else ("Update" if status.installed else "Install")
        self.action_btn = QPushButton(label, self)
        self.action_btn.setProperty("variant", "primary")
        self.action_btn.setAccessibleName(f"{label} {status.name}")
        # Hub: only when a newer release exists. Apps: update on a newer release, install when missing.
        self.action_btn.setEnabled(status.update_available or (not status.installed and not is_hub))
        self.action_btn.clicked.connect(lambda: on_update(status.app_id))
        lay.addWidget(self.action_btn)


class UpdatesPage(QWidget):
    def __init__(self, workspace_root: Path, toast: ToastManager,
                 checker: Optional[Callable[..., List[Any]]] = None,
                 apply: Optional[Callable[..., Dict[str, Any]]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workspace_root = Path(workspace_root)
        self._toast = toast
        self._checker = checker or updater.check_updates
        self._apply = apply or updater.apply_update
        self._checked = False
        self._in_flight = False
        self._rows: Dict[str, UpdateRow] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 16)
        root.setSpacing(12)
        header = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("Updates", self)
        title.setProperty("role", "pageTitle")
        sub = QLabel("Checks GitHub Releases for PlumbCenter and the Plumbnote apps. Nothing is installed without a click.", self)
        sub.setProperty("role", "pageSubtitle")
        col.addWidget(title)
        col.addWidget(sub)
        header.addLayout(col, 1)
        self.summary_badge = Badge("Not checked", "neutral", parent=self)
        header.addWidget(self.summary_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.check_btn = QPushButton("Check for updates", self)
        self.check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_btn.clicked.connect(self.check)
        header.addWidget(self.check_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget(scroll)
        self.list_layout = QVBoxLayout(host)
        self.list_layout.setContentsMargins(0, 4, 8, 12)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

    def set_workspace_root(self, new_root: Path) -> None:
        self._workspace_root = Path(new_root)

    def on_activated(self) -> None:
        if not self._checked:
            self.check()

    def check(self) -> None:
        if self._in_flight:
            return
        self._in_flight = True
        self.check_btn.setEnabled(False)
        self.summary_badge.set_badge("Checking...", "neutral")

        def _err(msg: str) -> None:
            self.summary_badge.set_badge("Check failed", "danger")
            self._toast.error(f"Update check failed: {msg}")

        run_in_background(self._checker, self._workspace_root,
                          on_success=self._show, on_error=_err, on_done=self._done)

    def _done(self) -> None:
        self._in_flight = False
        self.check_btn.setEnabled(True)

    def _show(self, statuses: List["updater.UpdateStatus"]) -> None:
        self._checked = True
        for row in self._rows.values():
            row.setParent(None)
            row.deleteLater()
        self._rows = {}
        for i, st in enumerate(statuses):
            row = UpdateRow(st, self._on_update, self._open_url, self)
            self._rows[st.app_id] = row
            self.list_layout.insertWidget(i, row)
        n = sum(1 for s in statuses if s.update_available)
        errs = sum(1 for s in statuses if s.state == "error")
        if n:
            self.summary_badge.set_badge(f"{n} update{'s' if n != 1 else ''} available", "warning")
        elif statuses and errs == len(statuses):
            self.summary_badge.set_badge("GitHub unreachable", "danger")
        else:
            self.summary_badge.set_badge("All up to date", "success")

    def _open_url(self, url: str) -> None:
        if url.startswith("https://github.com/"):
            webbrowser.open(url)

    def _on_update(self, app_id: str) -> None:
        row = self._rows.get(app_id)
        if row is None:
            return
        row.action_btn.setEnabled(False)
        row.action_btn.setText("Working...")
        name = row.status.name

        def _ok(res: Dict[str, Any]) -> None:
            if res.get("action") == "downloaded":
                tail = "checksum verified" if res.get("verified") else "no checksum published"
                folder = Path(res["path"]).parent
                self._toast.success(f"Downloaded {res.get('tag')} ({tail}). Run it from {folder}")
                try:
                    if os.name == "nt":
                        os.startfile(str(folder))  # type: ignore[attr-defined]
                except OSError:
                    pass
            else:
                self._toast.success(f"{name}: {res.get('action', 'updated')}")
            self.check()

        def _err(msg: str) -> None:
            self._toast.error(f"{name}: {msg}")
            self.check()

        run_in_background(self._apply, app_id, root=self._workspace_root, on_success=_ok, on_error=_err)
