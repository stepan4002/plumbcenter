"""Diagnostics page: environment checks, per-app health table, and clipboard report."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import PySide6
from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import __version__, diagnostics_bundle, discovery, runner
from ..tasks import run_in_background
from ..widgets.badge import Badge
from ..widgets.toast import ToastManager


def _probe_cmd(cmd: List[str]) -> str:
    exe = shutil.which(cmd[0])
    if not exe:
        return "Not found on PATH"
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
        out = (res.stdout or res.stderr or "").strip().splitlines()
        return out[0] if out else exe
    except Exception as exc:  # noqa: BLE001
        return f"Error ({exc})"


def _probe_keyring_backend() -> str:
    try:
        from ...providers.secrets import default_backend

        return default_backend().__class__.__name__
    except Exception:  # noqa: BLE001
        try:
            import keyring

            return keyring.get_keyring().__class__.__name__
        except Exception as exc:  # noqa: BLE001
            return f"Unavailable ({exc})"


class DiagnosticsPage(QWidget):
    """System diagnostics and per-app health overview with one-click clipboard report."""

    def __init__(
        self,
        workspace_root: Path,
        toast: ToastManager,
        parent: Optional[QWidget] = None,
        provider_store=None,
    ) -> None:
        super().__init__(parent)
        self._store = provider_store
        self._workspace_root = Path(workspace_root)
        self._toast = toast
        self._last_report: Dict[str, Any] = {}
        self._refresh_in_flight = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 16)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Diagnostics", self)
        title.setProperty("role", "pageTitle")
        subtitle = QLabel("Runtime environment, keyring backend, and per-app health checks.", self)
        subtitle.setProperty("role", "pageSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        self.copy_btn = QPushButton("Copy report", self)
        self.copy_btn.setProperty("variant", "primary")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setToolTip("Copy full diagnostic report to clipboard")
        self.copy_btn.clicked.connect(self.copy_report)
        header.addWidget(self.copy_btn)

        self.export_btn = QPushButton("Export bundle", self)
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setToolTip("Save a secret-redacted diagnostics bundle (.zip or .json) to share for support")
        self.export_btn.setAccessibleName("Export diagnostics bundle")
        self.export_btn.clicked.connect(lambda: self.export_bundle())
        header.addWidget(self.export_btn)

        self.refresh_btn = QPushButton("Run checks", self)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)

        root.addLayout(header)

        # Environment grid panel
        env_panel = QFrame(self)
        env_panel.setProperty("panel", True)
        env_layout = QVBoxLayout(env_panel)
        env_layout.setContentsMargins(18, 14, 18, 14)
        env_layout.setSpacing(10)

        env_title = QLabel("Environment", env_panel)
        env_title.setProperty("role", "sectionTitle")
        env_layout.addWidget(env_title)

        self._env_labels: Dict[str, QLabel] = {}
        env_grid = QGridLayout()
        env_grid.setHorizontalSpacing(18)
        env_grid.setVerticalSpacing(6)
        env_grid.setColumnStretch(1, 1)
        env_grid.setColumnStretch(3, 1)

        fields = [
            ("plumbcenter", "PlumbCenter"),
            ("platform", "OS / Platform"),
            ("python", "Python"),
            ("qt", "Qt / PySide6"),
            ("git", "Git"),
            ("node", "Node.js"),
            ("keyring", "Keyring backend"),
            ("workspace", "Workspace root"),
        ]
        for idx, (key, label) in enumerate(fields):
            r = idx // 2
            c = (idx % 2) * 2
            k_lbl = QLabel(f"{label}:", env_panel)
            k_lbl.setProperty("role", "muted")
            v_lbl = QLabel("Checking...", env_panel)
            v_lbl.setProperty("role", "mono")
            v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            env_grid.addWidget(k_lbl, r, c)
            env_grid.addWidget(v_lbl, r, c + 1)
            self._env_labels[key] = v_lbl

        env_layout.addLayout(env_grid)
        root.addWidget(env_panel)

        # Per-app health table
        table_title_row = QHBoxLayout()
        table_title = QLabel("Per-App Health", self)
        table_title.setProperty("role", "sectionTitle")
        table_title_row.addWidget(table_title)
        table_title_row.addStretch(1)
        self.health_summary_badge = Badge("Pending", "neutral", parent=self)
        table_title_row.addWidget(self.health_summary_badge)
        root.addLayout(table_title_row)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["App", "State", "Version", "Branch", "Details"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

    def set_workspace_root(self, new_root: Path) -> None:
        self._workspace_root = Path(new_root)
        if self.isVisible():
            self.refresh()

    def on_activated(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        if self._refresh_in_flight:
            return
        self._refresh_in_flight = True
        self.refresh_btn.setEnabled(False)
        root_path = self._workspace_root

        def _work() -> Dict[str, Any]:
            env = {
                "plumbcenter": f"v{__version__}",
                "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
                "python": f"{sys.version.split()[0]} ({sys.executable})",
                "qt": f"Qt {qVersion()} / PySide6 {PySide6.__version__}",
                "git": _probe_cmd(["git", "--version"]),
                "node": _probe_cmd(["node", "--version"]),
                "keyring": _probe_keyring_backend(),
                "workspace": str(root_path),
            }
            statuses = discovery.scan(root_path)
            health_fn = getattr(runner, "health", None)
            rows = []
            for st in statuses:
                if callable(health_fn):
                    try:
                        h = health_fn(st.id, root=root_path)
                    except Exception as exc:  # noqa: BLE001
                        h = {"state": "error", "reasons": [str(exc)]}
                else:
                    if not st.installed:
                        h = {"state": "missing", "reasons": ["Not installed in workspace"]}
                    elif st.dirty:
                        h = {"state": "warn", "reasons": ["Uncommitted git changes"]}
                    else:
                        h = {"state": "ok", "reasons": [st.path or "Installed"]}
                rows.append({"status": st, "health": h})
            return {"env": env, "apps": rows}

        def _on_ok(data: Dict[str, Any]) -> None:
            self._last_report = data
            env = data["env"]
            for key, lbl in self._env_labels.items():
                lbl.setText(env.get(key, "—"))

            rows = data["apps"]
            self.table.setRowCount(len(rows))
            ok_count = 0
            for idx, item in enumerate(rows):
                st = item["status"]
                h = item["health"]
                state = str(h.get("state", "missing"))
                if state == "ok":
                    ok_count += 1
                reasons = ", ".join(h.get("reasons") or []) or (st.path or "—")

                self.table.setItem(idx, 0, QTableWidgetItem(st.name))
                self.table.setItem(idx, 1, QTableWidgetItem(state.upper()))
                self.table.setItem(idx, 2, QTableWidgetItem(st.version or "—"))
                self.table.setItem(idx, 3, QTableWidgetItem(st.branch or "—"))
                self.table.setItem(idx, 4, QTableWidgetItem(reasons))

            self.health_summary_badge.set_badge(
                f"{ok_count}/{len(rows)} healthy",
                "success" if ok_count == len(rows) and rows else "info",
            )

        def _on_err(msg: str) -> None:
            self._toast.error(f"Diagnostics failed: {msg}")

        def _on_done() -> None:
            self._refresh_in_flight = False
            self.refresh_btn.setEnabled(True)

        run_in_background(
            _work,
            on_success=_on_ok,
            on_error=_on_err,
            on_done=_on_done,
        )

    def format_report_text(self) -> str:
        env = self._last_report.get("env", {})
        apps = self._last_report.get("apps", [])
        lines = ["PlumbCenter Diagnostics Report", "=" * 32]
        for k, v in env.items():
            lines.append(f"{k}: {v}")
        lines.append("")
        lines.append("Apps:")
        for item in apps:
            st = item["status"]
            h = item["health"]
            reasons = "; ".join(h.get("reasons") or [])
            lines.append(
                f"  - {st.name} ({st.id}): state={h.get('state')} installed={st.installed} "
                f"version={st.version or '-'} branch={st.branch or '-'} {reasons}"
            )
        return "\n".join(lines)

    def copy_report(self) -> None:
        text = self.format_report_text()
        QApplication.clipboard().setText(text)
        self._toast.success("Diagnostics report copied to clipboard.")

    def export_bundle(self, dest: Optional[str] = None) -> None:
        """Write the redacted bundle. With no `dest`, ask where to save (.zip by default)."""
        if dest is None:
            dest, _ = QFileDialog.getSaveFileName(
                self, "Export diagnostics bundle", "plumbcenter-diagnostics.zip",
                "Zip archive (*.zip);;JSON (*.json)")
            if not dest:
                return
        self.export_btn.setEnabled(False)

        def _on_ok(res: Dict[str, Any]) -> None:
            self._toast.success(f"Diagnostics bundle saved ({res['format']}, {res['bytes']} bytes). Secrets are redacted.")
            self.last_export = res

        run_in_background(
            diagnostics_bundle.export_bundle, dest, root=self._workspace_root, store=self._store,
            on_success=_on_ok,
            on_error=lambda msg: self._toast.error(f"Export failed: {msg}"),
            on_done=lambda: self.export_btn.setEnabled(True),
        )
