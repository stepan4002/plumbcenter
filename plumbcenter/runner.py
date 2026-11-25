"""Run and manage app actions (short-lived runs and detached serves)."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import AppSpec, get_app
from .discovery import hub_root, find_checkout

__all__ = ["RunnerError", "state_dir", "run_action", "start", "stop",
           "status", "open_app", "tail_log", "get_app"]


class RunnerError(Exception):
    pass


def state_dir() -> Path:
    env = os.environ.get("PLUMBCENTER_STATE")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent / ".plumbcenter"


def _processes_file() -> Path:
    return state_dir() / "processes.json"


def _load_procs() -> dict:
    p = _processes_file()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_procs(data: dict) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = _processes_file()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _key(app_id: str, action_name: str) -> str:
    return f"{app_id}:{action_name}"


_children: Dict[int, "subprocess.Popen"] = {}   # keeps POSIX children reapable (no zombies)


def _process_name(pid: int) -> Optional[str]:
    """Image name of a live process (Windows only), else None."""
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10)
        for row in csv.reader(out.stdout.splitlines()):
            if len(row) >= 2 and row[1].strip() == str(pid):
                return row[0].lower()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _is_alive(pid, exe: Optional[str] = None) -> bool:
    """True if `pid` is our still-running process. `exe` (basename) guards against PID reuse."""
    if not pid:
        return False
    if os.name == "nt":
        name = _process_name(int(pid))
        return name is not None and (not exe or name == exe.lower())
    child = _children.get(int(pid))
    if child is not None:
        if child.poll() is not None:
            _children.pop(int(pid), None)
            return False
        return True
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _check_installed(app: AppSpec, root) -> Path:
    r = root if root is not None else hub_root()
    checkout = find_checkout(app, Path(r))
    if checkout is None:
        raise RunnerError("not installed")
    return checkout


def _validate_action(app: AppSpec, action_name: str, kind: str):
    action = app.action(action_name)
    if action is None:
        raise RunnerError(f"unknown action: {action_name}")
    if action.kind != kind:
        raise RunnerError(f"action {action_name} is not {kind}")
    return action


def _build_argv(action) -> List[str]:
    """Registry argv with {python} expanded and the executable resolved to a full path."""
    for req in action.requires:
        if req != "python" and shutil.which(req) is None:
            raise RunnerError(f"missing required executable: {req}")
    argv = [sys.executable if tok == "{python}" else tok for tok in action.argv]
    if argv[0] != sys.executable:
        resolved = shutil.which(argv[0])
        if resolved is None:
            raise RunnerError(f"missing required executable: {argv[0]}")
        argv[0] = resolved
    return argv


def _child_env() -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_action(app_id, action_name, root=None, timeout=120):
    app = get_app(app_id.strip().lower() if isinstance(app_id, str) else app_id)
    if app is None:
        raise RunnerError(f"unknown app: {app_id}")
    checkout = _check_installed(app, root)
    action = _validate_action(app, action_name, "run")
    argv = _build_argv(action)
    start_t = time.time()
    try:
        proc = subprocess.run(
            argv, cwd=str(checkout), capture_output=True, encoding="utf-8", errors="replace",
            timeout=timeout, shell=False, env=_child_env(),
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        if len(output) > 65536:
            output = output[-65536:]
        duration = time.time() - start_t
        ok = proc.returncode in (action.ok_exit_codes or (0,))
        return {
            "ok": bool(ok),
            "exit_code": int(proc.returncode),
            "output": output,
            "duration_s": float(duration),
        }
    except subprocess.TimeoutExpired as e:
        output = ""
        if e.stdout:
            output += e.stdout if isinstance(e.stdout, str) else e.stdout.decode("utf-8", "replace")
        if e.stderr:
            output += e.stderr if isinstance(e.stderr, str) else e.stderr.decode("utf-8", "replace")
        if len(output) > 65536:
            output = output[-65536:]
        return {
            "ok": False,
            "exit_code": -1,
            "output": output + "\ntimed out" if output else "timed out",
            "duration_s": float(time.time() - start_t),
        }


def start(app_id, action_name, root=None):
    app = get_app(app_id.strip().lower() if isinstance(app_id, str) else app_id)
    if app is None:
        raise RunnerError(f"unknown app: {app_id}")
    checkout = _check_installed(app, root)
    action = _validate_action(app, action_name, "serve")
    argv = _build_argv(action)

    procs = _load_procs()
    k = _key(app.id, action.name)
    if k in procs:
        rec = procs[k]
        if _is_alive(rec.get("pid", 0), rec.get("exe")):
            raise RunnerError("already running")
        # stale: remove
        del procs[k]

    state_dir().mkdir(parents=True, exist_ok=True)
    logs_dir = state_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{app.id}-{action.name}.log"
    # truncate
    log_path.write_text("", encoding="utf-8")

    env = _child_env()
    with open(log_path, "ab") as lf:
        if os.name == "nt":
            creationflags = 0x00000200 | 0x00000008 | 0x08000000  # NEW_PROCESS_GROUP | DETACHED | NO_WINDOW
            proc = subprocess.Popen(
                argv, cwd=str(checkout), stdout=lf, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=creationflags, shell=False, env=env,
            )
        else:
            proc = subprocess.Popen(
                argv, cwd=str(checkout), stdout=lf, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, shell=False, env=env,
            )

    _children[proc.pid] = proc
    rec = {
        "exe": Path(argv[0]).name.lower(),
        "app": app.id,
        "action": action.name,
        "pid": proc.pid,
        "started_at": time.time(),
        "argv": argv,
        "log": str(log_path),
    }
    procs[k] = rec
    _save_procs(procs)

    return {
        "app": app.id,
        "action": action.name,
        "pid": proc.pid,
        "running": True,
        "started_at": rec["started_at"],
        "url": None,
        "log": str(log_path),
    }


def stop(app_id, action_name):
    app_id_n = app_id.strip().lower() if isinstance(app_id, str) else app_id
    procs = _load_procs()
    k = _key(app_id_n, action_name)
    rec = procs.get(k)
    if rec is None:
        return {"app": app_id_n, "action": action_name, "stopped": True}
    pid, exe = rec.get("pid"), rec.get("exe")
    if pid and _is_alive(pid, exe):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
        else:
            import signal
            for target in (lambda: os.killpg(pid, signal.SIGKILL), lambda: os.kill(pid, signal.SIGKILL)):
                try:
                    target()
                except (ProcessLookupError, PermissionError, OSError):
                    pass
        deadline = time.time() + 5
        while time.time() < deadline and _is_alive(pid, exe):
            time.sleep(0.1)
        if _is_alive(pid, exe):
            raise RunnerError(f"could not stop {app_id_n}:{action_name} (pid {pid}); record kept")
        child = _children.pop(int(pid), None)
        if child is not None:
            child.poll()  # reap so Popen does not warn about a running child
    if k in procs:
        del procs[k]
    _save_procs(procs)
    return {"app": app_id_n, "action": action_name, "stopped": True}


def status(app_id=None):
    procs = _load_procs()
    result = []
    changed = False
    for k, rec in list(procs.items()):
        if app_id is not None and rec.get("app") != (app_id.strip().lower() if isinstance(app_id, str) else app_id):
            continue
        pid = rec.get("pid")
        running = _is_alive(pid, rec.get("exe"))
        if not running:
            del procs[k]
            changed = True
            continue
        # url from log
        url = None
        log_path = rec.get("log")
        # find action url_pattern
        app = get_app(rec["app"])
        action = app.action(rec["action"]) if app else None
        if log_path and Path(log_path).is_file():
            try:
                text = Path(log_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            if action and action.url_pattern:
                m = re.search(action.url_pattern, text)
                if m:
                    url = m.group(0)
        result.append({
            "app": rec["app"],
            "action": rec["action"],
            "pid": pid,
            "running": True,
            "started_at": rec.get("started_at"),
            "url": url,
            "log": log_path,
        })
    if changed:
        _save_procs(procs)
    return result


def open_app(app_id, root=None):
    app_id_n = app_id.strip().lower() if isinstance(app_id, str) else app_id
    app = get_app(app_id_n)
    if app is None:
        raise RunnerError(f"unknown app: {app_id}")
    # if a served app is running, open its launch link (token included) or plain URL
    for rec in _load_procs().values():
        if rec.get("app") != app_id_n or not _is_alive(rec.get("pid"), rec.get("exe")):
            continue
        action = app.action(rec.get("action", ""))
        target = None
        for pattern in (action.launch_pattern if action else None, action.url_pattern if action else None):
            if pattern and rec.get("log") and Path(rec["log"]).is_file():
                m = re.search(pattern, Path(rec["log"]).read_text(encoding="utf-8", errors="replace"))
                if m:
                    target = m.group(0)
                    break
        if target:
            webbrowser.open(target)
            return {"opened": target.split("#")[0]}   # never echo the token
    # else open folder/readme
    checkout = find_checkout(app, Path(root) if root is not None else hub_root())
    if checkout:
        try:
            if os.name == "nt":
                os.startfile(str(checkout))  # type: ignore
            else:
                webbrowser.open(f"file://{checkout}")
            return {"opened": str(checkout)}
        except Exception:
            pass
    return {"opened": None}


def tail_log(app_id, action_name, lines=50):
    app_id_n = app_id.strip().lower() if isinstance(app_id, str) else app_id
    log_path = state_dir() / "logs" / f"{app_id_n}-{action_name}.log"
    if not log_path.is_file():
        return ""
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    parts = content.splitlines()
    return "\n".join(parts[-lines:])
