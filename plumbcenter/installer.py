"""Installation and update of Plumbnote apps."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from .discovery import find_checkout, hub_root
from .registry import AppSpec, get_app


class InstallError(Exception):
    """Raised when installation cannot proceed."""
    pass


class UnknownAppError(InstallError):
    """Raised when app id is not in the registry."""
    pass


# Hook for tests to override clone URL
def clone_url_for(app: AppSpec) -> str:
    """Return the clone URL for an app. Can be monkeypatched in tests."""
    return app.clone_url


def _run_git(path: Path, args: list, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run git command in path, return CompletedProcess."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", "-C", str(path)] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _is_inside_root(path: Path, root: Path) -> bool:
    """Check if path is inside root (no path escape)."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _try_git(path: Path, args: list, timeout: int = 30):
    """Run git, translating timeouts / missing git into InstallError."""
    try:
        return _run_git(path, args, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise InstallError(f"git {' '.join(args)} timed out")
    except FileNotFoundError:
        raise InstallError("git is not installed or not on PATH")


def install(app_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """Clone app into root/dir_names[0]. Returns dict with ok/action/path."""
    app = get_app(app_id)
    if app is None:
        raise UnknownAppError(f"unknown app: {app_id}")

    if root is None:
        root = hub_root()
    root = Path(root)

    # The checkout may live under an alias dir_name, e.g. "plumcheck" for plumbcheck.
    target_dir = find_checkout(app, root)
    if target_dir is not None:
        raise InstallError("already installed")

    # Clone target must stay inside root (reject path escapes).
    candidate = root / app.dir_names[0]
    if not _is_inside_root(candidate, root):
        raise InstallError("target path escapes root")

    # Ensure root exists.
    root.mkdir(parents=True, exist_ok=True)

    # If a non-git folder already exists at the primary dir name, refuse (never overwrite).
    primary = root / app.dir_names[0]
    if primary.exists() and not (primary / ".git").exists():
        raise InstallError(
            f"{app_id}: target folder {app.dir_names[0]} already exists and is not a git checkout"
        )

    # Clone the repo into the first available alias dir name.
    url = clone_url_for(app)
    result = _try_git(root, ["clone", url, app.dir_names[0]], timeout=300)
    if result.returncode != 0:
        # Only clean up if we actually created it.
        if not target_dir.exists() and (root / app.dir_names[0]).exists():
            shutil.rmtree(root / app.dir_names[0], ignore_errors=True)
        raise InstallError(f"git clone failed: {result.stderr.strip()}")

    installed_dir = root / app.dir_names[0]
    return {
        "ok": True,
        "app": app_id,
        "path": str(installed_dir),
        "action": "cloned",
        "output": result.stdout.strip(),
    }


def update(app_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch and pull with --ff-only. Returns dict with ok/action/path."""
    app = get_app(app_id)
    if app is None:
        raise UnknownAppError(f"unknown app: {app_id}")

    if root is None:
        root = hub_root()
    root = Path(root)

    # The checkout may live under an alias dir_name; refuse if none found.
    target_dir = find_checkout(app, root)
    if target_dir is None:
        raise InstallError("not installed")

    # Reject path escapes.
    if not _is_inside_root(target_dir, root):
        raise InstallError("target path escapes root")

    # Check for dirty work tree: update refuses.
    try:
        status_result = _run_git(target_dir, ["status", "--porcelain"])
    except subprocess.TimeoutExpired:
        raise InstallError(f"git status timed out for {app_id}")
    except FileNotFoundError:
        raise InstallError("git is not installed or not on PATH")
    if status_result.returncode == 0 and status_result.stdout.strip():
        raise InstallError(f"{app_id}: working tree has uncommitted changes")

    # Fetch, then pull with --ff-only.
    try:
        fetch_result = _run_git(target_dir, ["fetch"], timeout=120)
        pull_result = _run_git(target_dir, ["pull", "--ff-only"], timeout=120)
    except subprocess.TimeoutExpired:
        raise InstallError(f"git operations timed out for {app_id}")
    except FileNotFoundError:
        raise InstallError("git is not installed or not on PATH")

    if fetch_result.returncode != 0:
        raise InstallError(f"git fetch failed: {fetch_result.stderr.strip()}")

    if pull_result.returncode != 0:
        if "fast-forward" in pull_result.stderr.lower() or "not possible" in pull_result.stderr.lower():
            raise InstallError(f"{app_id}: pull is not a fast-forward")
        raise InstallError(f"git pull failed: {pull_result.stderr.strip()}")

    out = (pull_result.stdout or pull_result.stderr or "").strip()
    if "already up to date" in out.lower():
        action = "up-to-date"
    else:
        action = "updated"

    return {
        "ok": True,
        "app": app_id,
        "path": str(target_dir),
        "action": action,
        "output": out,
    }
