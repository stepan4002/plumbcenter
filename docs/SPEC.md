# PlumbCenter MVP spec (OSS-CENTER-001)

Python 3.8+, **standard library only** (matches the sibling apps), tests with `unittest`
(`python -m unittest discover -s tests`). Windows is the primary platform; code must also
work on POSIX. Never use `shell=True`; always pass argv lists. `plumbcenter/registry.py` and
`plumbcenter/__init__.py` already exist; do not change their public shape (ask pc-orch).

## Roots
- `hub_root(override=None) -> Path` (in `discovery.py`): the directory that holds the app
  checkouts. Order: explicit override, env `PLUMBCENTER_HOME`, else the parent directory of
  this repo (siblings). App checkout = `hub_root / dir_name` for the first existing
  `dir_names` entry that is a directory containing `.git` (symlinks/junctions allowed).
- State dir: `state_dir()` (in `runner.py`) = env `PLUMBCENTER_STATE` or `<repo>/.plumbcenter/`
  (gitignored). Holds `processes.json` and `logs/<app>-<action>.log`.

## discovery.py (worker-1)
```python
@dataclass
class AppStatus:
    id: str; name: str; tagline: str; stage: str; repo: str; web_url: str
    installed: bool
    path: Optional[str]
    version: Optional[str]      # version_file "version" else `git describe --tags --always` else short sha
    branch: Optional[str]
    commit: Optional[str]       # short sha
    dirty: Optional[bool]       # uncommitted changes
    actions: List[str]          # action names available
    def to_dict(self) -> dict: ...

def hub_root(override: Optional[str] = None) -> Path
def find_checkout(app: AppSpec, root: Path) -> Optional[Path]
def scan(root: Optional[Path] = None) -> List[AppStatus]        # one per REGISTRY entry, registry order
def get_status(app_id: str, root=None) -> AppStatus             # KeyError for unknown id
def github_metadata(app: AppSpec, timeout=5.0, cache_ttl=600) -> dict
    # urllib GET https://api.github.com/repos/<repo> (+ /releases/latest). Returns
    # {"stars","latest_release","pushed_at","description","error"}; NEVER raises; on any
    # failure returns {"error": "..."} so the hub works fully offline. Cache to state dir.
def remote_state(path: Path, timeout=15) -> dict   # optional `git fetch` -> {"ahead","behind","error"}
```
git calls via `subprocess.run(["git", "-C", path, ...])` with a timeout, `GIT_TERMINAL_PROMPT=0`.

## installer.py (worker-1)
```python
class InstallError(Exception): ...
def install(app_id: str, root=None) -> dict   # git clone --depth? NO: full clone of app.clone_url into root/dir_names[0]
def update(app_id: str, root=None) -> dict    # git fetch + `git pull --ff-only`
```
Return `{"ok": True, "app": id, "path": ..., "action": "cloned|updated|up-to-date", "output": "..."}`.
Rules: only URLs from the registry are ever cloned (never user-supplied); `install` on an
already-installed app is a no-op error `InstallError("already installed")`; `update` refuses
when the work tree is dirty (message names the app) and when the pull is not fast-forward;
unknown id -> `InstallError`; `git` missing -> clear `InstallError`. Clone target must stay
inside `root` (reject path escapes). Tests use a **local bare repo** as the remote (monkeypatch
the clone URL via a module-level `clone_url_for(app)` hook) — no network in tests.

## runner.py (worker-2)
```python
class RunnerError(Exception): ...
def state_dir() -> Path
def run_action(app_id, action_name, root=None, timeout=120) -> dict
    # kind "run" only. -> {"ok": bool, "exit_code": int, "output": str(<=64KB tail), "duration_s": float}
    # ok = exit code in action.ok_exit_codes. Timeout -> ok False, exit_code -1, "timed out".
def start(app_id, action_name, root=None) -> dict
    # kind "serve" only. Detached child (Windows: CREATE_NEW_PROCESS_GROUP|DETACHED_PROCESS|CREATE_NO_WINDOW;
    # POSIX: start_new_session). stdout+stderr -> logs/<app>-<action>.log. Records pid, started_at,
    # argv in processes.json (atomic write). Already running -> RunnerError. Returns the status dict below.
def stop(app_id, action_name) -> dict            # kill the process tree (Windows: taskkill /T /F; POSIX: killpg), clear record
def status(app_id=None) -> List[dict]            # [{"app","action","pid","running","started_at","url","log"}]
    # prunes dead pids; `url` = first regex match of action.url_pattern in the log (or None)
def open_app(app_id) -> dict                     # open the served url (webbrowser) if running, else the app folder/README
def tail_log(app_id, action_name, lines=50) -> str
```
Rules: app must be installed (else `RunnerError("not installed")`), action must exist and
match the kind, every `requires` executable must resolve via `shutil.which` (clear error
otherwise); `{python}` -> `sys.executable`; the command runs with `cwd` = the checkout. The
registry argv is the only thing that is ever executed. PID liveness must be robust on
Windows (no `os.kill(pid, 0)`; use `tasklist`/ctypes `OpenProcess`). Tests use a throwaway
app dir plus a fake `AppSpec` (monkeypatch the registry lookup via a module-level
`get_app` import) with `{python} -c ...` actions, incl. a sleeping serve action that is
started, seen as running, then stopped.

## cli.py + `__main__.py` (worker-1, wave 2)
`python -m plumbcenter <command>` (also `plumbcenter.py` launcher at repo root is NOT needed).
Commands: `list` (table; `--json`), `info <app>`, `install <app>`, `update <app|--all>`,
`run <app> [action]` (default action `demo`), `start <app> [action]`, `stop <app> [action]`,
`ps`, `logs <app> [action]`, `open <app>`, `serve [--port 8765]`. Global `--root DIR`.
Exit codes: 0 ok, 1 command failed, 2 usage/unknown app. Errors print one line to stderr, no traceback.
`list` also shows GitHub stars/release only with `--remote` (default offline and fast).

## web.py + static UI (worker-2, wave 2)
`serve` runs `http.server.ThreadingHTTPServer` on **127.0.0.1 only**. Endpoints (JSON):
`GET /api/apps`, `GET /api/apps/<id>`, `GET /api/ps`, `GET /api/logs/<id>/<action>`,
`POST /api/apps/<id>/{install,update}`, `POST /api/apps/<id>/actions/<action>/{run,start,stop}`,
`POST /api/apps/<id>/open`. Security (it can clone/run things): reject any request whose
`Host` is not `127.0.0.1:<port>`/`localhost:<port>` (DNS rebinding); reject POSTs whose
`Origin` is present and not the server's own origin; POST requires header
`X-PlumbCenter: 1` (blocks simple cross-site forms); only registry ids/actions accepted;
no path traversal in static serving. Single-file UI at `plumbcenter/static/index.html`
(vanilla JS, no CDN, dark theme, cards per app: status badge, version/branch, buttons
Install/Update/Run demo/Start/Stop/Open/Logs). Auto-refreshes `/api/ps` every 3 s.
Tests call the handler against a real server on an ephemeral port.
