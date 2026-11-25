# PlumbCenter

**Central hub for all Plumbnote open-source apps.** Discover, install, update, run and stop
PlumbCheck, PlumbCode, PlumbDoctor, PlumbGate, PlumbScout, PlumbStudio and PlumbBridge from one
CLI or one local web page.

Pure Python 3.8+ standard library. No dependencies, nothing to `pip install`.

## Quick start

```sh
git clone https://github.com/stepan4002/plumbcenter && cd plumbcenter
python -m plumbcenter list          # catalog + install status
python -m plumbcenter serve         # web hub at http://127.0.0.1:8765/
```

Apps live as sibling folders of this repo (`../plumbdoctor`, `../plumbcheck`, ...). Use
`--root DIR` or the `PLUMBCENTER_HOME` environment variable to point at a different folder.
State (running processes, logs) is kept in `.plumbcenter/` (override with `PLUMBCENTER_STATE`).

## What it does

| Capability | CLI | Web UI |
|---|---|---|
| Discover & catalog: description, stage, installed?, version, branch, uncommitted changes, GitHub stars/release | `list [--json] [--remote]`, `info <app>` | cards, "Check GitHub" |
| Download / update from GitHub | `install <app>`, `update <app>` / `update --all` | Install / Update buttons |
| Run & control | `run <app> [demo]`, `start <app> [action]`, `stop <app> [action]`, `ps`, `logs <app>`, `open <app>` | Run demo / Start / Stop / Open / Logs |

Exit codes: `0` ok, `1` command failed, `2` usage error or unknown app. Errors are one line on stderr.

| App | Stage | Hub actions |
|---|---|---|
| PlumbCheck | released | `demo` (exits 1 by design, treated as success), `studio` (local web app) |
| PlumbDoctor, PlumbGate, PlumbScout, PlumbStudio, PlumbBridge | preview | `demo` (`python demo/run.py`) |
| PlumbCode | design | catalog only, nothing to run yet |

## Safety

- Only the registry in `plumbcenter/registry.py` is ever cloned or executed: never a user-supplied URL or command, never through a shell.
- `update` refuses a checkout with uncommitted changes and never merges (fast-forward only).
- The web hub binds to `127.0.0.1` only, rejects foreign `Host`/`Origin` headers, requires an `X-PlumbCenter` header on every POST, and serves a strict CSP.
- Logs can contain private launch links (PlumbCheck Studio prints a session token). `open` uses it; `ps` and the UI list never show it. Keep logs private.
- Process records remember the executable name, so a recycled PID is never killed by mistake.

## Adding an app

Add one `AppSpec` to `REGISTRY` in `plumbcenter/registry.py` (repo name, local folder names, actions).
Everything else, including the UI, picks it up.

## Layout

```
plumbcenter/registry.py    app catalog (data only)
plumbcenter/discovery.py   local scan, version/git state, GitHub metadata
plumbcenter/installer.py   clone / fast-forward update
plumbcenter/runner.py      run, start/stop, process table, logs
plumbcenter/cli.py         command line        plumbcenter/web.py + static/  web hub
docs/SPEC.md               module contracts
```

## Tests

```sh
python -m unittest discover -s tests
```

No network needed: git tests use a local bare repository as the remote.

Built by [Plumbnote](https://plumbnote.com).
