# PlumbCenter 1.0.0 release checklist

Tick each box before tagging `v1.0.0`. "Auto" items are covered by CI or `pytest`.

## Code and tests
- [x] Auto: `python -m pytest -q` green on Ubuntu and Windows (offscreen Qt, `.github/workflows/ci.yml`)
- [x] Auto: provider key never in `providers.json`, logs or exceptions (`tests/test_providers*.py`)
- [x] Auto: sibling apps read the shared `providers.json` (`tests/test_cross_app_sync.py`)
- [x] Auto: no local paths or personal emails in tracked text files (`tests/test_repo_hygiene.py`)
- [x] Screenshots regenerated from a neutral demo workspace (`scripts/capture_screenshots.py`)
- [x] Auto: inputs have accessible names, controls have tooltips (`tests/gui/test_accessible_names.py`)
- [ ] Manual: GUI opens at 100 %, 150 % and 200 % Windows scaling with no clipped text
- [ ] Manual: keyboard only: Tab through sidebar, cards, provider form; Ctrl+T toggles the theme
- [ ] Manual: screen reader (Narrator) reads sidebar, provider fields and the Test button

## Packaging (Windows)
- [ ] `powershell -File packaging/build.ps1` finishes; smoke test prints `Smoke test OK`
- [ ] `dist/PlumbCenter/PlumbCenter.exe` shows the Plumbnote icon and version 1.0.0 in Properties
- [ ] Zip SHA256 recorded in the GitHub release notes
- [ ] Run the exe on a clean user profile: no console window, keyring backend works

## Cross-app
- [ ] With real checkouts of PlumbGate, PlumbStudio, PlumbDoctor and PlumbScout: Apps page shows each as installed with a version
- [ ] Run demo from the hub for each app; set a default provider and confirm the app reads it from `~/.plumbnote/providers.json`
- [ ] PlumbCode shows as design stage with a default-provider chip and no launch button

## Provider probes (VERIFY before announcing)
- [ ] Kilo: `GET /models` is public, so a 200 does not prove the key. Test with a real key and document the result
- [ ] Z.ai: no models-list endpoint is documented; confirm the probe and the `glm-4.6` default against a live account
- [ ] PlumbScout does not read `providers.json` yet: ship as-is and say so, or add support first

## Repo hygiene
- [ ] `CHANGELOG.md` 1.0.0 entry matches what shipped; README screenshots current
- [ ] Legacy web hub (`web.py`, `static/`, `serve`) removed or explicitly kept for 1.0
- [ ] Tag `v1.0.0` on main after the release PR is merged (never push to main directly)
