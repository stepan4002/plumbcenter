# Contributing to PlumbCenter

Thanks for helping. PlumbCenter is a native PySide6 desktop hub; the core (`plumbcenter/*.py`,
`plumbcenter/providers/`) has no Qt dependency and the GUI lives in `plumbcenter/gui/`.

## Setup

```sh
python -m pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen python -m pytest
```

Python 3.11. Tests need no network and no real API keys; use the sentinel `sk-test-SENTINEL` and a
temporary `PLUMBNOTE_HOME`.

## Workflow

1. **Never push to `main`.** Branch from an up-to-date `main`: `feat/…`, `fix/…`, `docs/…`.
2. Keep commits small, with [Conventional Commit](https://www.conventionalcommits.org/) messages
   (`feat:`, `fix:`, `docs:`, `test:`, `build:`, `refactor:`).
3. Open a pull request. CI (Ubuntu and Windows) must be green. PRs are squash-merged.
4. Add or update tests with the change, and a line in `CHANGELOG.md` under the unreleased heading.

## Rules the tests enforce

- No user-profile paths or personal email addresses in tracked text files (`tests/test_repo_hygiene.py`).
- API keys never reach `providers.json`, logs, or error text.
- GUI work that touches the network, subprocesses, or git runs off the UI thread (`gui/tasks.py`).
- In headless GUI tests do not use `QTest.qWait` while waiting for background work; it starves the thread
  pool. Pump with `app.processEvents()` and `time.sleep()` (see `tests/gui/test_hub_pages.py`).

## Cutting a release (maintainers)

1. Bump the version in **all three** places: `plumbcenter/__init__.py`, `pyproject.toml`, and
   `packaging/version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`).
   `tests/test_version_consistency.py` fails if they disagree.
2. Move the `CHANGELOG.md` entries under the new version and date.
3. Merge via PR, then tag the merge commit: `git tag v1.2.3 && git push origin v1.2.3`.
4. The `Release` workflow checks the tag against the package version, runs the tests, builds the exe,
   smoke-tests it, and publishes `PlumbCenter-<version>-win64.zip` and its `.sha256` to a GitHub Release.
5. Work through `docs/RELEASE-CHECKLIST.md` for the manual checks (high-DPI, screen reader, clean profile).

You can build locally with `packaging/build.ps1` (add `-SkipSmoke` to skip the launch test).

## Reporting security issues

See [SECURITY.md](SECURITY.md). Do not file them as public issues.
