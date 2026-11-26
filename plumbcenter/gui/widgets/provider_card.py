"""AI Provider configuration card widget for the Provider Setup Shop."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .badge import Badge


class ProviderCard(QFrame):
    """Card for configuring a single AI provider.

    Security contract: API keys are entered in a password-masked field, cleared
    immediately after saving, and NEVER echoed back into the UI.
    """

    save_requested = Signal(str, dict)      # provider_id, payload
    clear_key_requested = Signal(str)       # provider_id
    test_requested = Signal(str, dict)      # provider_id, draft payload
    docs_requested = Signal(str)            # docs_url

    def __init__(self, spec: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.provider_id: str = spec.id
        self._has_key = False
        self._is_ollama = spec.id == "ollama"

        self.setProperty("card", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(260)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)

        self.enable_cb = QCheckBox(spec.name, self)
        self.enable_cb.setToolTip(f"Enable {spec.name}")
        header.addWidget(self.enable_cb)

        kind_tone = "info" if spec.kind == "local" else "neutral"
        self.kind_badge = Badge(spec.kind.capitalize(), kind_tone, parent=self)
        header.addWidget(self.kind_badge)

        self.key_badge = Badge(
            "No key needed" if not spec.needs_key else "No key",
            "info" if not spec.needs_key else "neutral",
            parent=self,
        )
        header.addWidget(self.key_badge)

        header.addStretch(1)

        if getattr(spec, "docs_url", None):
            docs_btn = QPushButton("Docs", self)
            docs_btn.setProperty("variant", "ghost")
            docs_btn.setProperty("size", "sm")
            docs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            docs_btn.setToolTip(f"Open {spec.name} documentation")
            docs_btn.clicked.connect(lambda: self.docs_requested.emit(spec.docs_url))
            header.addWidget(docs_btn)

        root.addLayout(header)

        # Form grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        row = 0
        if spec.needs_key:
            key_lbl = QLabel("API key", self)
            key_lbl.setProperty("role", "muted")
            grid.addWidget(key_lbl, row, 0)

            self.key_input = QLineEdit(self)
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.key_input.setPlaceholderText(f"Enter {spec.name} API key ({spec.key_env})")
            self.key_input.setToolTip("Stored in OS keyring; never written to JSON or echoed back")
            grid.addWidget(self.key_input, row, 1)
            row += 1
        else:
            self.key_input = None

        url_lbl = QLabel("Base URL", self)
        url_lbl.setProperty("role", "muted")
        grid.addWidget(url_lbl, row, 0)

        self.url_input = QLineEdit(self)
        self.url_input.setText(spec.base_url or "")
        self.url_input.setReadOnly(not self._is_ollama)
        self.url_input.setEnabled(self._is_ollama)
        if not self._is_ollama:
            self.url_input.setToolTip("Catalog default endpoint (read-only for cloud providers)")
        else:
            self.url_input.setToolTip("Local Ollama endpoint (default http://127.0.0.1:11434)")
        grid.addWidget(self.url_input, row, 1)
        row += 1

        model_lbl = QLabel("Default model", self)
        model_lbl.setProperty("role", "muted")
        grid.addWidget(model_lbl, row, 0)

        self.model_input = QLineEdit(self)
        self.model_input.setText(spec.default_model or "")
        self.model_input.setPlaceholderText("Model identifier")
        grid.addWidget(self.model_input, row, 1)

        root.addLayout(grid)

        # Action row
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.save_btn = QPushButton("Save", self)
        self.save_btn.setProperty("variant", "primary")
        self.save_btn.setProperty("size", "sm")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._emit_save)
        actions.addWidget(self.save_btn)

        self.test_btn = QPushButton("Test connection", self)
        self.test_btn.setProperty("size", "sm")
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_btn.clicked.connect(self._emit_test)
        actions.addWidget(self.test_btn)

        self.clear_key_btn = QPushButton("Clear key", self)
        self.clear_key_btn.setProperty("variant", "ghost")
        self.clear_key_btn.setProperty("size", "sm")
        self.clear_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_key_btn.setVisible(spec.needs_key)
        self.clear_key_btn.setEnabled(False)
        self.clear_key_btn.clicked.connect(lambda: self.clear_key_requested.emit(self.provider_id))
        actions.addWidget(self.clear_key_btn)

        actions.addStretch(1)

        self.test_status_label = QLabel("", self)
        self.test_status_label.setProperty("role", "muted")
        actions.addWidget(self.test_status_label)

        root.addLayout(actions)

    def apply_config(
        self,
        *,
        enabled: bool,
        base_url: Optional[str],
        default_model: Optional[str],
        has_key: bool,
    ) -> None:
        self._has_key = bool(has_key)
        self.enable_cb.setChecked(bool(enabled))
        if base_url:
            self.url_input.setText(base_url)
        if default_model is not None:
            self.model_input.setText(default_model)

        if self.spec.needs_key:
            if self._has_key:
                self.key_badge.set_badge("Key saved", "success", "API key is stored securely in keyring")
                if self.key_input is not None:
                    self.key_input.clear()
                    self.key_input.setPlaceholderText("•••••••• (stored securely; enter new key to replace)")
            else:
                self.key_badge.set_badge("No key", "neutral", "No API key stored yet")
                if self.key_input is not None:
                    self.key_input.setPlaceholderText(f"Enter {self.spec.name} API key ({self.spec.key_env})")
            self.clear_key_btn.setEnabled(self._has_key)
        else:
            self.key_badge.set_badge("No key needed", "info", "Local provider does not require an API key")

    def set_testing(self, testing: bool) -> None:
        self.test_btn.setEnabled(not testing)
        self.save_btn.setEnabled(not testing)
        if testing:
            self.test_status_label.setText("Testing...")

    def set_test_result(self, ok: bool, message: str, latency_ms: Optional[int] = None) -> None:
        self.test_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        suffix = f" ({latency_ms} ms)" if latency_ms is not None else ""
        prefix = "✓ " if ok else "✕ "
        self.test_status_label.setText(f"{prefix}{message}{suffix}")
        self.test_status_label.setToolTip(f"{message}{suffix}")

    def _collect_payload(self) -> dict:
        key_val = self.key_input.text().strip() if self.key_input is not None else ""
        return {
            "enabled": self.enable_cb.isChecked(),
            "api_key": key_val if key_val else None,
            "base_url": self.url_input.text().strip() if self._is_ollama else self.spec.base_url,
            "default_model": self.model_input.text().strip() or self.spec.default_model,
        }

    def _emit_save(self) -> None:
        payload = self._collect_payload()
        if self.key_input is not None:
            self.key_input.clear()
        self.save_requested.emit(self.provider_id, payload)

    def _emit_test(self) -> None:
        payload = self._collect_payload()
        self.test_requested.emit(self.provider_id, payload)
