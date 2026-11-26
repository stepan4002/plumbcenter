"""PlumbCenter CLI — `python -m plumbcenter <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import discovery
from .installer import InstallError, UnknownAppError, clone_url_for, install as _install, update as _update
from .registry import AppSpec, get_app, REGISTRY


def _fail(message: str, code: int = 1) -> int:
    """Print one line to stderr (no traceback) and return exit code."""
    print(f"plumbcenter: {message}", file=sys.stderr)
    return code


def _load_runner():
    """Lazy import of runner (worker-2 module)."""
    from . import runner as _runner
    return _runner


def _load_web():
    """Lazy import of web (worker-2 module)."""
    from . import web as _web
    return _web


def _table(headers: List[str], rows: List[List[str]]) -> str:
    """Render a plain-ASCII table (no unicode box chars)."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def fmt(row):
        return "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row))

    lines = [fmt(headers), "  ".join("-" * w for w in widths)]
    for row in rows:
        lines.append(fmt(row))
    return "\n".join(lines)


def _cmd_list(args) -> int:
    root = discovery.hub_root(args.root)
    statuses = discovery.scan(root)

    if args.json:
        payload = []
        for s in statuses:
            entry = s.to_dict()
            if args.remote:
                app = get_app(s.id)
                if app:
                    meta = discovery.github_metadata(app)
                    entry["stars"] = meta.get("stars")
                    entry["latest_release"] = meta.get("latest_release")
                    if meta.get("error"):
                        entry["github_error"] = meta["error"]
            payload.append(entry)
        print(json.dumps(payload, indent=2))
        return 0

    headers = ["id", "name", "stage", "installed", "version", "branch", "commit", "dirty", "actions", "path"]
    rows = []
    for s in statuses:
        rows.append([
            s.id,
            s.name,
            s.stage,
            "yes" if s.installed else "no",
            s.version or "-",
            s.branch or "-",
            s.commit or "-",
            "dirty" if s.dirty else "clean" if s.installed else "-",
            ",".join(s.actions),
            s.path or "-",
        ])
    print(_table(headers, rows))
    return 0


def _cmd_info(args) -> int:
    root = discovery.hub_root(args.root)
    try:
        s = discovery.get_status(args.app, root)
    except KeyError:
        return _fail(f"unknown app: {args.app}", code=2)

    if args.json:
        print(json.dumps(s.to_dict(), indent=2))
        return 0

    print(f"id:        {s.id}")
    print(f"name:      {s.name}")
    print(f"tagline:   {s.tagline}")
    print(f"stage:     {s.stage}")
    print(f"repo:      {s.repo}")
    print(f"web_url:   {s.web_url}")
    print(f"installed: {s.installed}")
    if s.installed:
        print(f"path:      {s.path}")
        print(f"version:   {s.version}")
        print(f"branch:    {s.branch}")
        print(f"commit:    {s.commit}")
        print(f"dirty:     {s.dirty}")
    print(f"actions:   {', '.join(s.actions)}")
    return 0


def _cmd_install(args) -> int:
    root = discovery.hub_root(args.root)
    try:
        result = _install(args.app, root)
    except UnknownAppError as e:
        return _fail(str(e), code=2)
    except InstallError as e:
        return _fail(str(e))
    except Exception as e:
        return _fail(str(e))
    print(f"{result['action']}: {result['app']} -> {result['path']}")
    if result.get("output"):
        print(result["output"])
    return 0


def _cmd_update(args) -> int:
    root = discovery.hub_root(args.root)
    if args.all:
        failures = 0
        for st in discovery.scan(root):
            if not st.installed:
                continue
            try:
                result = _update(st.id, root)
                print(f"{result['action']}: {st.id}")
            except InstallError as e:
                print(f"plumbcenter: {st.id}: {e}", file=sys.stderr)
                failures += 1
        return 1 if failures else 0
    if not args.app:
        return _fail("update needs an app id or --all", code=2)
    try:
        result = _update(args.app, root)
    except UnknownAppError as e:
        return _fail(str(e), code=2)
    except InstallError as e:
        return _fail(str(e))
    print(f"{result['action']}: {result['app']} -> {result['path']}")
    if result.get("output"):
        print(result["output"])
    return 0


def _resolve(args, kind: str):
    """Validate app/action against the registry. Returns (app, action_name) or an exit code."""
    app = get_app(args.app)
    if app is None:
        return _fail(f"unknown app: {args.app}", code=2)
    name = args.action
    if not name:
        candidates = [a for a in app.actions if a.kind == kind]
        if not candidates:
            return _fail(f"{app.id} has no '{kind}' action", code=2)
        name = candidates[0].name
    if app.action(name) is None:
        known = ", ".join(a.name for a in app.actions) or "none"
        return _fail(f"unknown action '{name}' for {app.id} (available: {known})", code=2)
    return app, name


def _cmd_run(args) -> int:
    resolved = _resolve(args, "run")
    if isinstance(resolved, int):
        return resolved
    app, name = resolved
    runner_mod = _load_runner()
    try:
        result = runner_mod.run_action(app.id, name, root=discovery.hub_root(args.root))
    except runner_mod.RunnerError as e:
        return _fail(str(e))
    out = result.get("output", "")
    if out:
        print(out, file=sys.stdout if result["ok"] else sys.stderr)
    if result["ok"]:
        return 0
    return _fail(f"{app.id} {name} failed (exit {result.get('exit_code')})")


def _cmd_start(args) -> int:
    resolved = _resolve(args, "serve")
    if isinstance(resolved, int):
        return resolved
    app, name = resolved
    runner_mod = _load_runner()
    try:
        result = runner_mod.start(app.id, name, root=discovery.hub_root(args.root))
    except runner_mod.RunnerError as e:
        return _fail(str(e))
    print(f"started {app.id}/{name} (pid {result['pid']}), log: {result['log']}")
    print("tip: `plumbcenter ps` shows the URL once the app prints it")
    return 0


def _cmd_stop(args) -> int:
    resolved = _resolve(args, "serve")
    if isinstance(resolved, int):
        return resolved
    app, name = resolved
    runner_mod = _load_runner()
    try:
        runner_mod.stop(app.id, name)
    except runner_mod.RunnerError as e:
        return _fail(str(e))
    print(f"stopped {app.id}/{name}")
    return 0


def _cmd_ps(args) -> int:
    runner_mod = _load_runner()
    procs = runner_mod.status()
    if args.json:
        print(json.dumps(procs, indent=2))
        return 0
    if not procs:
        print("no running apps")
        return 0
    rows = [[p["app"], p["action"], str(p["pid"]), p.get("url") or "-", p.get("log") or "-"] for p in procs]
    print(_table(["app", "action", "pid", "url", "log"], rows))
    return 0


def _cmd_logs(args) -> int:
    resolved = _resolve(args, "serve")
    if isinstance(resolved, int):
        return resolved
    app, name = resolved
    print(_load_runner().tail_log(app.id, name))
    return 0


def _cmd_open(args) -> int:
    app = get_app(args.app)
    if app is None:
        return _fail(f"unknown app: {args.app}", code=2)
    runner_mod = _load_runner()
    try:
        result = runner_mod.open_app(app.id, root=discovery.hub_root(args.root))
    except runner_mod.RunnerError as e:
        return _fail(str(e))
    if not result.get("opened"):
        return _fail(f"{app.id} is not installed; nothing to open")
    print(f"opened {result['opened']}")
    return 0


def _cmd_gui(args) -> int:
    """Launch the native desktop hub. The web `serve` command stays until the GUI is accepted."""
    try:
        from .gui.app import main as gui_main
    except Exception as exc:
        return _fail(f"GUI is not available: {exc}")
    try:
        code = gui_main()
    except Exception as exc:
        return _fail(str(exc))
    return int(code or 0)


def _provider_row(cfg) -> dict:
    """Public provider fields. Never includes an API key."""
    return {
        "id": cfg.id,
        "name": cfg.name,
        "kind": cfg.kind,
        "enabled": bool(cfg.enabled),
        "has_key": bool(cfg.has_key),
        "base_url": cfg.base_url,
        "default_model": cfg.default_model,
        "needs_key": bool(cfg.needs_key),
    }


def _cmd_providers_list(args) -> int:
    from .providers.store import ProviderError, ProviderStore

    try:
        rows = [_provider_row(cfg) for cfg in ProviderStore().list()]
    except ProviderError as exc:
        return _fail(str(exc))
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    headers = ["id", "name", "enabled", "key", "model", "base_url"]
    table_rows = []
    for row in rows:
        table_rows.append([
            row["id"],
            row["name"],
            "yes" if row["enabled"] else "no",
            "saved" if row["has_key"] else ("n/a" if not row["needs_key"] else "no"),
            row["default_model"],
            row["base_url"],
        ])
    print(_table(headers, table_rows))
    return 0


def _cmd_providers_set_default(args) -> int:
    from .providers.store import ProviderError, ProviderStore

    raw = (args.provider or "").strip().lower()
    provider_id = None if raw in ("", "none", "-") else raw
    try:
        ProviderStore().set_default(args.app, provider_id)
    except ProviderError as exc:
        code = 2 if str(exc).startswith("unknown ") else 1
        return _fail(str(exc), code=code)
    if provider_id is None:
        print(f"default cleared: {args.app.strip().lower()}")
    else:
        print(f"default: {args.app.strip().lower()} -> {provider_id}")
    return 0


def _cmd_serve(args) -> int:
    web_mod = _load_web()
    try:
        web_mod.serve(host="127.0.0.1", port=args.port, root=discovery.hub_root(args.root))
    except OSError as e:
        return _fail(f"cannot start server on port {args.port}: {e}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="plumbcenter", description="PlumbCenter hub CLI")
    parser.add_argument("--root", dest="root", default=None, help="override hub root directory")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="list registered apps")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--remote", action="store_true", help="include GitHub stars/release (network)")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("info", help="show app info")
    p.add_argument("app", help="app id")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.set_defaults(func=_cmd_info)

    p = sub.add_parser("install", help="clone an app")
    p.add_argument("app", help="app id")
    p.set_defaults(func=_cmd_install)

    p = sub.add_parser("update", help="pull an app (or --all)")
    p.add_argument("app", nargs="?", help="app id (required unless --all)")
    p.add_argument("--all", action="store_true", help="update every installed app")
    p.set_defaults(func=_cmd_update)

    p = sub.add_parser("run", help="run an action (default: demo)")
    p.add_argument("app", help="app id")
    p.add_argument("action", nargs="?", default="demo", help="action name (default: demo)")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("start", help="start a serve action")
    p.add_argument("app", help="app id")
    p.add_argument("action", nargs="?", help="action name")
    p.set_defaults(func=_cmd_start)

    p = sub.add_parser("stop", help="stop a serve action")
    p.add_argument("app", help="app id")
    p.add_argument("action", nargs="?", help="action name")
    p.set_defaults(func=_cmd_stop)

    p = sub.add_parser("ps", help="list running processes")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.set_defaults(func=_cmd_ps)

    p = sub.add_parser("logs", help="tail an action log")
    p.add_argument("app", help="app id")
    p.add_argument("action", nargs="?", help="action name")
    p.set_defaults(func=_cmd_logs)

    p = sub.add_parser("open", help="open an app")
    p.add_argument("app", help="app id")
    p.set_defaults(func=_cmd_open)

    p = sub.add_parser("serve", help="start the web hub")
    p.add_argument("--port", type=int, default=8765, help="port (default: 8765)")
    p.set_defaults(func=_cmd_serve)

    p = sub.add_parser("gui", help="open the desktop hub")
    p.set_defaults(func=_cmd_gui)

    providers = sub.add_parser("providers", help="list providers or set a per-app default")
    providers_sub = providers.add_subparsers(dest="providers_command", required=True)
    p = providers_sub.add_parser("list", help="list providers (keys are never printed)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.set_defaults(func=_cmd_providers_list)
    p = providers_sub.add_parser("set-default", help="set or clear the default provider for an app")
    p.add_argument("app", help="app id")
    p.add_argument("provider", help="provider id, or 'none' to clear")
    p.set_defaults(func=_cmd_providers_set_default)

    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # app output may contain unicode; never crash the console
        except (AttributeError, ValueError):
            pass
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        return _fail(str(e))

