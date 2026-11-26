# Changelog

## Unreleased

### Added

- **Updates page**: checks GitHub Releases for PlumbCenter and the seven Plumbnote apps (`plumbcenter/updater.py`). One click updates an installed app (`git pull --ff-only`, refuses a dirty tree), installs a missing one, or downloads the hub's release zip and verifies its SHA-256. Downloads go only to GitHub hosts over HTTPS, are size-capped, and are never executed.
- **Processes page**: live table of apps started from the hub, with Stop, Restart, Open and a live log tail. New `runner.restart`.
- **Provider health card** on the Providers page: pings each enabled provider in parallel and shows latency, plus a quota line where the provider exposes one (OpenRouter). Other providers say "not exposed" rather than guessing.
- `.github/workflows/release.yml`: pushing a `vX.Y.Z` tag runs the tests, builds and smoke-tests the exe, and publishes the zip and a `.sha256` file to a GitHub Release.
- `CONTRIBUTING.md` and `SECURITY.md`.
- `packaging/build.ps1` reads the version from `plumbcenter/__init__.py` and writes a `.sha256` sidecar; `tests/test_version_consistency.py` keeps the version strings in sync.

### Changed

- Sidebar now has six pages (Ctrl+1 to Ctrl+6).

## 1.0.0 - 2026-11-26

### Added

- Native desktop hub for the seven Plumbnote apps (Apps, Providers, Settings, Diagnostics).
- Shared provider configuration in `~/.plumbnote/providers.json`. API keys stay in the OS keyring (DPAPI file fallback on Windows) and are never written to JSON.
- `runner.setup_venv` and `runner.health` for per-app virtualenvs and install checks.
- `discovery.self_status` for the hub checkout versus the GitHub latest release.
- CLI: `plumbcenter gui`, `plumbcenter providers list`, `plumbcenter providers set-default`.
- PyInstaller `packaging/build.ps1` with icon, version metadata and an exe launch smoke test (`--smoke-test`), plus GitHub Actions CI (Ubuntu and Windows, offscreen Qt).
- Cross-app tests: discovery, launch and shared `providers.json` for the sibling apps; the key never reaches the file or app output.
- Accessible names on every input and the theme toggle.
- `scripts/capture_screenshots.py` regenerates the docs screenshots from a neutral demo workspace.

### Changed

- Package version is 1.0.0. Dependencies are PySide6-Essentials and keyring.

### Removed

- The legacy local web hub: `plumbcenter serve`, `web.py`, `static/` and its tests. The hub is native-only. Per-app start and stop of registry `serve` actions (for example PlumbCheck Studio) is unchanged.

### Known limitations

- Kilo's `GET /models` is public, so a 200 does not prove the key is valid. Z.ai documents no models-list endpoint, so its test probes `GET /models` and the default model is `glm-4.6`.
- PlumbScout does not read `~/.plumbnote/providers.json` yet.
- The Windows build warns that optional Qt6WebEngine, Pdf and VirtualKeyboard DLLs are absent from PySide6-Essentials. The window launches; the hub uses none of them.
