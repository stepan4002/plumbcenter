# Changelog

## 1.0.0 - 2026-11-26

### Added

- Native desktop hub for the seven Plumbnote apps (Apps, Providers, Settings, Diagnostics).
- Shared provider configuration in `~/.plumbnote/providers.json`. API keys stay in the OS keyring (DPAPI file fallback on Windows) and are never written to JSON.
- `runner.setup_venv` and `runner.health` for per-app virtualenvs and install checks.
- `discovery.self_status` for the hub checkout versus the GitHub latest release.
- CLI: `plumbcenter gui`, `plumbcenter providers list`, `plumbcenter providers set-default`.
- PyInstaller `build.ps1` and GitHub Actions CI (Ubuntu and Windows, offscreen Qt).

### Changed

- Package version is 1.0.0. Dependencies are PySide6-Essentials and keyring.
