"""Local server for the India + US Macro Dashboard (Python standard library only).

Started by launcher.py (via Open_Indian_Macro_Dashboard.cmd). Binds to 127.0.0.1 only.

Routes
  GET  /                         -> redirect to the dashboard
  GET  /india_macro_dashboard_v5.html, /data/macro_snapshot.js   (allow-listed static files)
  GET  /api/health               -> identifies this app + project folder (used to reuse an instance)
  GET  /api/snapshot             -> saved, validated snapshot (no provider calls)
  POST /api/refresh[?force=1]    -> refresh due sources via refresh_data.refresh(), return snapshot + run

Every page open or reload calls POST /api/refresh. Sources checked within their reuse window
are not re-requested (see refresh_data.SOURCES[...]['recheck_minutes']); the Refresh button
sends force=1, which re-checks everything not checked in the last 30 seconds.

Safety: requests must carry a Host of 127.0.0.1/localhost on our port (blocks DNS rebinding),
and POST /api/refresh needs the X-Dashboard header (a cross-site page cannot send it without a
CORS preflight, which this server never approves).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import refresh_data  # noqa: E402

APP_ID = "indian-macro-dashboard"
ENTRY = "india_macro_dashboard_v5.html"
STATIC = {
    "/" + ENTRY: (os.path.join(HERE, ENTRY), "text/html; charset=utf-8"),
    "/data/macro_snapshot.js": (refresh_data.OUT_PATH, "text/javascript; charset=utf-8"),
}
LOG_PATH = os.path.join(refresh_data.DATA_DIR, "server.log")
REFRESH_WAIT_S = 20   # a page gets finished sources within this; slower ones finish in the background
STARTED_AT = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
_last_request = time.monotonic()


def project_root() -> str:
    return os.path.normcase(os.path.realpath(HERE))


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}\n"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "IndianMacroDashboard/1"

    def log_message(self, fmt, *args):  # route http.server's access log to our file
        log(f"{self.address_string()} {fmt % args}")

    # ── helpers ──
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        return (self.headers.get("Host") or "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _guard(self) -> bool:
        global _last_request
        _last_request = time.monotonic()
        if not self._host_ok():
            self._json(403, {"error": "unexpected Host header"})
            return False
        return True

    # ── routes ──
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._guard():
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(302, b"", "text/plain", {"Location": "/" + ENTRY})
        elif path == "/api/health":
            self._json(200, {"app": APP_ID, "root": project_root(), "pid": os.getpid(),
                             "started_at": STARTED_AT, "entry": "/" + ENTRY})
        elif path == "/api/snapshot":
            sources, problems = refresh_data.read_snapshot()
            self._json(200, {"snapshot": {"schema_version": refresh_data.SCHEMA_VERSION, "sources": sources},
                             "problems": problems})
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif path in STATIC:
            fpath, ctype = STATIC[path]
            try:
                with open(fpath, "rb") as f:
                    body = f.read()
            except FileNotFoundError:
                if path.endswith(".js"):   # no snapshot yet: an empty but valid script, page shows baseline
                    body = b"// no snapshot yet\n"
                else:
                    self._json(404, {"error": "not found"})
                    return
            self._send(200, body, ctype)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._guard():
            return
        path, _, query = self.path.partition("?")
        if path != "/api/refresh":
            self._json(404, {"error": "not found"})
            return
        if self.headers.get("X-Dashboard") != "1":
            self._json(403, {"error": "missing X-Dashboard header"})
            return
        force = "force=1" in query.split("&")
        t0 = time.monotonic()
        try:
            out = refresh_data.refresh(force=force, wait_seconds=REFRESH_WAIT_S)
        except Exception as e:  # never leave the page hanging; report the failure
            log("refresh crashed: " + "".join(traceback.format_exception(e)))
            self._json(500, {"error": f"refresh failed: {type(e).__name__}: {e}"})
            return
        out["run"]["duration_ms"] = int((time.monotonic() - t0) * 1000)
        failed = [r["id"] for r in out["run"]["results"] if r["action"] == "failed"]
        log(f"refresh force={force} {out['run']['duration_ms']}ms failed={failed}")
        self._json(200, out)

    def do_OPTIONS(self):   # never approve cross-origin preflights
        self._json(405, {"error": "method not allowed"})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False   # http.server defaults to True; on Windows that lets 2 servers share a port

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):   # Windows: refuse to share the port
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8817)
    ap.add_argument("--idle-exit-hours", type=float, default=12.0,
                    help="exit after this long with no requests (0 = never)")
    args = ap.parse_args(argv)
    os.makedirs(refresh_data.DATA_DIR, exist_ok=True)
    try:   # keep the log small
        if os.path.getsize(LOG_PATH) > 1_000_000:
            os.replace(LOG_PATH, LOG_PATH + ".old")
    except OSError:
        pass
    try:
        httpd = Server(("127.0.0.1", args.port), Handler)
    except OSError as e:
        log(f"cannot bind 127.0.0.1:{args.port}: {e}")
        print(f"cannot bind 127.0.0.1:{args.port}: {e}", file=sys.stderr)
        return 2
    log(f"listening on 127.0.0.1:{args.port} pid={os.getpid()} root={HERE}")

    if args.idle_exit_hours > 0:
        def watchdog():
            while True:
                time.sleep(60)
                if time.monotonic() - _last_request > args.idle_exit_hours * 3600:
                    log("idle timeout; shutting down")
                    httpd.shutdown()
                    return
        threading.Thread(target=watchdog, daemon=True).start()
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
