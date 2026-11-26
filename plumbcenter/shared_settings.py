"""Shared desktop settings in ``<PLUMBNOTE_HOME>/settings.json`` (default ``~/.plumbnote``).

Contract: a JSON object with ``"version": 1`` and ``"theme": "dark" | "light"``. Any other key belongs
to another Plumbnote app and is preserved untouched on write. The file never holds secrets.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .providers.store import plumbnote_home

__all__ = ["THEMES", "settings_path", "read_settings", "load_theme", "save_theme", "mtime"]

THEMES = ("dark", "light")
FILE_NAME = "settings.json"


def settings_path(home=None) -> Path:
    return plumbnote_home(home) / FILE_NAME


def read_settings(home=None) -> Dict[str, Any]:
    """The parsed file, or {} when missing, unreadable, or not a JSON object. Never raises."""
    try:
        data = json.loads(settings_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_theme(home=None) -> Optional[str]:
    """"dark"/"light" if the shared file sets a valid theme, else None."""
    theme = str(read_settings(home).get("theme", "")).strip().lower()
    return theme if theme in THEMES else None


def save_theme(theme: str, home=None) -> bool:
    """Atomically write the theme, keeping every other key. Returns False on failure (never raises)."""
    theme = str(theme).strip().lower()
    if theme not in THEMES:
        raise ValueError(f"theme must be one of {THEMES}")
    path = settings_path(home)
    data = read_settings(home)
    data["version"] = 1
    data["theme"] = theme
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    return True


def mtime(home=None) -> Optional[float]:
    try:
        return settings_path(home).stat().st_mtime_ns
    except OSError:
        return None
