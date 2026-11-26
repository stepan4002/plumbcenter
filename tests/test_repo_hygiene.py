"""Guard: tracked text files must not contain user-profile paths or personal emails."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BS = re.escape(chr(92))  # one literal backslash
PATTERN = re.compile(r"[A-Za-z]:" + BS + "Users" + BS + r"|[A-Za-z]:/Users/|/Users/[^/\s]+/|/home/[^/\s]+/|@gmail\.com|@outlook\.com")
TEXT = {".md", ".py", ".ps1", ".toml", ".yml", ".yaml", ".txt", ".json", ".cfg", ".ini"}


class HygieneTest(unittest.TestCase):
    def test_no_local_paths_or_personal_emails(self):
        try:
            files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                                   check=True).stdout.splitlines()
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("not a git checkout")
        bad = []
        for name in files:
            path = ROOT / name
            if name == "tests/test_repo_hygiene.py" or path.suffix.lower() not in TEXT or not path.is_file():
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if PATTERN.search(line):
                    bad.append(f"{name}:{n}")
        self.assertEqual(bad, [], "local path / personal email found")


if __name__ == "__main__":
    unittest.main()
