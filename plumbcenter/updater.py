"""GitHub Releases version check and verified download for the hub and sibling apps.

Network use is limited to the public GitHub API (read-only, no token) and to
release-asset downloads from GitHub's own hosts. Downloads are only saved, never
executed. If GitHub publishes a sha256 digest for an asset, it is verified.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from . import __version__, installer
from .discovery import AppStatus, scan
from .registry import GITHUB_OWNER, REGISTRY

__all__ = [
    "UpdaterError", "ReleaseAsset", "ReleaseInfo", "UpdateStatus", "HUB_ID",
    "parse_version", "is_newer", "fetch_latest_release", "check_updates",
    "pick_asset", "download_asset", "apply_update",
]

HUB_ID = "plumbcenter"
API_HOST = "api.github.com"
DOWNLOAD_HOSTS = frozenset({
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
})
MAX_DOWNLOAD_BYTES = 400 * 1024 * 1024
_UA = "plumbcenter-updater"


class UpdaterError(Exception):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int = 0
    sha256: Optional[str] = None     # lowercase hex, from GitHub's `digest` field when present


@dataclass(frozen=True)
class ReleaseInfo:
    repo: str
    tag: str
    version: str
    url: str
    published_at: Optional[str] = None
    prerelease: bool = False
    assets: Tuple[ReleaseAsset, ...] = ()


@dataclass
class UpdateStatus:
    app_id: str
    name: str
    installed: bool
    current: Optional[str]
    latest: Optional[str] = None
    release_url: Optional[str] = None
    update_available: bool = False
    state: str = "unknown"          # "up-to-date" | "update" | "no-release" | "unknown" | "error"
    message: str = ""
    release: Optional[ReleaseInfo] = field(default=None, repr=False)


_VER = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(text: Optional[str]) -> Optional[Tuple[int, int, int]]:
    """'v1.2.3', '1.2', '1.2.3-rc1' -> (1, 2, 3). None when there is no number."""
    if not text:
        return None
    m = _VER.search(str(text).strip().lstrip("vV"))
    if not m:
        return None
    return tuple(int(g) if g else 0 for g in m.groups())  # type: ignore[return-value]


def is_newer(latest: Optional[str], current: Optional[str]) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def _https_host_ok(url: str, hosts) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "").lower() in hosts and not parts.username


class _HostRestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts) -> None:
        super().__init__()
        self._hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _https_host_ok(newurl, self._hosts):
            raise UpdaterError(f"refusing redirect to {urlsplit(newurl).hostname or 'unknown host'}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, hosts, accept: str, timeout: float):
    if not _https_host_ok(url, hosts):
        raise UpdaterError("url is not an allowed https GitHub host")
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": _UA})
    return urllib.request.build_opener(_HostRestrictedRedirect(hosts)).open(req, timeout=timeout)


def _parse_release(repo: str, data: Dict[str, Any]) -> ReleaseInfo:
    tag = str(data.get("tag_name") or "")
    assets: List[ReleaseAsset] = []
    for a in data.get("assets") or []:
        digest = str(a.get("digest") or "")
        sha = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else None
        url = str(a.get("browser_download_url") or "")
        if a.get("name") and url:
            assets.append(ReleaseAsset(str(a["name"]), url, int(a.get("size") or 0), sha))
    return ReleaseInfo(
        repo=repo, tag=tag, version=tag.lstrip("vV"), url=str(data.get("html_url") or ""),
        published_at=data.get("published_at"), prerelease=bool(data.get("prerelease")),
        assets=tuple(assets),
    )


def fetch_latest_release(repo: str, timeout: float = 10.0) -> Optional[ReleaseInfo]:
    """Latest published (non-draft, non-prerelease) release, or None when the repo has none."""
    url = f"https://{API_HOST}/repos/{repo}/releases/latest"
    try:
        with _open(url, {API_HOST}, "application/vnd.github+json", timeout) as resp:
            data = json.loads(resp.read(2_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code in (403, 429):
            raise UpdaterError("GitHub rate limit reached; try again later") from exc
        raise UpdaterError(f"GitHub returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdaterError(f"could not reach GitHub: {exc}") from exc
    if not isinstance(data, dict) or not data.get("tag_name"):
        return None
    return _parse_release(repo, data)


Fetcher = Callable[[str], Optional[ReleaseInfo]]


def check_updates(root=None, fetcher: Optional[Fetcher] = None,
                  statuses: Optional[List[AppStatus]] = None) -> List[UpdateStatus]:
    """One entry for the hub itself and one per registry app. Never raises per app."""
    fetch = fetcher or fetch_latest_release
    if statuses is None:
        statuses = scan(root)
    by_id = {s.id: s for s in statuses}
    targets: List[Tuple[str, str, str, bool, Optional[str]]] = [
        (HUB_ID, "PlumbCenter", f"{GITHUB_OWNER}/{HUB_ID}", True, __version__)
    ]
    for spec in REGISTRY:
        st = by_id.get(spec.id)
        targets.append((spec.id, spec.name, spec.repo, bool(st and st.installed), st.version if st else None))

    out: List[UpdateStatus] = []
    for app_id, name, repo, installed, current in targets:
        us = UpdateStatus(app_id, name, installed, current)
        try:
            rel = fetch(repo)
        except UpdaterError as exc:
            us.state, us.message = "error", str(exc)
            out.append(us)
            continue
        except Exception as exc:  # noqa: BLE001 - a bad fetcher must not abort the sweep
            us.state, us.message = "error", f"check failed: {exc}"
            out.append(us)
            continue
        if rel is None:
            us.state, us.message = "no-release", "No GitHub release published yet"
        else:
            us.latest, us.release_url, us.release = rel.version, rel.url, rel
            if parse_version(current) is None:
                us.state = "unknown"
                us.message = f"Latest release {rel.tag}; installed version unknown"
            elif is_newer(rel.version, current):
                us.state, us.update_available = "update", True
                us.message = f"{rel.tag} available (installed {current})"
            else:
                us.state, us.message = "up-to-date", f"Up to date ({current})"
        out.append(us)
    return out


def pick_asset(release: ReleaseInfo, prefer: Tuple[str, ...] = ("win64", ".zip")) -> Optional[ReleaseAsset]:
    """Best downloadable asset: prefer names containing `prefer` tokens, never checksum files."""
    candidates = [a for a in release.assets if not a.name.lower().endswith((".sha256", ".sha256sum", ".txt", ".sig"))]
    for token in prefer:
        for a in candidates:
            if token in a.name.lower():
                return a
    return candidates[0] if candidates else None


def _checksum_from_sidecar(release: ReleaseInfo, asset: ReleaseAsset, timeout: float) -> Optional[str]:
    for a in release.assets:
        if a.name.lower() in (asset.name.lower() + ".sha256", asset.name.lower() + ".sha256sum"):
            try:
                with _open(a.url, DOWNLOAD_HOSTS, "application/octet-stream", timeout) as resp:
                    m = re.search(r"\b([0-9a-fA-F]{64})\b", resp.read(4096).decode("utf-8", "replace"))
                    return m.group(1).lower() if m else None
            except (UpdaterError, urllib.error.URLError, OSError):
                return None
    return None


def download_asset(release: ReleaseInfo, asset: ReleaseAsset, dest_dir, timeout: float = 30.0,
                   progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
    """Download `asset` into `dest_dir`; verify sha256 when GitHub or a sidecar publishes one.

    Returns {"path", "sha256", "verified"}. Raises UpdaterError on a mismatch (file removed).
    The file is never executed or extracted.
    """
    name = Path(asset.name).name          # strip any path components from the remote name
    if not name or name in (".", ".."):
        raise UpdaterError("asset has no usable file name")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / name
    part = dest_dir / (name + ".part")
    expected = asset.sha256 or _checksum_from_sidecar(release, asset, timeout)

    h = hashlib.sha256()
    total = 0
    try:
        with _open(asset.url, DOWNLOAD_HOSTS, "application/octet-stream", timeout) as resp, open(part, "wb") as fh:
            size = int(resp.headers.get("Content-Length") or asset.size or 0)
            if size > MAX_DOWNLOAD_BYTES:
                raise UpdaterError("asset is larger than the allowed download size")
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise UpdaterError("download exceeded the allowed size")
                h.update(chunk)
                fh.write(chunk)
                if progress:
                    progress(total, size)
    except (urllib.error.URLError, OSError) as exc:
        part.unlink(missing_ok=True)
        raise UpdaterError(f"download failed: {exc}") from exc
    except UpdaterError:
        part.unlink(missing_ok=True)
        raise

    digest = h.hexdigest()
    if expected and digest != expected:
        part.unlink(missing_ok=True)
        raise UpdaterError("checksum mismatch; the download was discarded")
    part.replace(final)
    return {"path": str(final), "sha256": digest, "verified": bool(expected)}


def apply_update(app_id: str, root=None, downloads_dir=None, fetcher: Optional[Fetcher] = None) -> Dict[str, Any]:
    """One-click update.

    - PlumbCenter itself: download the latest release asset (verified) and return its path.
      The user runs it; the hub never replaces its own running files.
    - A sibling app: clone it when missing, otherwise `git pull --ff-only` (refuses dirty trees).
    """
    app_id = app_id.strip().lower()
    if app_id == HUB_ID:
        from .runner import state_dir
        rel = (fetcher or fetch_latest_release)(f"{GITHUB_OWNER}/{HUB_ID}")
        if rel is None:
            raise UpdaterError("PlumbCenter has no published release yet")
        asset = pick_asset(rel)
        if asset is None:
            raise UpdaterError(f"release {rel.tag} has no downloadable asset")
        res = download_asset(rel, asset, downloads_dir or (state_dir() / "downloads"))
        return {"ok": True, "app": app_id, "action": "downloaded", "tag": rel.tag, **res}
    status = {s.id: s for s in scan(root)}.get(app_id)
    if status is None:
        raise UpdaterError(f"unknown app: {app_id}")
    if not status.installed:
        return installer.install(app_id, root=root)
    return installer.update(app_id, root=root)
