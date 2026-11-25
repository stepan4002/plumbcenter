# PlumbCenter 1.0.0 — native desktop hub (V1-CENTER-001)

Branch: `feat/1.0-native-desktop`. **Do NOT push.** Commit locally in small conventional commits
(only files you own, see Ownership). Python 3.9+, **PySide6-Essentials (Qt 6)**, `keyring`.
**No webapp, no localhost browser UI, no QtWebEngine.** The existing Qt-free core
(`registry/discovery/installer/runner/cli`) stays Qt-free and its tests stay green.

## Product
Creative-Cloud-style desktop hub with a left sidebar: **Apps · Providers · Settings · Diagnostics**.

1. **Apps hub** — card grid for the 7 apps (PlumbCheck, PlumbCode, PlumbDoctor, PlumbGate,
   PlumbScout, PlumbStudio, PlumbBridge). Per card: stage + health + version badges, Install
   (clone), Update (fast-forward), Set up (create `.venv`, install requirements if present),
   Launch / Run demo, Stop, Live logs (dock/dialog, polls every 500 ms), Open folder, default
   AI provider chip. Long operations run off the UI thread (QThreadPool/QRunnable), with
   progress state and error toasts; the UI never blocks.
2. **AI Provider Setup Shop** — OpenAI, Anthropic, Google Gemini, OpenRouter, Groq, Z.ai,
   Ollama, Kilo. Per provider: enable, API key (masked field, never echoed back), base URL
   (editable for Ollama only, plus catalog default), default model, **Test connection**, and a
   per-Plumbnote-app default-provider matrix. Writes shared `~/.plumbnote/providers.json`.
3. **Settings & Diagnostics** — workspace root picker (native QFileDialog), dark/light theme
   toggle (persisted), self-update status (hub repo vs GitHub latest release), diagnostics
   page (python/git/node/keyring backend/Qt version, per-app health, copy-to-clipboard report).

## Provider contract (Qt-free, `plumbcenter/providers/`)
`~/.plumbnote/providers.json` (override dir with env `PLUMBNOTE_HOME`), atomic writes, UTF-8:
```json
{"version": 1,
 "providers": {"openai": {"enabled": true, "base_url": "https://api.openai.com/v1",
               "default_model": "gpt-4.1-mini", "secret": "keyring"}},
 "defaults": {"plumbcheck": "ollama", "plumbdoctor": "openai"}}
```
**The API key is never written to JSON, logs, QSettings, exceptions or test output.**
```python
# catalog.py
@dataclass(frozen=True) class ProviderSpec: id, name, kind("cloud"|"local"), base_url, key_env,
                                            needs_key, default_model, docs_url, test_kind
PROVIDERS: Tuple[ProviderSpec, ...]; def get_provider(id) -> Optional[ProviderSpec]
# secrets.py
class SecretBackend(Protocol): get(name)->Optional[str]; set(name, value); delete(name)
class KeyringBackend; class DpapiFileBackend (Windows ctypes CryptProtectData fallback, file in
PLUMBNOTE_HOME, per-user only); class MemoryBackend (tests); def default_backend()
# store.py
class ProviderStore(home=None, secrets=None):
    list() -> List[ProviderConfig]      # merged catalog + saved config; has_key: bool
    configure(id, api_key=None, base_url=None, default_model=None, enabled=None)
    clear_key(id); get_key(id) -> Optional[str]; remove(id)
    set_default(app_id, provider_id|None); defaults() -> Dict[str,str]
# tester.py
@dataclass class TestResult: ok, status, message, latency_ms
def test_connection(spec, api_key, base_url=None, timeout=10.0) -> TestResult
```
`test_connection`: cheap authenticated GET (models list) per provider, urllib only, HTTPS required
except loopback (Ollama `http://127.0.0.1:11434`), redirects not followed to other hosts, key sent
only to the configured provider host, key redacted from every message. **Verify each provider's
real endpoint/auth header from its official docs; do not guess** (Kilo and Z.ai especially; mark
anything unverified with a `# VERIFY` note and report it).

## Core additions (Qt-free, owned by core)
`runner.setup_venv(app_id, root=None) -> dict` (create `<app>/.venv`, `pip install -r
requirements.txt` if present, never run arbitrary scripts), `runner.health(app_id, root=None) ->
{"state": "ok|warn|error|missing", "reasons": [...]}` (installed, git clean?, required exe on PATH,
venv present), `discovery.self_status(root)`. The `serve` CLI command and `web.py`/`static/`/
`tests/test_web.py` are **removed** at the end (core manager, after the GUI works); CLI otherwise
unchanged. CLI gains `plumbcenter gui` and `plumbcenter providers list|set-default`.

## GUI layout (`plumbcenter/gui/`, owned by ui)
`app.py` (`main()`, QApplication, HiDPI, QSettings org "Plumbnote"/app "PlumbCenter"),
`mainwindow.py` (sidebar `QListWidget`/`QToolButton` column + `QStackedWidget`), `theme.py`
(QSS dark+light generated from one token table; Plumbnote accent #79ccf3), `pages/{apps,providers,
settings,diagnostics}.py`, `widgets/{app_card,provider_card,log_view,toast,badge}.py`,
`tasks.py` (QRunnable + signals wrapper), `icons.py`. Pages talk to core only through
`plumbcenter.*` modules; no business logic in widgets. Accessible: keyboard navigation, tooltips,
sufficient contrast in both themes.

## Packaging & repo hygiene (owned by core)
`pyproject.toml` (name `plumbcenter`, version `1.0.0`, MIT, deps `PySide6-Essentials>=6.6`,
`keyring>=24`; `[project.scripts] plumbcenter`, `[project.gui-scripts] plumbcenter-gui`; optional
`dev` extra: pytest, pyinstaller), `assets/plumbcenter.ico` + `.png` (generated, multi-size),
`build.ps1` (PyInstaller one-folder windowed build with the icon, outputs `dist/PlumbCenter/`,
zips it, prints SHA256), `.github/workflows/ci.yml` (ubuntu + windows, `QT_QPA_PLATFORM=offscreen`
pytest), `CHANGELOG.md` (1.0.0), `LICENSE` (MIT, Plumbnote), polished `README.md` (screenshots
optional), `docs/`.

## Tests
`pytest` (existing unittest tests keep working under pytest). GUI tests in `tests/gui/` run with
`QT_QPA_PLATFORM=offscreen`; use `MemoryBackend` and temp `PLUMBNOTE_HOME`; cover: main window
builds, sidebar navigation, app cards reflect a temp workspace, provider save/test (mocked HTTP)/
default assignment writes valid JSON **without the key**, theme toggle persists, a long task does
not block the event loop (QTest.qWait), settings round-trip. Providers/secret redaction have unit
tests incl. a test that greps every written file for the sentinel key.

## Ownership (no two agents edit the same file)
- **pc-mgr-ui**: `plumbcenter/gui/**`, `tests/gui/**`, `assets/**`, UX copy.
- **pc-mgr-core**: `plumbcenter/providers/**`, `tests/test_providers*.py`, `runner.py`,
  `discovery.py`, `installer.py`, `cli.py`, `registry.py`, `pyproject.toml`, `build.ps1`, CI,
  CHANGELOG, LICENSE, README, final QA + integration.
- Workers are assigned by the managers; every worker gets files from exactly one manager's list.
- pc-orch (me): this spec, coordination, final acceptance. Spec changes go through pc-orch.

## Rules
- Free-quota first: opencode workers use the configured free APIs (OpenAI free tier, Groq, Gemini
  free, Z.ai free, Ollama). If an agent hits a rate/usage limit or a sign-in wall (pc-worker-2/kilo
  currently does), the manager reassigns its work to another agent at once and tells pc-orch.
- Never ask the human for secrets; never put real keys anywhere. Tests use fake sentinel keys.
- Report to pc-orch with `herdr agent prompt pc-orch "<short status>"` at: design ready, GUI
  runnable, providers done, all green. Final report: test counts, `build.ps1` result, screenshots
  (offscreen `QWidget.grab()` PNGs saved in `docs/screenshots/`), known gaps.
- Done = `pytest` green (incl. offscreen GUI), `build.ps1` produces a launching exe, no push.
