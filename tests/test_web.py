import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from plumbcenter import web


class WebTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        cls.root = tmp / "apps"
        app = cls.root / "plumbdoctor"
        (app / ".git").mkdir(parents=True)          # enough for find_checkout
        (app / "demo").mkdir()
        (app / "demo" / "run.py").write_text("print('hello from demo')\n", encoding="utf-8")
        cls._old_state = os.environ.get("PLUMBCENTER_STATE")
        os.environ["PLUMBCENTER_STATE"] = str(tmp / "state")
        cls.server = web.make_server(port=0, root=cls.root)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if cls._old_state is None:
            os.environ.pop("PLUMBCENTER_STATE", None)
        else:
            os.environ["PLUMBCENTER_STATE"] = cls._old_state
        cls.tmp.cleanup()

    def call(self, method, path, headers=None, host=None):
        hdrs = {"Host": host or f"127.0.0.1:{self.port}"}
        hdrs.update(headers or {})
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method,
                                     headers=hdrs, data=b"" if method == "POST" else None)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def post(self, path, **kw):
        h = {"X-PlumbCenter": "1"}
        h.update(kw.pop("headers", {}))
        return self.call("POST", path, headers=h, **kw)


class TestApi(WebTestCase):
    def test_apps_shape(self):
        status, body, _ = self.call("GET", "/api/apps")
        self.assertEqual(status, 200)
        apps = json.loads(body)["apps"]
        self.assertEqual([a["id"] for a in apps][:2], ["plumbcheck", "plumbcode"])
        doctor = next(a for a in apps if a["id"] == "plumbdoctor")
        self.assertTrue(doctor["installed"])
        self.assertEqual(doctor["action_specs"][0]["name"], "demo")
        self.assertFalse(next(a for a in apps if a["id"] == "plumbgate")["installed"])

    def test_unknown_app_is_404(self):
        self.assertEqual(self.call("GET", "/api/apps/nope")[0], 404)
        self.assertEqual(self.post("/api/apps/nope/install")[0], 404)
        self.assertEqual(self.post("/api/apps/plumbdoctor/actions/evil/run")[0], 404)

    def test_run_demo(self):
        status, body, _ = self.post("/api/apps/plumbdoctor/actions/demo/run")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("hello from demo", data["output"])

    def test_run_on_uninstalled_app_is_400(self):
        status, body, _ = self.post("/api/apps/plumbgate/actions/demo/run")
        self.assertEqual(status, 400)
        self.assertIn("not installed", json.loads(body)["error"])

    def test_install_already_installed_is_400(self):
        status, body, _ = self.post("/api/apps/plumbdoctor/install")
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(body)["ok"])

    def test_ps_empty(self):
        self.assertEqual(json.loads(self.call("GET", "/api/ps")[1])["processes"], [])


class TestSecurity(WebTestCase):
    def test_bad_host_forbidden(self):
        self.assertEqual(self.call("GET", "/api/apps", host="evil.example:80")[0], 403)
        self.assertEqual(self.call("GET", "/", host=f"evil.example:{self.port}")[0], 403)

    def test_post_requires_header(self):
        self.assertEqual(self.call("POST", "/api/apps/plumbdoctor/actions/demo/run")[0], 403)

    def test_foreign_origin_forbidden(self):
        status, _, _ = self.post("/api/apps/plumbdoctor/actions/demo/run",
                                 headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)

    def test_own_origin_allowed(self):
        status, _, _ = self.post("/api/apps/plumbdoctor/actions/demo/run",
                                 headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)

    def test_static_traversal_blocked(self):
        for p in ("/..%2fregistry.py", "/%2e%2e/registry.py", "/../registry.py", "/nope.html", "/..\\registry.py"):
            self.assertEqual(self.call("GET", p)[0], 404, p)

    def test_static_served_with_csp(self):
        status, body, hdrs = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"PlumbCenter", body)
        self.assertIn("script-src 'self'", hdrs["Content-Security-Policy"])
        self.assertEqual(self.call("GET", "/app.js")[0], 200)

    def test_non_loopback_bind_refused(self):
        with self.assertRaises(ValueError):
            web.make_server(host="0.0.0.0", port=0)

    def test_unsupported_method(self):
        self.assertEqual(self.call("DELETE", "/api/apps")[0], 405)


if __name__ == "__main__":
    unittest.main()
