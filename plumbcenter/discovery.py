"""Discovery of installed Plumbnote apps."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

from .registry import AppSpec, REGISTRY, get_app


@dataclass
class AppStatus:
    id: str
    name: str
    tagline: str
    stage: str
    repo: str
    web_url: str
    installed: bool
    path: Optional[str]
    version: Optional[str]
    branch: Optional[str]
    commit: Optional[str]
    dirty: Optional[bool]
    actions: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


def hub_root(override: Optional[str] = None) -> Path:
    """Return the directory that holds the app checkouts."""
    if override:
        return Path(override).resolve()
    env_home = os.environ.get("PLUMBCENTER_HOME")
    if env_home:
        return Path(env_home).resolve()
    # Default: parent directory of this repo (siblings).
    # __file__ is plumbcenter/discovery.py -> parent = plumbcenter/ -> parent.parent = repo root,
    # parent.parent.parent = one level above (siblings dir).
    return Path(__file__).resolve().parent.parent.parent


def find_checkout(app: AppSpec, root: Path) -> Optional[Path]:
    """Find the checkout directory for an app under root."""
    for dir_name in app.dir_names:
        candidate = root / dir_name
        if candidate.is_dir() and (candidate / ".git").exists():
            return candidate
    return None


def _run_git(path: Path, args: List[str], timeout: int = 15) -> Optional[str]:
    """Run git command in path, return stdout stripped, or None on failure."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", "-C", str(path)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _get_version(app: AppSpec, path: Path) -> Optional[str]:
    """Get version from version_file or git describe."""
    if app.version_file:
        version_file = path / app.version_file
        if version_file.is_file():
            try:
                with open(version_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    version = data.get("version")
                    if isinstance(version, str):
                        return version
            except (json.JSONDecodeError, OSError):
                pass
    # Try git describe --tags --always
    desc = _run_git(path, ["describe", "--tags", "--always"])
    if desc:
        return desc
    # Fallback: short sha
    sha = _run_git(path, ["rev-parse", "--short", "HEAD"])
    return sha


def _get_branch(path: Path) -> Optional[str]:
    """Get current branch name."""
    return _run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"])


def _get_commit(path: Path) -> Optional[str]:
    """Get short commit SHA."""
    return _run_git(path, ["rev-parse", "--short", "HEAD"])


def _is_dirty(path: Path) -> Optional[bool]:
    """Check if working tree has uncommitted changes."""
    status = _run_git(path, ["status", "--porcelain"])
    if status is not None:
        return bool(status.strip())
    return None


def _status_for(app: AppSpec, root: Path) -> AppStatus:
    """Build an AppStatus for a single app under root."""
    checkout = find_checkout(app, root)
    if checkout:
        installed = True
        path_str = str(checkout)
        version = _get_version(app, checkout)
        branch = _get_branch(checkout)
        commit = _get_commit(checkout)
        dirty = _is_dirty(checkout)
        actions = [a.name for a in app.actions]
    else:
        installed = False
        path_str = None
        version = None
        branch = None
        commit = None
        dirty = None
        actions = [a.name for a in app.actions]
    return AppStatus(
        id=app.id,
        name=app.name,
        tagline=app.tagline,
        stage=app.stage,
        repo=app.repo,
        web_url=app.web_url,
        installed=installed,
        path=path_str,
        version=version,
        branch=branch,
        commit=commit,
        dirty=dirty,
        actions=actions,
    )


def scan(root: Optional[Path] = None) -> List[AppStatus]:
    """Scan for all apps in REGISTRY order."""
    if root is None:
        root = hub_root()
    root = Path(root)
    return [_status_for(app, root) for app in REGISTRY]


def get_status(app_id: str, root: Optional[Path] = None) -> AppStatus:
    """Get status for a single app by id."""
    app = get_app(app_id)
    if app is None:
        raise KeyError(app_id)
    if root is None:
        root = hub_root()
    root = Path(root)
    return _status_for(app, root)


# Cache for github_metadata
_github_cache: Dict[str, Dict[str, Any]] = {}
_github_cache_time: Dict[str, float] = {}


def _state_dir() -> Path:
    """Get the state directory for caching."""
    env_state = os.environ.get("PLUMBCENTER_STATE")
    if env_state:
        return Path(env_state).resolve()
    return Path(__file__).resolve().parent.parent / ".plumbcenter"


def github_metadata(app: AppSpec, timeout: float = 5.0, cache_ttl: float = 600) -> dict:
    """Fetch GitHub metadata for an app's repo."""
    cache_key = app.repo
    now = time.time()
    
    # Check cache
    if cache_key in _github_cache and (now - _github_cache_time.get(cache_key, 0)) < cache_ttl:
        return _github_cache[cache_key]
    
    # Ensure state dir exists for persistent cache
    state = _state_dir()
    state.mkdir(exist_ok=True)
    cache_file = state / f"github_{app.repo.replace('/', '_')}.json"
    
    # Try file cache
    if cache_file.is_file():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if (now - cached.get("_cached_at", 0)) < cache_ttl:
                    result = {k: v for k, v in cached.items() if k != "_cached_at"}
                    _github_cache[cache_key] = result
                    _github_cache_time[cache_key] = now
                    return result
        except (json.JSONDecodeError, OSError):
            pass
    
    result = {"error": ""}
    try:
        # Fetch repo info
        req = urllib.request.Request(
            f"https://api.github.com/repos/{app.repo}",
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.load(resp)
                result["stars"] = data.get("stargazers_count")
                result["pushed_at"] = data.get("pushed_at")
                result["description"] = data.get("description")
            else:
                result["error"] = f"HTTP {resp.status}"
    except Exception as e:
        result["error"] = str(e)
    
    try:
        # Fetch latest release
        req = urllib.request.Request(
            f"https://api.github.com/repos/{app.repo}/releases/latest",
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.load(resp)
                result["latest_release"] = data.get("tag_name")
            elif "error" not in result or not result["error"]:
                result["error"] = f"release HTTP {resp.status}"
    except Exception as e:
        if "error" not in result or not result["error"]:
            result["error"] = str(e)
    
    # Ensure all keys exist
    for key in ("stars", "latest_release", "pushed_at", "description"):
        if key not in result:
            result[key] = None
    
    # Cache in memory and file
    _github_cache[cache_key] = result
    _github_cache_time[cache_key] = now
    try:
        cache_data = {**result, "_cached_at": now}
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)
    except OSError:
        pass
    
    return result


def remote_state(path: Path, timeout: int = 15) -> dict:
    """Check remote state: ahead/behind counts."""
    result = {"ahead": 0, "behind": 0, "error": ""}
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        # Fetch first
        fetch_result = subprocess.run(
            ["git", "-C", str(path), "fetch"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if fetch_result.returncode != 0:
            result["error"] = fetch_result.stderr.strip() or "fetch failed"
            return result
        
        # Get ahead/behind
        rev_list = subprocess.run(
            ["git", "-C", str(path), "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if rev_list.returncode == 0:
            out = rev_list.stdout.strip()
            if out:
                parts = out.split()
                if len(parts) == 2:
                    result["ahead"] = int(parts[0])
                    result["behind"] = int(parts[1])
        else:
            # No upstream or other error
            result["error"] = rev_list.stderr.strip() or "no upstream"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError) as e:
        result["error"] = str(e)
    return result