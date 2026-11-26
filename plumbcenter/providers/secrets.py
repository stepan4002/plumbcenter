"""Secret storage for provider API keys.

Keys never belong in JSON, logs, QSettings, exceptions, or test output.
Service name is ``plumbnote``. Account names are ``provider.<id>``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Protocol


SERVICE_NAME = "plumbnote"


class SecretBackend(Protocol):
    def get(self, name: str) -> Optional[str]:
        ...

    def set(self, name: str, value: str) -> None:
        ...

    def delete(self, name: str) -> None:
        ...


def _home(override: Optional[os.PathLike] = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()
    env = os.environ.get("PLUMBNOTE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".plumbnote").resolve()


def _safe_filename(name: str) -> str:
    cleaned = []
    for ch in name:
        if ch.isalnum() or ch in "._-":
            cleaned.append(ch)
        else:
            cleaned.append("_")
    slug = "".join(cleaned).strip("._")
    if not slug or slug in (".", ".."):
        raise ValueError("invalid secret name")
    return slug


class MemoryBackend:
    """In-process store for tests. Never reads or writes the disk."""

    def __init__(self) -> None:
        self._data: Dict[str, str] = {}

    def get(self, name: str) -> Optional[str]:
        return self._data.get(name)

    def set(self, name: str, value: str) -> None:
        self._data[name] = value

    def delete(self, name: str) -> None:
        self._data.pop(name, None)


class KeyringBackend:
    """OS keyring (Windows Credential Manager, macOS Keychain, Secret Service)."""

    def __init__(self, service: str = SERVICE_NAME) -> None:
        self.service = service

    def _keyring(self):
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError("keyring is not installed") from exc
        return keyring

    def get(self, name: str) -> Optional[str]:
        try:
            return self._keyring().get_password(self.service, name)
        except Exception as exc:
            raise RuntimeError("keyring get failed") from exc

    def set(self, name: str, value: str) -> None:
        try:
            self._keyring().set_password(self.service, name, value)
        except Exception as exc:
            raise RuntimeError("keyring set failed") from exc

    def delete(self, name: str) -> None:
        keyring = self._keyring()
        try:
            keyring.delete_password(self.service, name)
        except Exception as exc:
            err_name = exc.__class__.__name__
            if err_name == "PasswordDeleteError":
                return
            raise RuntimeError("keyring delete failed") from exc


class DpapiFileBackend:
    """Per-user DPAPI file fallback (Windows CryptProtectData, current user only).

    Blobs live in ``PLUMBNOTE_HOME/secrets/``. CryptProtectData is called without
    CRYPTPROTECT_LOCAL_MACHINE, so only the current Windows user can decrypt.
    """

    def __init__(self, home=None) -> None:
        self.home = _home(home)
        self.directory = self.home / "secrets"

    def _path(self, name: str) -> Path:
        return self.directory / f"{_safe_filename(name)}.dpapi"

    def get(self, name: str) -> Optional[str]:
        path = self._path(name)
        if not path.is_file():
            return None
        blob = path.read_bytes()
        return _dpapi_unprotect(blob).decode("utf-8")

    def set(self, name: str, value: str) -> None:
        blob = _dpapi_protect(value.encode("utf-8"))
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(name)
        tmp = path.with_suffix(".dpapi.tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, path)

    def delete(self, name: str) -> None:
        path = self._path(name)
        try:
            path.unlink()
        except FileNotFoundError:
            return


def _require_windows() -> None:
    if sys.platform != "win32":
        raise OSError("DPAPI secret storage is only available on Windows")


def _dpapi_protect(data: bytes) -> bytes:
    _require_windows()
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    blob_in = DATA_BLOB()
    buf = ctypes.create_string_buffer(data)
    blob_in.cbData = len(data)
    blob_in.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))
    blob_out = DATA_BLOB()
    # 0x01 = CRYPTPROTECT_UI_FORBIDDEN. Do not set CRYPTPROTECT_LOCAL_MACHINE.
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), "plumbnote", None, None, None, 0x01, ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    _require_windows()
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    blob_in = DATA_BLOB()
    buf = ctypes.create_string_buffer(data)
    blob_in.cbData = len(data)
    blob_in.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _keyring_usable() -> bool:
    try:
        import keyring
    except ImportError:
        return False
    try:
        backend = keyring.get_keyring()
    except Exception:
        return False
    name = type(backend).__name__.lower()
    if "fail" in name or name == "nullkeyring":
        return False
    return True


def default_backend() -> SecretBackend:
    """Keyring when it works, else per-user DPAPI on Windows, else memory."""
    if _keyring_usable():
        return KeyringBackend()
    if sys.platform == "win32":
        return DpapiFileBackend()
    return MemoryBackend()
