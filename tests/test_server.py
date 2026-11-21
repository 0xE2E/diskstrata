"""End-to-end: real HTTP server, real scan of a small temp tree."""
import json
import re
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

from diskstrata import server
from diskstrata.jobs import JobRunner
from diskstrata.storage import Store

MB = 1024 * 1024


def report_data(html: str) -> dict:
    return json.loads(re.search(r'id="ds-data"[^>]*>(.*?)</script>', html, re.S).group(1))


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "disk" / "sub").mkdir(parents=True)
        (root / "disk" / "sub" / "big.bin").write_bytes(b"z" * MB)
        cls.vol = {"id": "T", "root": str(root / "disk"), "name": "Test", "fs": "test",
                   "kind": "Local disk", "total": 100 * MB, "used": 10 * MB, "free": 90 * MB,
                   "is_system": False}
        cls.app = server.App(Store(root / "data"))
        cls.app.runner = JobRunner(cls.app.store, list_volumes=lambda: [cls.vol])
        cls.httpd = server.Server(("127.0.0.1", 0), server.make_handler(cls.app))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, token=True, host=None, cookie=True, headers=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        hdrs = {"Host": host or f"127.0.0.1:{self.port}", **(headers or {})}
        if token:
            hdrs["X-DS-Token"] = self.app.token
        if cookie:
            hdrs["Cookie"] = f"{server.COOKIE}={self.app.secret}"
        conn.request(method, path, json.dumps(body) if body is not None else None, hdrs)
        resp = conn.getresponse()
        data = resp.read().decode()
        conn.close()
        return resp, data

    def scan_and_wait(self):
        resp, data = self.call("POST", "/api/scan", {"volumes": ["T"]})
        self.assertEqual(resp.status, 200, data)
        deadline = time.time() + 30
        while time.time() < deadline:
            status = json.loads(self.call("GET", "/api/status")[1])
            if status["state"] != "running":
                return status
            time.sleep(0.1)
        raise TimeoutError("scan did not finish")

    def test_pages_carry_the_token_and_security_headers(self):
        resp, html = self.call("GET", "/")
        self.assertIn(f'window.DS_TOKEN = "{self.app.token}"', html)
        csp = resp.getheader("Content-Security-Policy")
        nonce = re.search(r"script-src 'nonce-([\w-]+)'", csp).group(1)
        self.assertNotIn("unsafe-inline'; style", csp)             # scripts are nonce-only
        self.assertEqual(html.count("<script"), html.count(f'<script nonce="{nonce}"'))
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")

    def test_every_request_needs_the_session_cookie(self):
        for path in ("/", "/api/state", "/api/status"):
            self.assertEqual(self.call("GET", path, cookie=False)[0].status, 403, path)
        resp, _ = self.call("GET", "/api/state", cookie=False,
                            headers={"Cookie": f"{server.COOKIE}=wrong"})
        self.assertEqual(resp.status, 403)
        resp, _ = self.call("POST", "/api/cancel", {}, cookie=False)
        self.assertEqual(resp.status, 403)

    def test_launch_link_sets_a_strict_http_only_cookie(self):
        resp, _ = self.call("GET", f"/?t={self.app.secret}", cookie=False)
        self.assertEqual(resp.status, 303)
        self.assertEqual(resp.getheader("Location"), "/")
        cookie = resp.getheader("Set-Cookie")
        self.assertIn(f"{server.COOKIE}={self.app.secret}", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertEqual(self.call("GET", "/?t=wrong", cookie=False)[0].status, 403)

    def test_malformed_requests_are_rejected_cleanly(self):
        self.assertEqual(self.call("POST", "/api/scan", {"volumes": 5})[0].status, 400)
        self.assertEqual(self.call("POST", "/api/scan", {"volumes": "T"})[0].status, 400)
        resp, _ = self.call("POST", "/api/scan", headers={"Content-Length": "-5"})
        self.assertIn(resp.status, (400, 413))
        resp, _ = self.call("POST", "/api/cancel", token=False, headers={"X-DS-Token": "caf\xe9"})
        self.assertEqual(resp.status, 403)

    def test_foreign_host_is_rejected(self):
        self.assertEqual(self.call("GET", "/api/state", host="evil.example")[0].status, 403)

    def test_actions_need_the_token(self):
        resp, _ = self.call("POST", "/api/scan", {"volumes": ["T"]}, token=False)
        self.assertEqual(resp.status, 403)
        self.assertEqual(self.call("GET", f"/open?path={self.tmp.name}")[0].status, 403)

    def test_unknown_volume_is_rejected(self):
        resp, data = self.call("POST", "/api/scan", {"volumes": ["nope"]})
        self.assertEqual(resp.status, 400)
        self.assertFalse(json.loads(data)["ok"])

    def test_full_scan_produces_one_report_with_growth_on_the_second_run(self):
        first = self.scan_and_wait()
        self.assertEqual((first["state"], first["errors"]), ("done", []))
        resp, html = self.call("GET", f"/scan/{first['scan']}")
        self.assertEqual(resp.status, 200)
        self.assertIn(f'window.DS_TOKEN = "{self.app.token}"', html)
        data = report_data(html)
        vol = data["volumes"][0]
        self.assertEqual(data["meta"]["version"], server.__version__)
        self.assertEqual((vol["id"], vol["scan"]["files"]), ("T", 1))
        self.assertGreaterEqual(vol["scan"]["size"], MB)
        self.assertIsNone(vol["prev"])
        time.sleep(1.1)                                 # scan ids have one-second resolution
        second = self.scan_and_wait()
        html2 = self.call("GET", f"/scan/{second['scan']}")[1]
        self.assertEqual(report_data(html2)["volumes"][0]["prev"], first["scan"])
        history = json.loads(self.call("GET", "/api/state")[1])["history"]
        self.assertEqual([h["id"] for h in history], [second["scan"], first["scan"]])

    def test_report_path_traversal_is_a_404(self):
        self.assertEqual(self.call("GET", "/scan/..%2F..%2Fsecret")[0].status, 404)

    def test_open_rejects_missing_paths(self):
        resp, _ = self.call("GET", f"/open?token={self.app.token}&path=/definitely/not/here")
        self.assertEqual(resp.status, 400)
        resp, _ = self.call("GET", f"/open?token={self.app.token}&path=%5C%5Chost%5Cshare")
        self.assertEqual(resp.status, 400)                  # network paths are refused

    def test_system_volume_report_has_every_section(self):
        runner = JobRunner(self.app.store, list_volumes=lambda: [{**self.vol, "is_system": True}])
        self.assertIsNone(runner.start(["T"]))
        while runner.running:
            time.sleep(0.1)
        status = runner.status()
        self.assertEqual(status["errors"], [])
        html = self.app.store.read_report(status["scan"])
        vol = report_data(html)["volumes"][0]
        for key in ("tree", "hotspots", "envs", "node_modules", "agents", "dotfolders",
                    "system", "programs", "big_files", "docs", "disk", "scan"):
            self.assertIn(key, vol)
        self.assertTrue(vol["is_system"])

    def test_port_is_not_shared_and_is_reclaimed_after_close(self):
        first = server.Server(("127.0.0.1", 0), server.make_handler(self.app))
        port = first.server_address[1]
        other = server.bind(None, port, self.app)       # default port busy: falls back
        self.assertNotEqual(other.server_address[1], port)
        other.server_close()
        threading.Timer(0.8, first.server_close).start()
        t0 = time.monotonic()
        second = server.bind(port, 0, self.app)         # explicit port: waits for the old copy
        self.assertGreater(time.monotonic() - t0, 0.5)
        self.assertEqual(second.server_address[1], port)
        second.server_close()

    def test_successful_launch_leaves_the_secret_for_the_new_copy_to_consume(self):
        # Windows' launcher returns as soon as the process starts, before it has read the file:
        # deleting it here would make the new copy invent its own secret and lose the session.
        with mock.patch.object(server.plat, "is_elevated", return_value=False), \
                mock.patch.object(server.plat, "relaunch_elevated", return_value=None):
            error = self.app.elevate(self.port)
        self.assertIsNone(error)
        leftovers = list(self.app.store.root.glob("elevate_*.secret"))
        self.assertEqual(len(leftovers), 1)
        self.assertEqual(leftovers[0].read_text(), self.app.secret)
        leftovers[0].unlink()

    def test_elevate_failure_is_reported_and_server_keeps_running(self):
        seen = {}

        def declined(args, announce):
            secret_file = Path(args[args.index("--secret-file") + 1])
            seen["secret"] = secret_file.read_text()        # handed over privately
            seen["data_dir_is_absolute"] = Path(args[args.index("--data-dir") + 1]).is_absolute()
            return "declined"

        with mock.patch.object(server.plat, "is_elevated", return_value=False), \
                mock.patch.object(server.plat, "relaunch_elevated", side_effect=declined):
            resp, data = self.call("POST", "/api/elevate", {})
        self.assertEqual(json.loads(data), {"ok": False, "error": "declined"})
        self.assertEqual(seen, {"secret": self.app.secret, "data_dir_is_absolute": True})
        self.assertEqual([p.name for p in self.app.store.root.glob("elevate_*")], [])  # cleaned up
        self.assertEqual(self.call("GET", "/api/status")[0].status, 200)


if __name__ == "__main__":
    unittest.main()
