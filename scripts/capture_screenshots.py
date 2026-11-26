"""Regenerate docs/screenshots/*.png offscreen with neutral, PII-free demo data.

    QT_QPA_PLATFORM=offscreen python scripts/capture_screenshots.py

Uses a throwaway workspace at a fixed neutral path and a fake interpreter path, so no
user name or profile directory ever appears in an image.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NEUTRAL = Path("C:/plumbnote-demo/workspace") if os.name == "nt" else Path("/tmp/plumbnote-demo/workspace")
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="Demo", GIT_AUTHOR_EMAIL="demo@example.invalid",
               GIT_COMMITTER_NAME="Demo", GIT_COMMITTER_EMAIL="demo@example.invalid")


def _fake_checkout(name: str, version: str = None) -> None:
    d = NEUTRAL / name
    d.mkdir(parents=True)
    if version:
        (d / "package.json").write_text('{"name": "%s", "version": "%s"}\n' % (name, version), encoding="utf-8")
    else:
        (d / "README.md").write_text(name + "\n", encoding="utf-8")
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *cmd], cwd=d, env=GIT_ENV, check=True, capture_output=True)


def _rmtree(path) -> None:
    """rmtree that also removes read-only git objects on Windows."""
    def _force(func, p, _exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except FileNotFoundError:
            pass  # already gone (e.g. a transient git lock file)
    shutil.rmtree(path, onerror=_force)


def _settle(app, page=None, timeout_s: float = 40.0) -> None:
    """Let background scans finish and the UI repaint.

    Uses processEvents + sleep (not QTest.qWait, which starves worker threads of the GIL).
    """
    import time
    from PySide6.QtCore import QThreadPool
    pool = QThreadPool.globalInstance()

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)

    pump(0.3)
    end = time.monotonic() + timeout_s
    while (pool.activeThreadCount() or getattr(page, "_refresh_in_flight", False))             and time.monotonic() < end:
        pump(0.1)
    pump(0.5)


def main() -> int:
    if NEUTRAL.parent.exists():
        _rmtree(NEUTRAL.parent)
    NEUTRAL.mkdir(parents=True)
    _fake_checkout("plumbcheck", "1.2.0")
    for app in ("plumbdoctor", "plumbgate", "plumbscout"):
        _fake_checkout(app)

    home = Path(tempfile.mkdtemp(prefix="pn-"))
    os.environ["PLUMBNOTE_HOME"] = str(home)
    os.environ["PLUMBCENTER_STATE"] = str(home / "state")
    sys.executable = "C:\Python311\python.exe" if os.name == "nt" else "/usr/bin/python3"  # display only

    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication
    from plumbcenter.gui.app import create_application
    from plumbcenter.gui.mainwindow import MainWindow
    from plumbcenter.providers.secrets import MemoryBackend
    from plumbcenter.providers.store import ProviderStore

    app = create_application(["capture"])
    store = ProviderStore(home=home, secrets=MemoryBackend())
    store.configure("openai", api_key="sk-demo-not-a-real-key", enabled=True, default_model="gpt-4.1-mini")
    store.configure("ollama", enabled=True)
    store.set_default("plumbdoctor", "openai")
    store.set_default("plumbgate", "ollama")

    out = ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        settings = QSettings(str(home / f"{theme}.ini"), QSettings.Format.IniFormat)
        settings.setValue("workspace/root", str(NEUTRAL))
        settings.setValue("ui/theme", theme)
        win = MainWindow(settings=settings, provider_store=store)
        win.resize(1240, 820)
        win.show()
        for page in ("apps", "providers", "settings", "diagnostics"):
            win.navigate(page)
            _settle(app, win._pages[page])
            win.grab().save(str(out / f"{page}-{theme}.png"))
        win.close()
    _rmtree(NEUTRAL.parent)
    shutil.rmtree(home, ignore_errors=True)
    print("wrote", len(list(out.glob("*.png"))), "screenshots to", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
