"""Shared pytest setup: give git a committer identity so tests that build
throwaway repos work on CI runners that have no global git config."""
import os

for _k, _v in (
    ("GIT_AUTHOR_NAME", "PlumbCenter Tests"),
    ("GIT_AUTHOR_EMAIL", "tests@example.invalid"),
    ("GIT_COMMITTER_NAME", "PlumbCenter Tests"),
    ("GIT_COMMITTER_EMAIL", "tests@example.invalid"),
    ("GIT_CONFIG_NOSYSTEM", "1"),
):
    os.environ.setdefault(_k, _v)


import pytest


@pytest.fixture(autouse=True)
def _isolated_plumbnote_home(tmp_path_factory, monkeypatch):
    """Never let a test read or write the developer's real ~/.plumbnote (providers.json, settings.json)."""
    home = tmp_path_factory.mktemp("plumbnote_home_default")   # outside the test's own tmp_path
    monkeypatch.setenv("PLUMBNOTE_HOME", str(home))
