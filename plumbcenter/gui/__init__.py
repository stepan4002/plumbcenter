"""Native PySide6 desktop hub for PlumbCenter."""

from __future__ import annotations

__all__ = ["main"]


def main(*args, **kwargs):
    from .app import main as _main

    return _main(*args, **kwargs)
