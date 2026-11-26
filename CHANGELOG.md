# Changelog

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
