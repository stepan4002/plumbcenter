"""Apps Hub page: Creative-Cloud-style card grid for the 7 Plumbnote apps."""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import discovery, installer, runner
from ...discovery import AppStatus
from ...registry import REGISTRY, get_app
from ..tasks import run_in_background
from ..widgets.app_card import AppCard
from ..widgets.badge import Badge
from ..widgets.log_view import LogViewerDialog
from ..widgets.toast import ToastManager


def _try_get_provider_defaults(provider_store=None) -> Dict[str, str]:
    """Read per-app default provider map without hard-failing if providers module is absent."""
    try:
        store = provider_store
        if store is None:
            from ...providers.store import ProviderStore

            store = ProviderStore()
        return dict(store.defaults() or {})
    except Exception:  # noqa: BLE001
        return {}


def _try_get_provider_names(provider_store=None) -> Dict[str, str]:
    try:
        from ...providers.catalog import PROVIDERS

        return {p.id: p.name for p in PROVIDERS}
    except Exception:  # noqa: BLE001
        return {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "gemini": "Google Gemini",
            "openrouter": "OpenRouter",
            "groq": "Groq",
            "zai": "Z.ai",
            "ollama": "Ollama",
            "kilo": "Kilo",
        }


class AppsPage(QWidget):
    """Main Apps hub page showing all 7 Plumbnote open-source apps."""

    def __init__(
        self,
        workspace_root: Path,
        toast: ToastManager,
        provider_store=None,
        on_open_providers: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._workspace_root = Path(workspace_root)
        self._toast = toast
        self._provider_store = provider_store
        self._on_open_providers = on_open_providers

        self._cards: Dict[str, AppCard] = {}
        self._statuses: Dict[str, AppStatus] = {}
        self._health_map: Dict[str, Dict[str, Any]] = {}
        self._running_map: Dict[str, Dict[str, Any]] = {}
        self._provider_defaults: Dict[str, str] = {}
        self._filter_mode = "all"
        self._log_dialogs: Dict[str, LogViewerDialog] = {}
        self._refresh_in_flight = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 16)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Apps", self)
        title.setProperty("role", "pageTitle")
        subtitle = QLabel("Install, update, set up environments, and launch Plumbnote open-source tools.", self)
        subtitle.setProperty("role", "pageSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        self.summary_badge = Badge("Scanning...", "neutral", parent=self)
        header.addWidget(self.summary_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        self.refresh_btn = QPushButton("Refresh", self)
        self.refresh_btn.setToolTip("Rescan workspace checkouts and running processes")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        root.addLayout(header)

        # Toolbar: search + filter buttons
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Filter apps by name or description...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMaximumWidth(320)
        self.search_input.textChanged.connect(self._apply_filters)
        toolbar.addWidget(self.search_input)

        toolbar.addSpacing(8)

        self._filter_buttons: Dict[str, QPushButton] = {}
        for key, label in (
            ("all", "All"),
            ("installed", "Installed"),
            ("released", "Released"),
            ("preview", "Preview"),
        ):
            btn = QPushButton(label, self)
            btn.setProperty("size", "sm")
            btn.setProperty("variant", "primary" if key == "all" else "ghost")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, k=key: self._set_filter(k))
            toolbar.addWidget(btn)
            self._filter_buttons[key] = btn

        toolbar.addStretch(1)
        root.addLayout(toolbar)

        # Scrollable card grid
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.grid_host = QWidget(self.scroll)
        self.grid_layout = QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(0, 4, 8, 12)
        self.grid_layout.setHorizontalSpacing(14)
        self.grid_layout.setVerticalSpacing(14)
        self.grid_layout.setColumnStretch(0, 1)
        self.grid_layout.setColumnStretch(1, 1)

        for spec in REGISTRY:
            card = AppCard(spec, self.grid_host)
            card.install_clicked.connect(self._on_install)
            card.update_clicked.connect(self._on_update)
            card.setup_clicked.connect(self._on_setup_venv)
            card.run_clicked.connect(self._on_run_action)
            card.start_clicked.connect(self._on_start_action)
            card.stop_clicked.connect(self._on_stop_action)
            card.logs_clicked.connect(self._on_open_logs)
            card.open_folder_clicked.connect(self._on_open_folder)
            card.open_running_clicked.connect(self._on_open_running)
            card.provider_chip_clicked.connect(self._on_provider_chip)
            self._cards[spec.id] = card

        self.empty_label = QLabel("No apps match your current filter.", self.grid_host)
        self.empty_label.setProperty("role", "muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setVisible(False)

        self.scroll.setWidget(self.grid_host)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)

        self._relayout_cards()

    def set_workspace_root(self, new_root: Path) -> None:
        self._workspace_root = Path(new_root)
        self.refresh()

    def on_activated(self) -> None:
        self.refresh()

    def _set_filter(self, mode: str) -> None:
        self._filter_mode = mode
        for key, btn in self._filter_buttons.items():
            btn.setProperty("variant", "primary" if key == mode else "ghost")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._apply_filters()

    def _apply_filters(self) -> None:
        self._relayout_cards()

    def _relayout_cards(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(self.grid_host)

        query = self.search_input.text().strip().lower()
        visible_cards: List[AppCard] = []

        for spec in REGISTRY:
            card = self._cards[spec.id]
            st = self._statuses.get(spec.id)
            matches_query = (
                not query
                or query in spec.name.lower()
                or query in spec.tagline.lower()
                or query in spec.id.lower()
            )
            matches_filter = True
            if self._filter_mode == "installed":
                matches_filter = bool(st and st.installed)
            elif self._filter_mode == "released":
                matches_filter = spec.stage == "released"
            elif self._filter_mode == "preview":
                matches_filter = spec.stage == "preview"

            show = matches_query and matches_filter
            card.setVisible(show)
            if show:
                visible_cards.append(card)

        cols = 2 if self.width() >= 760 or self.width() == 0 else 1
        for idx, card in enumerate(visible_cards):
            self.grid_layout.addWidget(card, idx // cols, idx % cols, Qt.AlignmentFlag.AlignTop)

        self.empty_label.setVisible(len(visible_cards) == 0)
        if not visible_cards:
            self.grid_layout.addWidget(self.empty_label, 0, 0, 1, cols)
        else:
            self.grid_layout.setRowStretch((len(visible_cards) - 1) // cols + 1, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout_cards()

    def refresh(self) -> None:
        """Scan workspace, process statuses, health, and provider defaults off the UI thread."""
        if self._refresh_in_flight:
            return
        self._refresh_in_flight = True
        self.refresh_btn.setEnabled(False)
        root_path = self._workspace_root
        store = self._provider_store

        def _work() -> dict:
            statuses = discovery.scan(root_path)
            procs = runner.status()
            health_fn = getattr(runner, "health", None)
            health_map: Dict[str, Dict[str, Any]] = {}
            if callable(health_fn):
                for st in statuses:
                    try:
                        health_map[st.id] = health_fn(st.id, root=root_path)
                    except Exception:  # noqa: BLE001
                        pass
            defaults = _try_get_provider_defaults(store)
            provider_names = _try_get_provider_names(store)
            return {
                "statuses": statuses,
                "procs": procs,
                "health": health_map,
                "defaults": defaults,
                "provider_names": provider_names,
            }

        def _on_ok(data: dict) -> None:
            statuses: List[AppStatus] = data["statuses"]
            procs: List[Dict[str, Any]] = data["procs"]
            self._health_map = data["health"]
            self._provider_defaults = data["defaults"]
            provider_names = data["provider_names"]

            self._statuses = {s.id: s for s in statuses}
            self._running_map = {p["app"]: p for p in procs}

            installed_count = sum(1 for s in statuses if s.installed)
            running_count = len(self._running_map)
            summary = f"{installed_count}/{len(statuses)} installed"
            if running_count:
                summary += f" · {running_count} running"
            self.summary_badge.set_badge(summary, "info" if installed_count else "neutral")

            for st in statuses:
                card = self._cards.get(st.id)
                if card is None:
                    continue
                pid = self._provider_defaults.get(st.id)
                plabel = provider_names.get(pid, pid) if pid else None
                card.update_state(
                    st,
                    health=self._health_map.get(st.id),
                    running_proc=self._running_map.get(st.id),
                    provider_label=plabel,
                )
            self._relayout_cards()

        def _on_err(msg: str) -> None:
            self._toast.error(f"Workspace scan failed: {msg}")

        def _on_done() -> None:
            self._refresh_in_flight = False
            self.refresh_btn.setEnabled(True)

        run_in_background(
            _work,
            on_success=_on_ok,
            on_error=_on_err,
            on_done=_on_done,
        )

    def _on_install(self, app_id: str) -> None:
        card = self._cards[app_id]
        card.set_busy(True, "Cloning repository...")
        root_path = self._workspace_root

        def _on_ok(res: dict) -> None:
            self._toast.success(f"Installed {card.spec.name} into {res.get('path', '')}")
            self.refresh()

        def _on_err(msg: str) -> None:
            self._toast.error(f"Install failed for {card.spec.name}: {msg}")

        run_in_background(
            installer.install,
            app_id,
            root=root_path,
            on_success=_on_ok,
            on_error=_on_err,
            on_done=lambda: card.set_busy(False),
        )

    def _on_update(self, app_id: str) -> None:
        card = self._cards[app_id]
        card.set_busy(True, "Fetching & updating...")
        root_path = self._workspace_root

        def _on_ok(res: dict) -> None:
            action = res.get("action", "updated")
            self._toast.success(f"{card.spec.name}: {action}")
            self.refresh()

        def _on_err(msg: str) -> None:
            self._toast.error(f"Update failed for {card.spec.name}: {msg}")

        run_in_background(
            installer.update,
            app_id,
            root=root_path,
            on_success=_on_ok,
            on_error=_on_err,
            on_done=lambda: card.set_busy(False),
        )

    def _on_setup_venv(self, app_id: str) -> None:
        setup_fn = getattr(runner, "setup_venv", None)
        card = self._cards[app_id]
        if not callable(setup_fn):
            self._toast.warning("Environment setup (runner.setup_venv) is not available yet.")
            return
        card.set_busy(True, "Setting up .venv & dependencies...")
        root_path = self._workspace_root

        def _on_ok(res: dict) -> None:
            msg = res.get("message") or "Virtual environment ready"
            self._toast.success(f"{card.spec.name}: {msg}")
            self.refresh()

        def _on_err(msg: str) -> None:
            self._toast.error(f"Set up failed for {card.spec.name}: {msg}")

        run_in_background(
            setup_fn,
            app_id,
            root=root_path,
            on_success=_on_ok,
            on_error=_on_err,
            on_done=lambda: card.set_busy(False),
        )

    def _on_run_action(self, app_id: str, action_name: str) -> None:
        card = self._cards[app_id]
        card.set_busy(True, f"Running {action_name}...")
        root_path = self._workspace_root

        def _on_ok(res: dict) -> None:
            ok = res.get("ok", False)
            code = res.get("exit_code", 0)
            dur = res.get("duration_s", 0.0)
            if ok:
                self._toast.success(f"{card.spec.name} {action_name} finished ({dur:.1f}s)")
            else:
                self._toast.warning(f"{card.spec.name} {action_name} exited with code {code}")
            dlg = LogViewerDialog(
                app_id=app_id,
                app_name=card.spec.name,
                action_name=action_name,
                initial_text=res.get("output", "") or "(no output)",
                is_live=False,
                parent=self,
            )
            dlg.show()
            self._log_dialogs[f"{app_id}:{action_name}:static"] = dlg

        def _on_err(msg: str) -> None:
            self._toast.error(f"{card.spec.name} {action_name} failed: {msg}")

        run_in_background(
            runner.run_action,
            app_id,
            action_name,
            root=root_path,
            on_success=_on_ok,
            on_error=_on_err,
            on_done=lambda: card.set_busy(False),
        )

    def _on_start_action(self, app_id: str, action_name: str) -> None:
        card = self._cards[app_id]
        card.set_busy(True, f"Starting {action_name}...")
        root_path = self._workspace_root

        def _on_ok(_res: dict) -> None:
            self._toast.success(f"Started {card.spec.name} ({action_name})")
            self.refresh()

        def _on_err(msg: str) -> None:
            self._toast.error(f"Could not start {card.spec.name}: {msg}")

        run_in_background(
            runner.start,
            app_id,
            action_name,
            root=root_path,
            on_success=_on_ok,
            on_error=_on_err,
            on_done=lambda: card.set_busy(False),
        )

    def _on_stop_action(self, app_id: str, action_name: str) -> None:
        card = self._cards[app_id]
        card.set_busy(True, f"Stopping {action_name}...")

        def _on_ok(_res: dict) -> None:
            self._toast.info(f"Stopped {card.spec.name} ({action_name})")
            self.refresh()

        def _on_err(msg: str) -> None:
            self._toast.error(f"Could not stop {card.spec.name}: {msg}")

        run_in_background(
            runner.stop,
            app_id,
            action_name,
            on_success=_on_ok,
            on_error=_on_err,
            on_done=lambda: card.set_busy(False),
        )

    def _on_open_logs(self, app_id: str, action_name: str) -> None:
        spec = get_app(app_id)
        app_name = spec.name if spec else app_id
        key = f"{app_id}:{action_name}"
        existing = self._log_dialogs.get(key)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        dlg = LogViewerDialog(
            app_id=app_id,
            app_name=app_name,
            action_name=action_name,
            is_live=True,
            on_stop=lambda: self._on_stop_action(app_id, action_name),
            parent=self,
        )
        self._log_dialogs[key] = dlg
        dlg.show()

    def _on_open_folder(self, app_id: str) -> None:
        st = self._statuses.get(app_id)
        if not st or not st.path:
            self._toast.warning("App is not installed locally.")
            return
        try:
            if os.name == "nt":
                os.startfile(st.path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(f"file://{st.path}")
        except Exception as exc:  # noqa: BLE001
            self._toast.error(f"Could not open folder: {exc}")

    def _on_open_running(self, app_id: str) -> None:
        root_path = self._workspace_root

        def _on_ok(res: dict) -> None:
            opened = res.get("opened")
            if opened:
                self._toast.info(f"Opened {opened}")
            else:
                self._toast.warning("No launch URL or folder available yet.")

        run_in_background(
            runner.open_app,
            app_id,
            root=root_path,
            on_success=_on_ok,
            on_error=lambda msg: self._toast.error(f"Open failed: {msg}"),
        )

    def _on_provider_chip(self, app_id: str) -> None:
        if self._on_open_providers:
            self._on_open_providers(app_id)
