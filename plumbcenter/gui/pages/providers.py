"""AI Provider Setup Shop page: configure 8 providers and per-app default matrix."""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...registry import REGISTRY
from ...providers import health as provider_health
from ..tasks import run_in_background
from ..widgets.badge import Badge
from ..widgets.provider_card import ProviderCard
from ..widgets.toast import ToastManager


@dataclass(frozen=True)
class _FallbackProviderSpec:
    id: str
    name: str
    kind: str
    base_url: str
    key_env: str
    needs_key: bool
    default_model: str
    docs_url: str
    test_kind: str


_FALLBACK_PROVIDERS: Tuple[_FallbackProviderSpec, ...] = (
    _FallbackProviderSpec("openai", "OpenAI", "cloud", "https://api.openai.com/v1", "OPENAI_API_KEY", True, "gpt-4.1-mini", "https://platform.openai.com/docs", "openai"),
    _FallbackProviderSpec("anthropic", "Anthropic", "cloud", "https://api.anthropic.com", "ANTHROPIC_API_KEY", True, "claude-sonnet-4-20250514", "https://docs.anthropic.com", "anthropic"),
    _FallbackProviderSpec("gemini", "Google Gemini", "cloud", "https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY", True, "gemini-2.5-flash", "https://ai.google.dev/gemini-api/docs", "gemini"),
    _FallbackProviderSpec("openrouter", "OpenRouter", "cloud", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", True, "openai/gpt-4.1-mini", "https://openrouter.ai/docs", "openai"),
    _FallbackProviderSpec("groq", "Groq", "cloud", "https://api.groq.com/openai/v1", "GROQ_API_KEY", True, "llama-3.3-70b-versatile", "https://console.groq.com/docs", "openai"),
    _FallbackProviderSpec("zai", "Z.ai", "cloud", "https://api.z.ai/api/paas/v4", "ZAI_API_KEY", True, "glm-4.5-air", "https://docs.z.ai", "openai"),
    _FallbackProviderSpec("ollama", "Ollama", "local", "http://127.0.0.1:11434", "", False, "llama3.2", "https://ollama.com/docs", "ollama"),
    _FallbackProviderSpec("kilo", "Kilo", "cloud", "https://api.kilo.ai/api/openrouter", "KILO_API_KEY", True, "auto", "https://kilo.ai/docs", "openai"),
)


def _load_provider_catalog() -> Tuple[Any, ...]:
    try:
        from ...providers.catalog import PROVIDERS

        return PROVIDERS
    except Exception:  # noqa: BLE001
        return _FALLBACK_PROVIDERS


def _create_default_store():
    try:
        from ...providers.store import ProviderStore

        return ProviderStore()
    except Exception:  # noqa: BLE001
        return None


class ProvidersPage(QWidget):
    """AI Provider Setup Shop: keys stored in OS keyring, config in ~/.plumbnote/providers.json."""

    def __init__(
        self,
        toast: ToastManager,
        provider_store=None,
        on_defaults_changed: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._toast = toast
        self._store = provider_store if provider_store is not None else _create_default_store()
        self._on_defaults_changed = on_defaults_changed
        self._catalog = _load_provider_catalog()
        self._specs_by_id = {s.id: s for s in self._catalog}
        self._cards: Dict[str, ProviderCard] = {}
        self._default_combos: Dict[str, QComboBox] = {}
        self._updating_combos = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 16)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("AI Provider Setup Shop", self)
        title.setProperty("role", "pageTitle")
        subtitle = QLabel(
            "Configure cloud & local AI providers once. Keys are stored in your OS keyring — never in JSON.",
            self,
        )
        subtitle.setProperty("role", "pageSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        self.store_badge = Badge(
            "Connected" if self._store is not None else "Preview mode",
            "success" if self._store is not None else "warning",
            parent=self,
        )
        header.addWidget(self.store_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.reload)
        header.addWidget(refresh_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        # Scroll area holding both provider grid and per-app default matrix
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 4, 8, 16)
        content_layout.setSpacing(18)

        # Provider health + quota summary card
        health_panel = QFrame(content)
        health_panel.setProperty("panel", True)
        health_layout = QVBoxLayout(health_panel)
        health_layout.setContentsMargins(18, 14, 18, 14)
        health_layout.setSpacing(8)
        health_head = QHBoxLayout()
        health_title = QLabel("Provider health", health_panel)
        health_title.setProperty("role", "sectionTitle")
        health_head.addWidget(health_title)
        self.health_badge = Badge("Not checked", "neutral", parent=health_panel)
        health_head.addWidget(self.health_badge)
        health_head.addStretch(1)
        self.health_btn = QPushButton("Check health", health_panel)
        self.health_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.health_btn.clicked.connect(self.check_health)
        health_head.addWidget(self.health_btn)
        health_layout.addLayout(health_head)
        self.health_detail = QLabel(
            "Pings each enabled provider with a cheap authenticated request. "
            "Quota is shown only where the provider exposes it.", health_panel)
        self.health_detail.setProperty("role", "muted")
        self.health_detail.setWordWrap(True)
        self.health_detail.setAccessibleName("Provider health results")
        health_layout.addWidget(self.health_detail)
        content_layout.addWidget(health_panel)

        # Providers grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        for idx, spec in enumerate(self._catalog):
            card = ProviderCard(spec, content)
            card.save_requested.connect(self._on_save_provider)
            card.clear_key_requested.connect(self._on_clear_key)
            card.test_requested.connect(self._on_test_provider)
            card.docs_requested.connect(self._on_open_docs)
            self._cards[spec.id] = card
            grid.addWidget(card, idx // 2, idx % 2, Qt.AlignmentFlag.AlignTop)

        content_layout.addLayout(grid)

        # Per-app default provider matrix
        matrix_panel = QFrame(content)
        matrix_panel.setProperty("panel", True)
        matrix_layout = QVBoxLayout(matrix_panel)
        matrix_layout.setContentsMargins(18, 16, 18, 16)
        matrix_layout.setSpacing(10)

        matrix_title = QLabel("Default Provider per Plumbnote App", matrix_panel)
        matrix_title.setProperty("role", "sectionTitle")
        matrix_sub = QLabel(
            "Choose which configured provider each Plumbnote app uses by default (saved to ~/.plumbnote/providers.json).",
            matrix_panel,
        )
        matrix_sub.setProperty("role", "muted")
        matrix_layout.addWidget(matrix_title)
        matrix_layout.addWidget(matrix_sub)

        matrix_grid = QGridLayout()
        matrix_grid.setHorizontalSpacing(16)
        matrix_grid.setVerticalSpacing(8)
        matrix_grid.setColumnStretch(1, 1)
        matrix_grid.setColumnStretch(2, 1)

        for row_idx, app_spec in enumerate(REGISTRY):
            app_lbl = QLabel(app_spec.name, matrix_panel)
            app_lbl.setStyleSheet("font-weight: 600;")
            tag_lbl = QLabel(app_spec.tagline, matrix_panel)
            tag_lbl.setProperty("role", "muted")

            combo = QComboBox(matrix_panel)
            combo.setAccessibleName(f"Default AI provider for {app_spec.name}")
            combo.addItem("None (use app default)", None)
            for p_spec in self._catalog:
                combo.addItem(p_spec.name, p_spec.id)
            combo.currentIndexChanged.connect(
                lambda _i, aid=app_spec.id, cb=combo: self._on_default_changed(aid, cb)
            )
            self._default_combos[app_spec.id] = combo

            matrix_grid.addWidget(app_lbl, row_idx, 0)
            matrix_grid.addWidget(tag_lbl, row_idx, 1)
            matrix_grid.addWidget(combo, row_idx, 2)

        matrix_layout.addLayout(matrix_grid)
        content_layout.addWidget(matrix_panel)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.reload()

    def set_store(self, store) -> None:
        self._store = store
        self.reload()

    def on_activated(self) -> None:
        if self._store is None:
            self._store = _create_default_store()
        self.reload()

    def reload(self) -> None:
        if self._store is None:
            self._store = _create_default_store()
        if self._store is None:
            self.store_badge.set_badge("Core pending", "warning", "Waiting for plumbcenter.providers backend")
            return

        self.store_badge.set_badge("Keyring active", "success", "Shared ~/.plumbnote/providers.json")
        try:
            configs = self._store.list()
            defaults = self._store.defaults()
        except Exception as exc:  # noqa: BLE001
            self._toast.error(f"Could not load providers: {exc}")
            return

        for cfg in configs:
            pid = getattr(cfg, "id", None) or (cfg.get("id") if isinstance(cfg, dict) else None)
            card = self._cards.get(pid)
            if card is None:
                continue
            card.apply_config(
                enabled=bool(getattr(cfg, "enabled", False)),
                base_url=getattr(cfg, "base_url", None),
                default_model=getattr(cfg, "default_model", None),
                has_key=bool(getattr(cfg, "has_key", False)),
            )

        self._updating_combos = True
        try:
            for app_id, combo in self._default_combos.items():
                assigned = defaults.get(app_id)
                idx = combo.findData(assigned)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self._updating_combos = False

    def check_health(self, pinger: Optional[Callable[..., Any]] = None) -> None:
        if self._store is None or getattr(self, "_health_in_flight", False):
            return
        self._health_in_flight = True
        self.health_btn.setEnabled(False)
        self.health_badge.set_badge("Pinging...", "neutral")
        store = self._store
        ping = pinger if callable(pinger) else provider_health.ping_all

        def _on_ok(entries: Any) -> None:
            self.show_health(entries)

        def _on_err(msg: str) -> None:
            self.health_badge.set_badge("Check failed", "danger")
            self._toast.error(f"Health check failed: {msg}")

        def _on_done() -> None:
            self._health_in_flight = False
            self.health_btn.setEnabled(True)

        run_in_background(ping, store, on_success=_on_ok, on_error=_on_err, on_done=_on_done)

    def show_health(self, entries: List[Any]) -> None:
        summary = provider_health.summarize(entries)
        if not entries or (summary["ok"] + summary["failed"]) == 0:
            self.health_badge.set_badge("Nothing to ping", "neutral")
        elif summary["failed"]:
            self.health_badge.set_badge(f"{summary['ok']} ok · {summary['failed']} failing", "warning")
        else:
            self.health_badge.set_badge(f"{summary['ok']} healthy · avg {summary['avg_latency_ms']} ms", "success")
        icons = {"ok": "OK", "fail": "FAIL", "skipped": "-"}
        lines = []
        for e in entries:
            if e.state == "skipped":
                lines.append(f"{e.name}: {e.message}")
            else:
                lines.append(f"{icons[e.state]}  {e.name}: {e.latency_ms} ms · {e.message} · quota: {e.quota}")
        self.health_detail.setText(chr(10).join(lines) or "No providers configured.")

    def _on_save_provider(self, provider_id: str, payload: dict) -> None:
        if self._store is None:
            self._toast.warning("Provider store backend is not loaded yet.")
            return
        try:
            self._store.configure(
                provider_id,
                api_key=payload.get("api_key"),
                base_url=payload.get("base_url"),
                default_model=payload.get("default_model"),
                enabled=payload.get("enabled"),
            )
        except Exception as exc:  # noqa: BLE001
            self._toast.error(f"Could not save {provider_id}: {exc}")
            return

        spec = self._specs_by_id.get(provider_id)
        name = spec.name if spec else provider_id
        self._toast.success(f"Saved {name} settings.")
        self.reload()

    def _on_clear_key(self, provider_id: str) -> None:
        if self._store is None:
            return
        try:
            self._store.clear_key(provider_id)
        except Exception as exc:  # noqa: BLE001
            self._toast.error(f"Could not clear key: {exc}")
            return
        spec = self._specs_by_id.get(provider_id)
        self._toast.info(f"Cleared stored API key for {spec.name if spec else provider_id}.")
        self.reload()

    def _on_test_provider(self, provider_id: str, payload: dict) -> None:
        card = self._cards.get(provider_id)
        spec = self._specs_by_id.get(provider_id)
        if card is None or spec is None:
            return

        try:
            from ...providers import tester
        except Exception:  # noqa: BLE001
            self._toast.warning("Provider connection tester is not available yet.")
            return

        api_key = payload.get("api_key")
        if not api_key and self._store is not None and spec.needs_key:
            try:
                api_key = self._store.get_key(provider_id)
            except Exception:  # noqa: BLE001
                api_key = None

        base_url = payload.get("base_url") or spec.base_url
        card.set_testing(True)

        def _work():
            return tester.test_connection(spec, api_key, base_url=base_url, timeout=10.0)

        def _on_ok(res: Any) -> None:
            ok = bool(getattr(res, "ok", False))
            msg = str(getattr(res, "message", "OK" if ok else "Failed"))
            latency = getattr(res, "latency_ms", None)
            card.set_test_result(ok, msg, latency)
            if ok:
                self._toast.success(f"{spec.name} connection succeeded ({latency} ms)")
            else:
                self._toast.warning(f"{spec.name} test failed: {msg}")

        def _on_err(msg: str) -> None:
            card.set_test_result(False, msg, None)
            self._toast.error(f"{spec.name} test error: {msg}")

        run_in_background(_work, on_success=_on_ok, on_error=_on_err)

    def _on_default_changed(self, app_id: str, combo: QComboBox) -> None:
        if self._updating_combos or self._store is None:
            return
        provider_id = combo.currentData()
        try:
            self._store.set_default(app_id, provider_id)
        except Exception as exc:  # noqa: BLE001
            self._toast.error(f"Could not update default for {app_id}: {exc}")
            return
        if self._on_defaults_changed:
            self._on_defaults_changed()

    def _on_open_docs(self, url: str) -> None:
        if url:
            webbrowser.open(url)
