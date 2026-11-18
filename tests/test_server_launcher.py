"""Local server and launcher tests (loopback only, providers faked). Run: python -m unittest discover tests"""
import json
import os
import socket
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import launcher  # noqa: E402
import refresh_data  # noqa: E402
import server  # noqa: E402


def req(port, path, method="GET", headers=None, host=None):
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method, headers=headers or {})
    if host:
        r.add_unredirected_header("Host", host)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._refresh = refresh_data.refresh
        refresh_data.refresh = lambda force=False, **kw: {"snapshot": {"sources": {}}, "run": {"at": "t", "forced": force,
                                                                                        "results": [], "problems": []}}
        cls.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        refresh_data.refresh = cls._refresh

    def test_health_identifies_app_and_folder(self):
        code, body = req(self.port, "/api/health")
        h = json.loads(body)
        self.assertEqual((code, h["app"], h["root"]), (200, "indian-macro-dashboard", server.project_root()))

    def test_refresh_requires_header_and_passes_force(self):
        self.assertEqual(req(self.port, "/api/refresh", "POST")[0], 403)
        code, body = req(self.port, "/api/refresh?force=1", "POST", {"X-Dashboard": "1"})
        self.assertEqual((code, json.loads(body)["run"]["forced"]), (200, True))
        code, body = req(self.port, "/api/refresh", "POST", {"X-Dashboard": "1"})
        self.assertFalse(json.loads(body)["run"]["forced"])

    def test_foreign_host_rejected(self):
        self.assertEqual(req(self.port, "/api/health", host="evil.example")[0], 403)

    def test_only_allowlisted_files_served(self):
        self.assertEqual(req(self.port, "/india_macro_dashboard_v5.html")[0], 200)
        for path in ("/refresh_data.py", "/data/server.log", "/data/../server.py", "/CLAUDE.md"):
            with self.subTest(path):
                self.assertEqual(req(self.port, path)[0], 404)

    def test_preflight_never_approved(self):
        self.assertEqual(req(self.port, "/api/refresh", "OPTIONS")[0], 405)

    def test_refresh_crash_returns_500_not_hang(self):
        def boom(force=False, **kw):
            raise RuntimeError("disk full")
        refresh_data.refresh = boom
        try:
            code, body = req(self.port, "/api/refresh", "POST", {"X-Dashboard": "1"})
        finally:
            refresh_data.refresh = lambda force=False, **kw: {"snapshot": {"sources": {}}, "run": {"at": "t", "forced": force,
                                                                                            "results": [], "problems": []}}
        self.assertEqual(code, 500)
        self.assertIn("disk full", json.loads(body)["error"])

    def test_port_cannot_be_shared(self):
        """Regression: http.server's default SO_REUSEADDR let two servers bind one port on Windows."""
        with self.assertRaises(OSError):
            server.Server(("127.0.0.1", self.port), server.Handler)


class LauncherTests(unittest.TestCase):
    def test_port_free_detects_bound_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen()
        try:
            self.assertFalse(launcher.port_free(s.getsockname()[1]))
        finally:
            s.close()

    def test_foreign_http_service_is_other_not_ours(self):
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def log_message(self, *a):
                pass
        httpd = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            self.assertEqual(launcher.health(httpd.server_address[1]), "other")
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_our_server_recognised_for_reuse(self):
        httpd = server.Server(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            h = launcher.health(httpd.server_address[1])
            self.assertIsInstance(h, dict)
            self.assertEqual(h["root"], launcher.root_id())
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
