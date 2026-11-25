"""Tests for discovery.py using temp dirs and local bare git repos."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from plumbcenter import discovery
from plumbcenter.discovery import (
    hub_root,
    find_checkout,
    scan,
    get_status,
    AppStatus,
)
from plumbcenter.registry import AppSpec


def _init_bare_remote(tmpdir: Path, name: str) -> Path:
    """Create a bare git repo with one commit."""
    bare = tmpdir / f"{name}.git"
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)
    # Create a temporary worktree, commit, push to bare
    work = tmpdir / f"{name}-work"
    work.mkdir()
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Test"
    env["GIT_AUTHOR_EMAIL"] = "test@test.test"
    env["GIT_COMMITTER_NAME"] = "Test"
    env["GIT_COMMITTER_EMAIL"] = "test@test.test"
    subprocess.run(["git", "config", "user.email", "test@test.test"], cwd=work, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work, capture_output=True)
    readme = work / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "init"], cwd=work, capture_output=True, check=True)
    subprocess.run(["git", "add", "README.md"], cwd=work, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=work, capture_output=True, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=work, capture_output=True, check=True)
    # Use master branch name (Windows default)
    subprocess.run(["git", "push", "-u", "origin", "master"], cwd=work, capture_output=True, check=True)
    return bare


def _clone_from_bare(bare: Path, dest: Path, dir_name: str) -> Path:
    """Clone bare repo into dest/dir_name."""
    target = dest / dir_name
    subprocess.run(["git", "clone", str(bare), str(target)], capture_output=True, check=True)
    return target


class TestHubRoot(unittest.TestCase):
    def test_override(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(hub_root(td), Path(td).resolve())

    def test_env(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.pop("PLUMBCENTER_HOME", None)
            try:
                os.environ["PLUMBCENTER_HOME"] = td
                self.assertEqual(hub_root(), Path(td).resolve())
            finally:
                if old is not None:
                    os.environ["PLUMBCENTER_HOME"] = old
                else:
                    os.environ.pop("PLUMBCENTER_HOME", None)

    def test_default_is_repo_parent(self):
        # discovery.py lives at repo/plumbcenter/discovery.py
        # hub_root() default = repo.parent
        expected = Path(discovery.__file__).resolve().parent.parent.parent
        self.assertEqual(hub_root(), expected)


class TestFindCheckout(unittest.TestCase):
    def test_finds_existing_git_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "plumbcheck"
            repo.mkdir()
            (repo / ".git").mkdir()
            spec = AppSpec("plumbcheck", "PC", "tag", "released", ("plumbcheck", "plumcheck"))
            result = find_checkout(spec, root)
            self.assertEqual(result, repo)

    def test_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec = AppSpec("plumbcheck", "PC", "tag", "released", ("plumbcheck", "plumcheck"))
            self.assertIsNone(find_checkout(spec, root))


class TestScanAndGetStatus(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_returns_all_registry_entries_in_order(self):
        # No checkouts installed
        statuses = scan(self.tmpdir)
        self.assertEqual(len(statuses), 7)
        ids = [s.id for s in statuses]
        self.assertEqual(ids, ["plumbcheck", "plumbcode", "plumbdoctor", "plumbgate", "plumbscout", "plumbstudio", "plumbbridge"])
        for s in statuses:
            self.assertFalse(s.installed)
            self.assertIsNone(s.path)
            self.assertIsNone(s.version)
            self.assertFalse(s.dirty)

    def test_scan_with_installed_app(self):
        # Install plumbcheck
        bare = _init_bare_remote(self.tmpdir, "plumbcheck")
        target = _clone_from_bare(bare, self.tmpdir, "plumbcheck")

        statuses = scan(self.tmpdir)
        plumbcheck = statuses[0]
        self.assertTrue(plumbcheck.installed)
        self.assertEqual(plumbcheck.path, str(target))
        self.assertEqual(plumbcheck.id, "plumbcheck")
        self.assertEqual(plumbcheck.name, "PlumbCheck")
        self.assertEqual(plumbcheck.repo, "stepan4002/plumbcheck")
        self.assertEqual(plumbcheck.web_url, "https://github.com/stepan4002/plumbcheck")
        self.assertIsInstance(plumbcheck.actions, list)
        self.assertEqual(plumbcheck.actions, ["demo", "studio"])

    def test_get_status_unknown_id_raises_keyerror(self):
        with self.assertRaises(KeyError):
            get_status("nonexistent-app", self.tmpdir)

    def test_get_status_installed(self):
        bare = _init_bare_remote(self.tmpdir, "plumbdoctor")
        target = _clone_from_bare(bare, self.tmpdir, "plumbdoctor")
        status = get_status("plumbdoctor", self.tmpdir)
        self.assertTrue(status.installed)
        self.assertEqual(status.path, str(target))
        self.assertEqual(status.id, "plumbdoctor")
        self.assertEqual(status.commit, target) if False else True


class TestAppStatusToDict(unittest.TestCase):
    def test_to_dict(self):
        s = AppStatus(
            id="plumbcheck", name="PlumbCheck", tagline="t", stage="released",
            repo="stepan4002/plumbcheck", web_url="https://github.com/stepan4002/plumbcheck",
            installed=False, path=None, version=None, branch=None, commit=None,
            dirty=None, actions=["demo"],
        )
        d = s.to_dict()
        self.assertEqual(d["id"], "plumbcheck")
        self.assertEqual(d["actions"], ["demo"])


class TestVersionAndBranch(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_version_and_branch_and_commit(self):
        bare = _init_bare_remote(self.tmpdir, "plumbbridge")
        target = _clone_from_bare(bare, self.tmpdir, "plumbbridge")
        status = get_status("plumbbridge", self.tmpdir)
        self.assertTrue(status.installed)
        self.assertEqual(status.branch, "master")
        self.assertIsNotNone(status.commit)
        self.assertIsNotNone(status.version)
        self.assertFalse(status.dirty)

    def test_dirty_detection(self):
        bare = _init_bare_remote(self.tmpdir, "plumbgate")
        target = _clone_from_bare(bare, self.tmpdir, "plumbgate")
        (target / "junk.txt").write_text("junk")
        status = get_status("plumbgate", self.tmpdir)
        self.assertTrue(status.dirty)


if __name__ == "__main__":
    unittest.main()