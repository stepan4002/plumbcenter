"""Release check + verified download. No real network: GitHub is replaced by fakes."""

from __future__ import annotations

import hashlib
import io
import json

import pytest

from plumbcenter import updater
from plumbcenter.discovery import AppStatus
from plumbcenter.registry import REGISTRY


def _rel(repo, tag, assets=()):
    return updater.ReleaseInfo(repo=repo, tag=tag, version=tag.lstrip("v"),
                               url=f"https://github.com/{repo}/releases/tag/{tag}", assets=tuple(assets))


def _statuses(installed_versions):
    out = []
    for spec in REGISTRY:
        v = installed_versions.get(spec.id)
        out.append(AppStatus(spec.id, spec.name, spec.tagline, spec.stage, spec.repo, spec.web_url,
                             spec.id in installed_versions, "/x" if v is not None or spec.id in installed_versions else None,
                             v, None, None, None, []))
    return out


def test_parse_and_compare_versions():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.parse_version("1.10") == (1, 10, 0)
    assert updater.parse_version("1.2.3-rc1") == (1, 2, 3)
    assert updater.parse_version("nightly") is None
    assert updater.is_newer("1.10.0", "1.9.9")
    assert not updater.is_newer("1.0.0", "1.0.0")
    assert not updater.is_newer("1.0.0", None)       # unknown installed version is never "newer"
    assert not updater.is_newer("garbage", "1.0.0")


def test_check_updates_classifies_every_app():
    fetched = []

    def fetcher(repo):
        fetched.append(repo)
        if repo.endswith("plumbdoctor"):
            return _rel(repo, "v2.0.0")
        if repo.endswith("plumbgate"):
            return _rel(repo, "v1.0.0")
        if repo.endswith("plumbscout"):
            raise updater.UpdaterError("GitHub rate limit reached; try again later")
        if repo.endswith("plumbcheck"):
            return _rel(repo, "v0.9.0")
        return None

    res = {s.app_id: s for s in updater.check_updates(
        fetcher=fetcher, statuses=_statuses({"plumbdoctor": "1.0.0", "plumbgate": "1.0.0",
                                             "plumbscout": "0.1.0", "plumbcheck": None}))}
    assert len(res) == len(REGISTRY) + 1                      # hub + every registry app
    assert len(fetched) == len(res)                           # one lookup each, repos from the registry
    assert res["plumbdoctor"].state == "update" and res["plumbdoctor"].update_available
    assert res["plumbgate"].state == "up-to-date"
    assert res["plumbscout"].state == "error" and "rate limit" in res["plumbscout"].message
    assert res["plumbcheck"].state == "unknown"               # installed, version unreadable
    assert res["plumbstudio"].state == "no-release"
    assert res["plumbcenter"].current == "1.0.0"


def test_check_updates_survives_a_crashing_fetcher():
    def boom(repo):
        raise RuntimeError("kaput")

    res = updater.check_updates(fetcher=boom, statuses=_statuses({}))
    assert all(s.state == "error" for s in res)


def test_url_allowlist_rejects_foreign_hosts():
    with pytest.raises(updater.UpdaterError):
        updater._open("http://api.github.com/x", {updater.API_HOST}, "x", 1)
    with pytest.raises(updater.UpdaterError):
        updater._open("https://evil.example/x", updater.DOWNLOAD_HOSTS, "x", 1)
    with pytest.raises(updater.UpdaterError):
        updater._open("https://user:pw@github.com/x", updater.DOWNLOAD_HOSTS, "x", 1)


def test_redirect_to_foreign_host_is_refused():
    h = updater._HostRestrictedRedirect(updater.DOWNLOAD_HOSTS)
    with pytest.raises(updater.UpdaterError):
        h.redirect_request(None, None, 302, "Found", {}, "https://evil.example/a.zip")


def test_parse_release_reads_digest_and_assets():
    rel = updater._parse_release("o/r", {
        "tag_name": "v1.1.0", "html_url": "https://github.com/o/r/releases/tag/v1.1.0",
        "assets": [{"name": "App-win64.zip", "browser_download_url": "https://github.com/o/r/releases/download/v1.1.0/App-win64.zip",
                    "size": 3, "digest": "sha256:" + "AB" * 32},
                   {"name": "no-url"}],
    })
    assert rel.version == "1.1.0" and len(rel.assets) == 1
    assert rel.assets[0].sha256 == "ab" * 32


def test_pick_asset_prefers_win64_zip_and_skips_checksums():
    a = updater.ReleaseAsset
    rel = _rel("o/r", "v1", [a("x.sha256", "u"), a("notes.txt", "u"), a("App-linux.tar.gz", "u"), a("App-1-win64.zip", "u")])
    assert updater.pick_asset(rel).name == "App-1-win64.zip"
    assert updater.pick_asset(_rel("o/r", "v1", [a("x.sha256", "u")])) is None


class _Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _patch_open(monkeypatch, payloads):
    def fake(url, hosts, accept, timeout):
        return _Resp(payloads[url])
    monkeypatch.setattr(updater, "_open", fake)


def test_download_verifies_digest_and_writes_file(tmp_path, monkeypatch):
    data = b"hello plumb"
    url = "https://github.com/o/r/releases/download/v1/App-win64.zip"
    _patch_open(monkeypatch, {url: data})
    asset = updater.ReleaseAsset("App-win64.zip", url, len(data), hashlib.sha256(data).hexdigest())
    out = updater.download_asset(_rel("o/r", "v1", [asset]), asset, tmp_path / "dl")
    assert out["verified"] and (tmp_path / "dl" / "App-win64.zip").read_bytes() == data
    assert not list((tmp_path / "dl").glob("*.part"))


def test_download_checksum_mismatch_discards_file(tmp_path, monkeypatch):
    url = "https://github.com/o/r/releases/download/v1/a.zip"
    _patch_open(monkeypatch, {url: b"tampered"})
    asset = updater.ReleaseAsset("a.zip", url, 8, "0" * 64)
    with pytest.raises(updater.UpdaterError, match="checksum mismatch"):
        updater.download_asset(_rel("o/r", "v1", [asset]), asset, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_download_uses_sidecar_checksum(tmp_path, monkeypatch):
    data = b"payload"
    base = "https://github.com/o/r/releases/download/v1/"
    side = hashlib.sha256(data).hexdigest() + "  a.zip\n"
    _patch_open(monkeypatch, {base + "a.zip": data, base + "a.zip.sha256": side.encode()})
    asset = updater.ReleaseAsset("a.zip", base + "a.zip", len(data))
    rel = _rel("o/r", "v1", [asset, updater.ReleaseAsset("a.zip.sha256", base + "a.zip.sha256")])
    assert updater.download_asset(rel, asset, tmp_path)["verified"] is True


def test_download_strips_path_components_from_asset_name(tmp_path, monkeypatch):
    url = "https://github.com/o/r/releases/download/v1/x"
    _patch_open(monkeypatch, {url: b"x"})
    asset = updater.ReleaseAsset("../../evil.zip", url, 1, hashlib.sha256(b"x").hexdigest())
    out = updater.download_asset(_rel("o/r", "v1", [asset]), asset, tmp_path / "dl")
    assert out["path"] == str(tmp_path / "dl" / "evil.zip")
    assert not (tmp_path / "evil.zip").exists()


def test_apply_update_for_hub_downloads_asset(tmp_path, monkeypatch):
    data = b"zipbytes"
    url = "https://github.com/stepan4002/plumbcenter/releases/download/v9/PlumbCenter-9-win64.zip"
    asset = updater.ReleaseAsset("PlumbCenter-9-win64.zip", url, len(data), hashlib.sha256(data).hexdigest())
    _patch_open(monkeypatch, {url: data})
    res = updater.apply_update("plumbcenter", downloads_dir=tmp_path,
                               fetcher=lambda repo: _rel(repo, "v9", [asset]))
    assert res["action"] == "downloaded" and res["verified"] and res["tag"] == "v9"
    with pytest.raises(updater.UpdaterError, match="no published release"):
        updater.apply_update("plumbcenter", downloads_dir=tmp_path, fetcher=lambda repo: None)


def test_apply_update_for_app_delegates_to_installer(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(updater.installer, "install", lambda app, root=None: calls.append(("install", app)) or {"ok": True})
    monkeypatch.setattr(updater.installer, "update", lambda app, root=None: calls.append(("update", app)) or {"ok": True})
    monkeypatch.setattr(updater, "scan", lambda root=None: _statuses({"plumbdoctor": "1.0.0"}))
    updater.apply_update("plumbdoctor", root=tmp_path)
    updater.apply_update("plumbgate", root=tmp_path)
    assert calls == [("update", "plumbdoctor"), ("install", "plumbgate")]
    with pytest.raises(updater.UpdaterError):
        updater.apply_update("nope", root=tmp_path)


def test_fetch_latest_release_maps_http_errors(monkeypatch):
    import urllib.error

    def raising(code):
        def _open(url, hosts, accept, timeout):
            raise urllib.error.HTTPError(url, code, "x", {}, None)
        return _open

    monkeypatch.setattr(updater, "_open", raising(404))
    assert updater.fetch_latest_release("o/r") is None
    monkeypatch.setattr(updater, "_open", raising(403))
    with pytest.raises(updater.UpdaterError, match="rate limit"):
        updater.fetch_latest_release("o/r")
    body = json.dumps({"tag_name": "v3.0.0", "html_url": "https://github.com/o/r/releases/tag/v3.0.0", "assets": []}).encode()
    monkeypatch.setattr(updater, "_open", lambda *a, **k: _Resp(body))
    assert updater.fetch_latest_release("o/r").version == "3.0.0"
