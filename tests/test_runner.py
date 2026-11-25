"""Tests for runner.py."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from plumbcenter.registry import AppSpec, Action
from plumbcenter import runner
from plumbcenter.runner import RunnerError


def _fake_app(checkout: Path) -> AppSpec:
    return AppSpec(
        id="fakeapp",
        name="Fake",
        tagline="t",
        stage="released",
        dir_names=("fakeapp",),
        actions=(
            Action("demo", "Run demo", "run", ("{python}", "-c", "print('hello')"), requires=("python",)),
            Action("serve", "Serve", "serve", ("{python}", "-c", "import time; print('http://127.0.0.1:9999', flush=True); time.sleep(30)"), url_pattern=r"http://127\.0\.0\.1:\d+", requires=("python",)),
        ),
    )


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "hub"
        self.root.mkdir()
        self.appdir = self.root / "fakeapp"
        self.appdir.mkdir()
        (self.appdir / ".git").mkdir()
        self.app = _fake_app(self.appdir)
        # monkeypatch get_app
        self._orig_get_app = runner.get_app
        runner.get_app = lambda aid: self.app if aid == "fakeapp" else None
        # state dir
        self.state = self.tmp / "state"
        os.environ["PLUMBCENTER_STATE"] = str(self.state)

    def tearDown(self):
        # stop any lingering
        try:
            runner.stop("fakeapp", "serve")
        except Exception:
            pass
        os.environ.pop("PLUMBCENTER_STATE", None)
        runner.get_app = self._orig_get_app
        shutil.rmtree(self.tmp, ignore_errors=True)
        # kill stray python sleepers
        pass

    def test_state_dir(self):
        self.assertEqual(runner.state_dir(), Path(os.environ["PLUMBCENTER_STATE"]).resolve())

    def test_run_action(self):
        r = runner.run_action("fakeapp", "demo", root=self.root)
        self.assertTrue(r["ok"])
        self.assertEqual(r["exit_code"], 0)
        self.assertIn("hello", r["output"])
        self.assertGreaterEqual(r["duration_s"], 0)

    def test_run_not_installed(self):
        empty = self.tmp / "emptyroot"
        empty.mkdir()
        with self.assertRaises(RunnerError):
            runner.run_action("fakeapp", "demo", root=empty)

    def test_run_timeout(self):
        app = AppSpec(
            id="fakeapp", name="Fake", tagline="t", stage="released",
            dir_names=("fakeapp",),
            actions=(Action("slow", "Slow", "run", ("{python}", "-c", "import time; time.sleep(10)"), requires=("python",)),),
        )
        self.app = app
        runner.get_app = lambda aid: app if aid == "fakeapp" else None
        r = runner.run_action("fakeapp", "slow", root=self.root, timeout=1)
        self.assertFalse(r["ok"])
        self.assertEqual(r["exit_code"], -1)
        self.assertIn("timed out", r["output"])

    def test_start_stop_status(self):
        res = runner.start("fakeapp", "serve", root=self.root)
        self.assertTrue(res["running"])
        pid = res["pid"]
        self.assertTrue(runner._is_alive(pid))
        # seen running
        st = runner.status()
        self.assertEqual(len(st), 1)
        self.assertTrue(st[0]["running"])
        # wait for url in log
        for _ in range(20):
            st = runner.status()
            if st and st[0].get("url"):
                break
            time.sleep(0.2)
        self.assertIsNotNone(st[0]["url"])
        # stop
        runner.stop("fakeapp", "serve")
        time.sleep(0.5)
        self.assertFalse(runner._is_alive(pid))
        self.assertEqual(runner.status(), [])

    def test_tail_log(self):
        runner.start("fakeapp", "serve", root=self.root)
        time.sleep(0.5)
        out = runner.tail_log("fakeapp", "serve")
        self.assertIn("http://127.0.0.1:9999", out)
        runner.stop("fakeapp", "serve")

    def test_already_running(self):
        runner.start("fakeapp", "serve", root=self.root)
        with self.assertRaises(RunnerError):
            runner.start("fakeapp", "serve", root=self.root)
        runner.stop("fakeapp", "serve")

    def test_wrong_kind(self):
        with self.assertRaises(RunnerError):
            runner.run_action("fakeapp", "serve", root=self.root)
        with self.assertRaises(RunnerError):
            runner.start("fakeapp", "demo", root=self.root)

    def test_missing_requires(self):
        app = AppSpec(
            id="fakeapp", name="Fake", tagline="t", stage="released",
            dir_names=("fakeapp",),
            actions=(Action("demo", "Run demo", "run", ("nonexistent_xyz",), requires=("nonexistent_xyz",)),),
        )
        runner.get_app = lambda aid: app if aid == "fakeapp" else None
        with self.assertRaises(RunnerError):
            runner.run_action("fakeapp", "demo", root=self.root)


if __name__ == "__main__":
    unittest.main()
