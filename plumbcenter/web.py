"""Local web UI + JSON API for PlumbCenter.

Binds to loopback only. Because the API can clone repositories and run commands, every
request is checked against DNS-rebinding (Host), cross-site (Origin) and simple-form
(custom header) attacks, and only registry-defined apps/actions are ever accepted.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

from . import discovery, installer, runner
from .registry import get_app

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
CSRF_HEADER = "X-PlumbCenter"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
       "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

# Serialises read-modify-write of the process table and git work per app.
_proc_lock = threading.Lock()
_git_locks: Dict[str, threading.Lock] = {}
_git_locks_guard = threading.Lock()

_ID = r"([a-z0-9_-]{1,40})"
_POST_ROUTES = [
    (re.compile(rf"^/api/apps/{_ID}/(install|update)$"), "git"),
    (re.compile(rf"^/api/apps/{_ID}/actions/{_ID}/(run|start|stop)$"), "action"),
    (re.compile(rf"^/api/apps/{_ID}/open$"), "open"),
]


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _git_lock(app_id: str) -> threading.Lock:
    with _git_locks_guard:
        return _git_locks.setdefault(app_id, threading.Lock())


def _app_or_404(app_id: str):
    app = get_app(app_id)
    if app is None:
        raise ApiError(404, f"unknown app: {app_id}")
    return app


class Handler(BaseHTTPRequestHandler):
    server_version = "PlumbCenter/0.1"
    protocol_version = "HTTP/1.1"

    # ---- plumbing -------------------------------------------------------
    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    @property
    def root(self) -> Optional[Path]:
        return self.server.root  # type: ignore[attr-defined]

    def _send(self, status: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: Any):
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        host = self.headers.get("Host", "")
        name, _, port = host.rpartition(":") if ":" in host else (host, "", "")
        if name not in LOOPBACK_HOSTS:
            return False
        return port == str(self.server.server_address[1])

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        port = self.server.server_address[1]
        return origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    def _guard(self, method: str) -> bool:
        if not self._host_ok():
            self._json(403, {"ok": False, "error": "forbidden host"})
            return False
        if method == "POST":
            if not self._origin_ok():
                self._json(403, {"ok": False, "error": "forbidden origin"})
                return False
            if self.headers.get(CSRF_HEADER) != "1":
                self._json(403, {"ok": False, "error": f"missing {CSRF_HEADER} header"})
                return False
        return True

    def _drain_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > 0:
            self.rfile.read(min(n, 65536))

    # ---- dispatch -------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._guard("GET"):
            return
        try:
            parts = urlsplit(self.path)
            path, query = parts.path, parse_qs(parts.query)
            if path.startswith("/api/"):
                self._json(200, self._api_get(path, query))
            else:
                self._static(path)
        except ApiError as e:
            self._json(e.status, {"ok": False, "error": e.message})
        except Exception as e:  # never leak a traceback to the client
            print(f"plumbcenter: internal error: {e!r}", file=sys.stderr)
            self._json(500, {"ok": False, "error": "internal error"})

    def do_POST(self):
        if not self._guard("POST"):
            return
        try:
            self._drain_body()
            self._json(200, self._api_post(urlsplit(self.path).path))
        except ApiError as e:
            self._json(e.status, {"ok": False, "error": e.message})
        except (installer.InstallError, runner.RunnerError) as e:
            self._json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            print(f"plumbcenter: internal error: {e!r}", file=sys.stderr)
            self._json(500, {"ok": False, "error": "internal error"})

    def do_PUT(self):
        self._json(405, {"ok": False, "error": "method not allowed"})

    do_DELETE = do_PATCH = do_PUT

    # ---- GET ------------------------------------------------------------
    def _processes(self) -> List[dict]:
        with _proc_lock:
            return runner.status()

    def _api_get(self, path: str, query: Dict[str, List[str]]) -> dict:
        if path == "/api/apps":
            procs = self._processes()
            apps = [s.to_dict() for s in discovery.scan(self.root)]
            if query.get("remote") == ["1"]:
                with ThreadPoolExecutor(max_workers=7) as pool:
                    metas = list(pool.map(lambda a: discovery.github_metadata(get_app(a["id"])), apps))
                for a, m in zip(apps, metas):
                    a["remote"] = m
            for a in apps:
                a["processes"] = [p for p in procs if p["app"] == a["id"]]
                a["action_specs"] = [{"name": x.name, "label": x.label, "kind": x.kind}
                                     for x in get_app(a["id"]).actions]
            return {"ok": True, "apps": apps}
        if path == "/api/ps":
            return {"ok": True, "processes": self._processes()}
        m = re.fullmatch(rf"/api/apps/{_ID}", path)
        if m:
            _app_or_404(m.group(1))
            d = discovery.get_status(m.group(1), self.root).to_dict()
            d["processes"] = [p for p in self._processes() if p["app"] == m.group(1)]
            return {"ok": True, "app": d}
        m = re.fullmatch(rf"/api/logs/{_ID}/{_ID}", path)
        if m:
            app = _app_or_404(m.group(1))
            if app.action(m.group(2)) is None:
                raise ApiError(404, f"unknown action: {m.group(2)}")
            return {"ok": True, "log": runner.tail_log(app.id, m.group(2), lines=200)}
        raise ApiError(404, "not found")

    # ---- POST -----------------------------------------------------------
    def _api_post(self, path: str) -> dict:
        for rx, kind in _POST_ROUTES:
            m = rx.match(path)
            if not m:
                continue
            app = _app_or_404(m.group(1))
            if kind == "git":
                verb = m.group(2)
                with _git_lock(app.id):
                    return getattr(installer, verb)(app.id, self.root)
            if kind == "open":
                return {"ok": True, **runner.open_app(app.id, self.root)}
            action_name, verb = m.group(2), m.group(3)
            if app.action(action_name) is None:
                raise ApiError(404, f"unknown action: {action_name}")
            if verb == "run":
                return runner.run_action(app.id, action_name, self.root)
            with _proc_lock:
                if verb == "start":
                    return {"ok": True, **runner.start(app.id, action_name, self.root)}
                return {"ok": True, **runner.stop(app.id, action_name)}
        raise ApiError(404, "not found")

    # ---- static ---------------------------------------------------------
    def _static(self, path: str):
        rel = "index.html" if path in ("", "/") else unquote(path).lstrip("/")
        target = (STATIC_DIR / rel).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            raise ApiError(404, "not found")
        ctype = STATIC_TYPES.get(target.suffix)
        if ctype is None or not target.is_file():
            raise ApiError(404, "not found")
        self._send(200, target.read_bytes(), ctype)


def make_server(host: str = "127.0.0.1", port: int = 8765, root=None) -> ThreadingHTTPServer:
    if host not in LOOPBACK_HOSTS:
        raise ValueError("PlumbCenter only binds to loopback (127.0.0.1)")
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    srv.root = Path(root) if root else discovery.hub_root()  # type: ignore[attr-defined]
    return srv


def serve(host: str = "127.0.0.1", port: int = 8765, root=None) -> None:
    srv = make_server(host, port, root)
    print(f"PlumbCenter running at http://127.0.0.1:{srv.server_address[1]}/  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
