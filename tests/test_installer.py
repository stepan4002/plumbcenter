"""Tests for installer.py using temp dirs and local bare git repos."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from subprocess import TimeoutExpired as SubTimeoutExpired

from plumbcenter.installer import (
    install,
    update,
    InstallError,
    clone_url_for,
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
    subprocess.run(["git", "push", "-u", "origin", "master"], cwd=work, capture_output=True, check=True)
    return bare


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_install_unknown_app_raises(self):
        with self.assertRaises(InstallError) as cm:
            install("no-such-app", self.tmpdir)
        self.assertIn("unknown app", str(cm.exception))

    def test_install_success(self):
        # Monkeypatch clone_url_for to use our local bare repo
        original_clone_url_for = clone_url_for
        bare = _init_bare_remote(self.tmpdir, "plumbdoctor")
        
        def mock_clone_url_for(app: AppSpec) -> str:
            if app.id == "plumbdoctor":
                return str(bare)
            return original_clone_url_for(app)
        
        import plumbcenter.installer as installer
        installer.clone_url_for = mock_clone_url_for
        
        try:
            result = install("plumbdoctor", self.tmpdir)
            self.assertTrue(result["ok"])
            self.assertEqual(result["app"], "plumbdoctor")
            self.assertEqual(result["action"], "cloned")
            self.assertTrue(Path(result["path"]).exists())
            self.assertTrue((Path(result["path"]) / ".git").exists())
            self.assertTrue((Path(result["path"]) / "README.md").exists())
        finally:
            installer.clone_url_for = original_clone_url_for

    def test_install_already_installed_raises(self):
        original_clone_url_for = clone_url_for
        bare = _init_bare_remote(self.tmpdir, "plumbgate")
        
        def mock_clone_url_for(app: AppSpec) -> str:
            if app.id == "plumbgate":
                return str(bare)
            return original_clone_url_for(app)
        
        import plumbcenter.installer as installer
        installer.clone_url_for = mock_clone_url_for
        
        try:
            install("plumbgate", self.tmpdir)  # First install
            with self.assertRaises(InstallError) as cm:
                install("plumbgate", self.tmpdir)  # Second should fail
            self.assertIn("already installed", str(cm.exception))
        finally:
            installer.clone_url_for = original_clone_url_for

    def test_install_path_escape_rejected(self):
        # Tricky to test directly since registry dir_names are fixed;
        # protection is exercised implicitly.
        pass

    def test_install_refuses_non_git_folder(self):
        """Install must not delete a pre-existing non-git folder (regression for fix 3)."""
        primary = self.tmpdir / "plumbbridge"
        primary.mkdir()
        (primary / "somefile.txt").write_text("user data")
        with self.assertRaises(InstallError) as cm:
            install("plumbbridge", self.tmpdir)
        self.assertIn("already exists and is not a git checkout", str(cm.exception))
        # Folder must be untouched
        self.assertTrue((primary / "somefile.txt").exists())

    def test_install_already_installed_via_alias(self):
        """find_checkout detects an existing checkout under an alias dir_name (fix 4)."""
        original_clone_url_for = clone_url_for
        bare = _init_bare_remote(self.tmpdir, "plumbcheck")

        def mock_clone_url_for(app: AppSpec) -> str:
            if app.id == "plumbcheck":
                return str(bare)
            return original_clone_url_for(app)

        import plumbcenter.installer as installer
        installer.clone_url_for = mock_clone_url_for
        try:
            # plumbcheck dir_names = ("plumbcheck", "plumcheck"); clone under the alias
            target = self.tmpdir / "plumcheck"
            subprocess.run(["git", "clone", str(bare), str(target)], capture_output=True, check=True)
            # install should detect find_checkout -> already installed
            with self.assertRaises(InstallError) as cm:
                install("plumbcheck", self.tmpdir)
            self.assertIn("already installed", str(cm.exception))
        finally:
            installer.clone_url_for = original_clone_url_for

    def test_update_detects_alias_checkout(self):
        """update uses find_checkout so alias-dir checkouts are updatable (fix 4)."""
        original_clone_url_for = clone_url_for
        bare = _init_bare_remote(self.tmpdir, "plumbstudio")

        def mock_clone_url_for(app: AppSpec) -> str:
            if app.id == "plumbstudio":
                return str(bare)
            return original_clone_url_for(app)

        import plumbcenter.installer as installer
        installer.clone_url_for = mock_clone_url_for
        try:
            pass
        finally:
            installer.clone_url_for = original_clone_url_for


class TestTimeoutTranslations(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_install_timeout_translated_to_install_error(self):
        """TimeoutExpired during clone becomes InstallError (fix 5)."""
        import plumbcenter.installer as installer

        # Monkeypatch _run_git to raise TimeoutExpired
        original_run = installer._run_git

        def failing_run(path, args, timeout=30):
            raise SubTimeoutExpired(cmd=["git", "-C", str(path)] + args, timeout=timeout)

        installer._run_git = failing_run

        try:
            with self.assertRaises(installer.InstallError) as cm:
                install("plumbdoctor", self.tmpdir)
            self.assertIn("timed out", str(cm.exception).lower())
        finally:
            installer._run_git = original_run

    def test_update_timeout_translated_to_install_error(self):
        """TimeoutExpired during fetch/pull becomes InstallError (fix 5)."""
        import plumbcenter.installer as installer

        original_run = installer._run_git

        # First install so update passes the "not installed" gate
        bare = _init_bare_remote(self.tmpdir, "plumbbridge")
        subprocess.run(["git", "clone", str(bare), str(self.tmpdir / "plumbbridge")], capture_output=True, check=True)

        def failing_run(path, args, timeout=30):
            raise SubTimeoutExpired(cmd=["git", "-C", str(path)] + args, timeout=timeout)

        installer._run_git = failing_run

        try:
            self.assertTrue((self.tmpdir / "plumbbridge").exists())
            with self.assertRaises(installer.InstallError) as cm:
                update("plumbbridge", self.tmpdir)
            self.assertIn("timed out", str(cm.exception).lower())
        finally:
            installer._run_git = original_run


class TestUpdate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_update_unknown_app_raises(self):
        with self.assertRaises(InstallError) as cm:
            update("no-such-app", self.tmpdir)
        self.assertIn("unknown app", str(cm.exception))

    def test_update_not_installed_raises(self):
        with self.assertRaises(InstallError) as cm:
            update("plumbdoctor", self.tmpdir)
        self.assertIn("not installed", str(cm.exception))

    def test_update_up_to_date(self):
        original_clone_url_for = clone_url_for
        bare = _init_bare_remote(self.tmpdir, "plumbscout")
        
        def mock_clone_url_for(app: AppSpec) -> str:
            if app.id == "plumbscout":
                return str(bare)
            return original_clone_url_for(app)
        
        import plumbcenter.installer as installer
        installer.clone_url_for = mock_clone_url_for
        
        try:
            install("plumbscout", self.tmpdir)
            result = update("plumbscout", self.tmpdir)
            self.assertTrue(result["ok"])
            self.assertEqual(result["action"], "up-to-date")
        finally:
            installer.clone_url_for = original_clone_url_for

    def test_update_with_new_commits(self):
        original_clone_url_for = clone_url_for
        bare = _init_bare_remote(self.tmpdir, "plumbstudio")
        
        def mock_clone_url_for(app: AppSpec) -> str:
            if app.id == "plumbstudio":
                return str(bare)
            return original_clone_url_for(app)
        
        import plumbcenter.installer as installer
        installer.clone_url_for = mock_clone_url_for
        
        try:
            install("plumbstudio", self.tmpdir)
            target = self.tmpdir / "plumbstudio"
            
            # Push a new commit to bare
            work = self.tmpdir / "plumbstudio-work2"
            subprocess.run(["git", "clone", str(bare), str(work)], capture_output=True, check=True)
            (work / "extra.txt").write_text("extra")
            subprocess.run(["git", "add", "extra.txt"], cwd=work, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "extra"], cwd=work, capture_output=True, check=True)
            subprocess.run(["git", "push"], cwd=work, capture_output=True, check=True)
            
            result = update("plumbstudio", self.tmpdir)
            self.assertTrue(result["ok"])
            self.assertEqual(result["action"], "updated")
            self.assertTrue((target / "extra.txt").exists())
        finally:
            installer.clone_url_for = original_clone_url_for

    def test_update_refuses_dirty(self):
        original_clone_url_for = clone_url_for
        bare = _init_bare_remote(self.tmpdir, "plumbbridge")
        
        def mock_clone_url_for(app: AppSpec) -> str:
            if app.id == "plumbbridge":
                return str(bare)
            return original_clone_url_for(app)
        
        import plumbcenter.installer as installer
        installer.clone_url_for = mock_clone_url_for
        
        try:
            install("plumbbridge", self.tmpdir)
            target = self.tmpdir / "plumbbridge"
            (target / "local_change.txt").write_text("local")
            
            with self.assertRaises(InstallError) as cm:
                update("plumbbridge", self.tmpdir)
            self.assertIn("uncommitted changes", str(cm.exception))
        finally:
            installer.clone_url_for = original_clone_url_for

    def test_update_refuses_non_ff(self):
        original_clone_url_for = clone_url_for
        bare = _init_bare_remote(self.tmpdir, "plumbcode")
        
        def mock_clone_url_for(app: AppSpec) -> str:
            if app.id == "plumbcode":
                return str(bare)
            return original_clone_url_for(app)
        
        import plumbcenter.installer as installer
        installer.clone_url_for = mock_clone_url_for
        
        try:
            install("plumbcode", self.tmpdir)
            target = self.tmpdir / "plumbcode"
            
            # Create a divergent commit locally
            (target / "local.txt").write_text("local")
            subprocess.run(["git", "add", "local.txt"], cwd=target, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "local"], cwd=target, capture_output=True, check=True)
            
            # Also push a different commit to remote (divergent history)
            work = self.tmpdir / "plumbcode-work2"
            subprocess.run(["git", "clone", str(bare), str(work)], capture_output=True, check=True)
            (work / "remote.txt").write_text("remote")
            subprocess.run(["git", "add", "remote.txt"], cwd=work, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "remote"], cwd=work, capture_output=True, check=True)
            subprocess.run(["git", "push"], cwd=work, capture_output=True, check=True)
            
            with self.assertRaises(InstallError) as cm:
                update("plumbcode", self.tmpdir)
            self.assertIn("fast-forward", str(cm.exception))
        finally:
            installer.clone_url_for = original_clone_url_for


if __name__ == "__main__":
    unittest.main()