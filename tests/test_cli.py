"""Tests for plumbcenter CLI (CLI tests)."""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

# Import the modules under test
import plumbcenter.cli as cli
import plumbcenter.discovery as discovery
import plumbcenter.installer as installer
import plumbcenter.registry as registry


class TestCLI(unittest.TestCase):
    def setUp(self):
        # Create a temporary hub root directory
        self.temp_dir = tempfile.mkdtemp()
        os.environ['PLUMBCENTER_HOME'] = self.temp_dir
        self.root = Path(self.temp_dir) / 'hub'
        self.root.mkdir(parents=True, exist_ok=True)

        # Create plumbdoctor with a .git and demo/run.py
        plumbdoctor_dir = self.root / 'plumbdoctor'
        plumbdoctor_dir.mkdir(parents=True, exist_ok=True)
        (plumbdoctor_dir / '.git').mkdir(parents=True, exist_ok=True)
        demo_dir = plumbdoctor_dir / 'demo'
        demo_dir.mkdir(exist_ok=True)
        (demo_dir / 'run.py').write_text('print("hello")\n', encoding='utf-8')

    def tearDown(self):
        # Clean up environment and temp directory
        os.environ.pop('PLUMBCENTER_HOME', None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _run_cli(self, args):
        """Run cli.main with given args and capture stdout/stderr."""
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exit_code = cli.main(args)
        return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()

    # -----------------------------------------------------------------
    # list command
    # -----------------------------------------------------------------
    def test_list_table_shows_all_apps(self):
        exit_code, stdout, _ = self._run_cli(['--root', str(self.root), 'list'])
        self.assertEqual(exit_code, 0)
        lines = [l for l in stdout.strip().splitlines() if l.strip()]
        # First line is header, second is separator, rest are data rows
        data_lines = lines[2:]
        self.assertEqual(len(data_lines), 7)
        ids = []
        for l in data_lines:
            parts = l.split()
            if parts:
                ids.append(parts[0])
        self.assertCountEqual(ids, ['plumbcheck', 'plumbcode', 'plumbdoctor', 'plumbgate', 'plumbscout', 'plumbstudio', 'plumbbridge'])

    def test_list_json_parses_and_has_correct_entries(self):
        exit_code, stdout, _ = self._run_cli(['--root', str(self.root), 'list', '--json'])
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 7)
        # plumbdoctor should be installed True, plumbgate installed False
        plumbdoctor_entry = next(e for e in data if e['id'] == 'plumbdoctor')
        plumbgate_entry = next(e for e in data if e['id'] == 'plumbgate')
        self.assertTrue(plumbdoctor_entry['installed'])
        self.assertFalse(plumbgate_entry['installed'])

    # -----------------------------------------------------------------
    # info command
    # -----------------------------------------------------------------
    def test_info_text_and_json(self):
        exit_code, stdout, _ = self._run_cli(['--root', str(self.root), 'info', 'plumbdoctor'])
        self.assertEqual(exit_code, 0)
        lines = stdout.strip().splitlines()
        self.assertIn('id:        plumbdoctor', lines)
        self.assertIn('installed: True', lines)

    def test_info_unknown_app_exits_2(self):
        exit_code, _, _ = self._run_cli(['--root', str(self.root), 'info', 'unknown-app'])
        self.assertEqual(exit_code, 2)

    # -----------------------------------------------------------------
    # run command
    # -----------------------------------------------------------------
    def test_run_plumbdoctor_success(self):
        exit_code, stdout, _ = self._run_cli(['--root', str(self.root), 'run', 'plumbdoctor'])
        self.assertEqual(exit_code, 0)
        self.assertIn('hello', stdout)

    def test_run_unknown_app_exits_2(self):
        exit_code, _, _ = self._run_cli(['--root', str(self.root), 'run', 'unknown-app'])
        self.assertEqual(exit_code, 2)

    def test_run_unknown_action_exits_2(self):
        exit_code, _, _ = self._run_cli(['--root', str(self.root), 'run', 'plumbdoctor', 'nonexistent-action'])
        self.assertEqual(exit_code, 2)

    def test_run_not_installed_plumbgate_exits_1_with_not_installed(self):
        exit_code, _, stderr = self._run_cli(['--root', str(self.root), 'run', 'plumbgate'])
        self.assertEqual(exit_code, 1)
        self.assertIn('not installed', stderr.lower())

    # -----------------------------------------------------------------
    # start command
    # -----------------------------------------------------------------
    def test_start_no_serve_action_exits_2(self):
        exit_code, _, stderr = self._run_cli(['--root', str(self.root), 'start', 'plumbdoctor'])
        self.assertEqual(exit_code, 2)
        self.assertIn("no 'serve' action", stderr)

    # -----------------------------------------------------------------
    # update command
    # -----------------------------------------------------------------
    def test_update_unknown_app_exits_2(self):
        exit_code, _, _ = self._run_cli(['--root', str(self.root), 'update', 'unknown-app'])
        self.assertEqual(exit_code, 2)

    def test_update_without_app_exits_2(self):
        # `update` with neither an app nor --all should exit 2 (unknown/missing app)
        exit_code, _, _ = self._run_cli(['--root', str(self.root), 'update'])
        self.assertEqual(exit_code, 2)

    def test_update_all_does_not_crash(self):
        # plumbdoctor is installed, so update should not crash
        exit_code, _, _ = self._run_cli(['--root', str(self.root), 'update', '--all'])
        self.assertNotEqual(exit_code, 2)  # no traceback/exit 2

    # -----------------------------------------------------------------
    # ps command
    # -----------------------------------------------------------------
    def test_ps_no_running_apps(self):
        exit_code, stdout, _ = self._run_cli(['--root', str(self.root), 'ps'])
        self.assertEqual(exit_code, 0)
        self.assertIn('no running apps', stdout.lower())

    # -----------------------------------------------------------------
    # install command
    # -----------------------------------------------------------------
    def test_install_already_installed(self):
        exit_code, _, _ = self._run_cli(['--root', str(self.root), 'install', 'plumbdoctor'])
        self.assertEqual(exit_code, 1)  # already installed error

    def test_providers_list_json_has_catalog_and_no_secrets(self):
        os.environ['PLUMBNOTE_HOME'] = str(self.temp_dir)
        try:
            exit_code, stdout, _ = self._run_cli(['providers', 'list', '--json'])
        finally:
            os.environ.pop('PLUMBNOTE_HOME', None)
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout)
        ids = [row['id'] for row in data]
        self.assertEqual(ids, [
            'openai', 'anthropic', 'gemini', 'openrouter', 'groq', 'zai', 'ollama', 'kilo',
        ])
        self.assertNotIn('sk-', stdout.lower())
        self.assertNotIn('api_key', stdout.lower())
        ollama = next(row for row in data if row['id'] == 'ollama')
        self.assertFalse(ollama['needs_key'])
        self.assertFalse(ollama['has_key'])

    def test_providers_set_default_round_trip(self):
        os.environ['PLUMBNOTE_HOME'] = str(self.temp_dir)
        try:
            exit_code, stdout, _ = self._run_cli(['providers', 'set-default', 'plumbcheck', 'ollama'])
            self.assertEqual(exit_code, 0)
            self.assertIn('plumbcheck -> ollama', stdout)
            written = (Path(self.temp_dir) / 'providers.json').read_text(encoding='utf-8')
            self.assertNotIn('sk-', written)
            exit_code, _, stderr = self._run_cli(['providers', 'set-default', 'nope', 'ollama'])
            self.assertEqual(exit_code, 2)
            self.assertIn('unknown app', stderr)
            exit_code, _, stderr = self._run_cli(['providers', 'set-default', 'plumbcheck', 'not-a-provider'])
            self.assertEqual(exit_code, 2)
            self.assertIn('unknown provider', stderr)
            exit_code, stdout, _ = self._run_cli(['providers', 'set-default', 'plumbcheck', 'none'])
            self.assertEqual(exit_code, 0)
            self.assertIn('default cleared', stdout)
            saved = json.loads((Path(self.temp_dir) / 'providers.json').read_text(encoding='utf-8'))
            self.assertNotIn('plumbcheck', saved['defaults'])
        finally:
            os.environ.pop('PLUMBNOTE_HOME', None)


# Entry point for unittest discovery
if __name__ == '__main__':
    unittest.main()