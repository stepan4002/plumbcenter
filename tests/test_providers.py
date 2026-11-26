"""Provider store, secret redaction, and connection-probe tests. No network."""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from plumbcenter.providers.catalog import PROVIDERS, get_provider
from plumbcenter.providers.secrets import DpapiFileBackend, MemoryBackend
from plumbcenter.providers.store import ProviderStore
from plumbcenter.providers import tester

SENTINEL = "sk-test-SENTINEL"


class _Response:
    def __init__(self, status, body=b"{}"):
        self.status = status
        self._body = body

    def getcode(self):
        return self.status

    def read(self, _n=2048):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class ProviderStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.secrets = MemoryBackend()
        self.store = ProviderStore(home=self.home, secrets=self.secrets)

    def tearDown(self):
        self.tmp.cleanup()

    def _written_text(self):
        parts = []
        for path in self.home.rglob("*"):
            if path.is_file():
                parts.append(path.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(parts)

    def test_configure_never_writes_the_key(self):
        self.store.configure(
            "openai",
            api_key=SENTINEL,
            enabled=True,
            default_model="gpt-4.1-mini",
        )
        self.store.set_default("plumbdoctor", "openai")
        blob = self._written_text()
        self.assertNotIn(SENTINEL, blob)
        saved = json.loads((self.home / "providers.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["providers"]["openai"]["secret"], "keyring")
        self.assertEqual(saved["defaults"]["plumbdoctor"], "openai")
        self.assertEqual(self.store.get_key("openai"), SENTINEL)
        listed = {item.id: item for item in self.store.list()}
        self.assertTrue(listed["openai"].has_key)
        self.assertFalse(listed["ollama"].has_key)

    def test_clear_and_remove_drop_the_key(self):
        self.store.configure("groq", api_key=SENTINEL, enabled=True)
        self.store.clear_key("groq")
        self.assertIsNone(self.store.get_key("groq"))
        self.assertNotIn(SENTINEL, self._written_text())
        self.store.configure("groq", api_key=SENTINEL, enabled=True)
        self.store.remove("groq")
        self.assertIsNone(self.store.get_key("groq"))
        self.assertNotIn("groq", json.loads((self.home / "providers.json").read_text(encoding="utf-8"))["providers"])

    def test_cloud_http_url_is_rejected(self):
        with self.assertRaises(Exception):
            self.store.configure("openai", base_url="http://example.com/v1")
        self.assertFalse((self.home / "providers.json").exists())

    def test_catalog_ids(self):
        self.assertEqual(
            [item.id for item in PROVIDERS],
            ["openai", "anthropic", "gemini", "openrouter", "groq", "zai", "ollama", "kilo"],
        )
        self.assertIsNone(get_provider("missing"))


class DpapiRedactionTests(unittest.TestCase):
    def test_dpapi_file_does_not_contain_the_key(self):
        if os.name != "nt":
            self.skipTest("DPAPI is Windows-only")
        home = tempfile.mkdtemp()
        backend = DpapiFileBackend(home=home)
        backend.set("provider.openai", SENTINEL)
        raw = b"".join(path.read_bytes() for path in Path(home).rglob("*") if path.is_file())
        self.assertNotIn(SENTINEL.encode("utf-8"), raw)
        self.assertEqual(backend.get("provider.openai"), SENTINEL)


class TesterTests(unittest.TestCase):
    def _capture(self, spec_id, status=200, body=b"{}"):
        spec = get_provider(spec_id)
        seen = {}

        def fake_open(request, timeout):
            seen["url"] = request.full_url
            seen["headers"] = {k.lower(): v for k, v in request.header_items()}
            seen["timeout"] = timeout
            if status >= 400:
                raise urllib.error.HTTPError(request.full_url, status, "nope", {}, io.BytesIO(body))
            return _Response(status, body)

        opener = mock.Mock()
        opener.open.side_effect = fake_open
        with mock.patch.object(tester.urllib.request, "build_opener", return_value=opener):
            result = tester.test_connection(spec, SENTINEL, timeout=3)
        return result, seen

    def test_openai_uses_bearer_on_models(self):
        result, seen = self._capture("openai")
        self.assertTrue(result.ok)
        self.assertEqual(seen["url"], "https://api.openai.com/v1/models")
        self.assertEqual(seen["headers"]["authorization"], "Bearer " + SENTINEL)
        self.assertNotIn(SENTINEL, result.message)

    def test_anthropic_header_and_path(self):
        _result, seen = self._capture("anthropic")
        self.assertEqual(seen["url"], "https://api.anthropic.com/v1/models")
        self.assertEqual(seen["headers"]["x-api-key"], SENTINEL)
        self.assertEqual(seen["headers"]["anthropic-version"], "2023-06-01")
        self.assertNotIn("authorization", seen["headers"])

    def test_gemini_uses_goog_header_not_query(self):
        _result, seen = self._capture("gemini")
        self.assertEqual(seen["url"], "https://generativelanguage.googleapis.com/v1beta/models")
        self.assertEqual(seen["headers"]["x-goog-api-key"], SENTINEL)
        self.assertNotIn(SENTINEL, seen["url"])

    def test_openrouter_checks_the_key_endpoint(self):
        _result, seen = self._capture("openrouter")
        self.assertEqual(seen["url"], "https://openrouter.ai/api/v1/key")
        self.assertTrue(seen["headers"]["authorization"].startswith("Bearer "))

    def test_groq_ollama_zai_kilo_targets(self):
        _, groq = self._capture("groq")
        self.assertEqual(groq["url"], "https://api.groq.com/openai/v1/models")
        _, ollama = self._capture("ollama", status=200)
        self.assertEqual(ollama["url"], "http://127.0.0.1:11434/api/tags")
        self.assertNotIn("authorization", ollama["headers"])
        _, zai = self._capture("zai")
        self.assertEqual(zai["url"], "https://api.z.ai/api/paas/v4/models")
        result, kilo = self._capture("kilo")
        self.assertEqual(kilo["url"], "https://api.kilo.ai/api/gateway/models")
        self.assertIn("does not prove the key", result.message)
        self.assertNotIn(SENTINEL, result.message)

    def test_http_error_redacts_the_key(self):
        result, _seen = self._capture("openai", status=401, body=SENTINEL.encode("utf-8"))
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "401")
        self.assertNotIn(SENTINEL, result.message)

    def test_refuses_non_loopback_http(self):
        spec = get_provider("openai")
        result = tester.test_connection(spec, SENTINEL, base_url="http://evil.example/v1")
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "bad_url")
        self.assertNotIn(SENTINEL, result.message)

    def test_missing_key(self):
        result = tester.test_connection(get_provider("openai"), None)
        self.assertEqual(result.status, "no_key")

    def test_cross_host_redirect_is_not_followed(self):
        handler = tester._SameHostRedirect("api.openai.com")
        request = urllib.request.Request("https://api.openai.com/v1/models")
        new = handler.redirect_request(
            request, None, 302, "found", {}, "https://evil.example/steal",
        )
        self.assertIsNone(new)


if __name__ == "__main__":
    unittest.main()
