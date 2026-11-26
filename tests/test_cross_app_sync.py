"""Cross-app contract: PlumbCenter discovers sibling Plumbnote apps, launches them, and
shares ~/.plumbnote/providers.json with them. The sibling "apps" here are tiny stubs that read
the file the way a real app would (plain json, no plumbcenter import)."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from plumbcenter import discovery, runner
from plumbcenter.providers.secrets import MemoryBackend
from plumbcenter.providers.store import ProviderStore

SENTINEL = "sk-sync-SENTINEL-0123456789"
SIBLINGS = ("plumbgate", "plumbstudio", "plumbdoctor", "plumbscout")  # apps with a demo action

STUB = (
    "import json, os, pathlib\n"
    "home = pathlib.Path(os.environ.get('PLUMBNOTE_HOME') or (pathlib.Path.home() / '.plumbnote'))\n"
    "data = json.loads((home / 'providers.json').read_text(encoding='utf-8'))\n"
    "print('APP=%s DEFAULT=%s VERSION=%s' % ({app!r}, data['defaults'].get({app!r}), data['version']))\n"
)


class CrossAppSyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.root, self.home = t / "apps", t / "plumbnote-home"
        for app in SIBLINGS + ("plumbcode",):
            (self.root / app / ".git").mkdir(parents=True)
        for app in SIBLINGS:
            (self.root / app / "demo").mkdir()
            (self.root / app / "demo" / "run.py").write_text(STUB.format(app=app), encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {
            "PLUMBNOTE_HOME": str(self.home), "PLUMBCENTER_STATE": str(t / "state")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.store = ProviderStore(home=self.home, secrets=MemoryBackend())

    def test_discovers_all_sibling_apps(self):
        found = {s.id: s for s in discovery.scan(self.root)}
        for app in SIBLINGS + ("plumbcode",):
            self.assertTrue(found[app].installed, app)
        self.assertFalse(found["plumbbridge"].installed)

    def test_siblings_read_shared_providers_json_without_key(self):
        self.store.configure("openai", api_key=SENTINEL, enabled=True, default_model="gpt-4.1-mini")
        self.store.configure("groq", api_key=SENTINEL + "-g", enabled=True)
        for i, app in enumerate(SIBLINGS + ("plumbcode",)):
            self.store.set_default(app, "openai" if i % 2 == 0 else "groq")
        for app in SIBLINGS:
            result = runner.run_action(app, "demo", root=self.root)
            self.assertTrue(result["ok"], result)
            expected = self.store.defaults()[app]
            self.assertIn(f"APP={app} DEFAULT={expected} VERSION=1", result["output"])
            self.assertNotIn(SENTINEL, result["output"])
        for p in self.home.rglob("*"):
            if p.is_file():
                self.assertNotIn(SENTINEL, p.read_text(encoding="utf-8", errors="replace"))

    def test_plumbcode_is_catalog_only_but_gets_a_default(self):
        self.store.set_default("plumbcode", "ollama")
        data = json.loads((self.home / "providers.json").read_text(encoding="utf-8"))
        self.assertEqual(data["defaults"]["plumbcode"], "ollama")
        with self.assertRaises(runner.RunnerError):
            runner.run_action("plumbcode", "demo", root=self.root)


if __name__ == "__main__":
    unittest.main()
