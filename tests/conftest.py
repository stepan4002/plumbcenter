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
