"""Shared provider configuration at ``~/.plumbnote/providers.json``.

Override the directory with ``PLUMBNOTE_HOME`` or ``ProviderStore(home=...)``.
The API key is stored only in the secret backend. JSON keeps ``"secret": "keyring"``
as a marker and never the key itself.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlsplit

from .catalog import ProviderSpec, get_provider
from .secrets import SecretBackend, default_backend

__all__ = ["ProviderConfig", "ProviderError", "ProviderStore", "plumbnote_home"]


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    """Catalog entry merged with the saved config. ``has_key`` is live, not stored."""

    id: str
    name: str
    kind: str
    base_url: str
    key_env: str
    needs_key: bool
    default_model: str
    docs_url: str
    test_kind: str
    enabled: bool
    has_key: bool
    catalog_base_url: str
    catalog_default_model: str


def plumbnote_home(override=None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()
    env = os.environ.get("PLUMBNOTE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".plumbnote").resolve()


def _secret_name(provider_id: str) -> str:
    return f"provider.{provider_id}"


def _redact(message: str, secret: Optional[str]) -> str:
    if secret and secret in message:
        return message.replace(secret, "***")
    return message


_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _validate_base_url(spec: ProviderSpec, url: str) -> str:
    raw = str(url).strip()
    if not raw or any(ch in raw for ch in ("\n", "\r", "\t", " ")):
        raise ProviderError("base_url is invalid")
    parts = urlsplit(raw)
    if parts.username or parts.password:
        raise ProviderError("base_url must not include credentials")
    host = (parts.hostname or "").lower()
    if not host:
        raise ProviderError("base_url is missing a host")
    if spec.kind == "local":
        if parts.scheme not in ("http", "https"):
            raise ProviderError("local base_url must be http or https")
        if parts.scheme == "http" and host not in _LOOPBACK:
            raise ProviderError("http base_url is only allowed for loopback")
    elif parts.scheme != "https":
        raise ProviderError("cloud base_url must use https")
    return raw.rstrip("/")


class ProviderStore:
    def __init__(self, home=None, secrets: Optional[SecretBackend] = None) -> None:
        self.home = plumbnote_home(home)
        self.secrets = secrets if secrets is not None else default_backend()
        self.path = self.home / "providers.json"

    def list(self) -> List[ProviderConfig]:
        """Catalog order, with saved overrides applied. ``has_key`` checks the backend."""
        from .catalog import PROVIDERS

        saved = self._load()["providers"]
        configs = []
        for spec in PROVIDERS:
            entry = saved.get(spec.id) if isinstance(saved.get(spec.id), dict) else {}
            base_url = entry.get("base_url") or spec.base_url
            model = entry.get("default_model") or spec.default_model
            configs.append(ProviderConfig(
                id=spec.id,
                name=spec.name,
                kind=spec.kind,
                base_url=str(base_url),
                key_env=spec.key_env,
                needs_key=spec.needs_key,
                default_model=str(model),
                docs_url=spec.docs_url,
                test_kind=spec.test_kind,
                enabled=bool(entry.get("enabled", False)),
                has_key=self._has_key(spec),
                catalog_base_url=spec.base_url,
                catalog_default_model=spec.default_model,
            ))
        return configs

    def configure(self, id, api_key=None, base_url=None, default_model=None, enabled=None):
        spec = self._require(id)
        data = self._load()
        current = data["providers"].get(spec.id)
        entry = dict(current) if isinstance(current, dict) else {}
        if enabled is None:
            entry["enabled"] = bool(entry.get("enabled", False))
        else:
            entry["enabled"] = bool(enabled)
        if base_url is None:
            entry["base_url"] = entry.get("base_url") or spec.base_url
        else:
            entry["base_url"] = _validate_base_url(spec, base_url)
        if default_model is None:
            entry["default_model"] = entry.get("default_model") or spec.default_model
        else:
            model = str(default_model).strip()
            if not model:
                raise ProviderError("default_model cannot be empty")
            entry["default_model"] = model

        key_text = None
        if api_key is not None:
            key_text = str(api_key).strip()
            if key_text:
                try:
                    self.secrets.set(_secret_name(spec.id), key_text)
                except Exception as exc:
                    raise ProviderError(_redact(str(exc), key_text)) from None
                entry["secret"] = "keyring"

        clean = self._public_entry(entry)
        self._refuse_secret(clean, key_text)
        data["providers"][spec.id] = clean
        self._refuse_secret(data, key_text)
        self._write(data)

    def clear_key(self, id) -> None:
        spec = self._require(id)
        try:
            self.secrets.delete(_secret_name(spec.id))
        except Exception as exc:
            raise ProviderError("could not clear the stored key") from exc
        data = self._load()
        entry = data["providers"].get(spec.id)
        if isinstance(entry, dict) and "secret" in entry:
            entry.pop("secret", None)
            data["providers"][spec.id] = self._public_entry(entry)
            self._write(data)

    def get_key(self, id) -> Optional[str]:
        spec = self._require(id)
        if not spec.needs_key:
            return None
        try:
            value = self.secrets.get(_secret_name(spec.id))
        except Exception as exc:
            raise ProviderError("could not read the stored key") from exc
        if value is None or value == "":
            return None
        return value

    def remove(self, id) -> None:
        spec = self._require(id)
        try:
            self.secrets.delete(_secret_name(spec.id))
        except Exception:
            raise ProviderError("could not delete the stored key") from None
        data = self._load()
        data["providers"].pop(spec.id, None)
        data["defaults"] = {
            app: provider for app, provider in data["defaults"].items() if provider != spec.id
        }
        self._write(data)

    def set_default(self, app_id, provider_id) -> None:
        from ..registry import get_app

        if not isinstance(app_id, str) or get_app(app_id) is None:
            raise ProviderError(f"unknown app: {app_id}")
        app = get_app(app_id)
        data = self._load()
        if provider_id is None:
            data["defaults"].pop(app.id, None)
        else:
            spec = self._require(provider_id)
            data["defaults"][app.id] = spec.id
        self._write(data)

    def defaults(self) -> Dict[str, str]:
        raw = self._load()["defaults"]
        return {str(k): str(v) for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}

    def _require(self, id) -> ProviderSpec:
        if not isinstance(id, str):
            raise ProviderError(f"unknown provider: {id}")
        spec = get_provider(id)
        if spec is None:
            raise ProviderError(f"unknown provider: {id}")
        return spec

    def _has_key(self, spec: ProviderSpec) -> bool:
        if not spec.needs_key:
            return False
        try:
            return bool(self.secrets.get(_secret_name(spec.id)))
        except Exception:
            return False

    @staticmethod
    def _public_entry(entry: dict) -> dict:
        clean = {
            "enabled": bool(entry.get("enabled", False)),
            "base_url": entry.get("base_url") or "",
            "default_model": entry.get("default_model") or "",
        }
        if entry.get("secret") == "keyring":
            clean["secret"] = "keyring"
        return clean

    @staticmethod
    def _refuse_secret(payload, secret: Optional[str]) -> None:
        if not secret:
            return
        if secret in json.dumps(payload):
            raise ProviderError("refusing to write a secret into providers.json")

    def _load(self) -> dict:
        if not self.path.is_file():
            return {"version": 1, "providers": {}, "defaults": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError(f"providers.json is not valid JSON: {exc}") from exc
        except OSError as exc:
            raise ProviderError(f"could not read providers.json: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError("providers.json must be a JSON object")
        data.setdefault("version", 1)
        if not isinstance(data.get("providers"), dict):
            data["providers"] = {}
        if not isinstance(data.get("defaults"), dict):
            data["defaults"] = {}
        return data

    def _write(self, data: dict) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "providers": data.get("providers") or {},
            "defaults": data.get("defaults") or {},
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.path)
