"""Start (or reuse) the local dashboard server, wait until it is ready, open the browser.

Run by Open_Indian_Macro_Dashboard.cmd with pythonw (no console window). Errors are shown in
a Windows message box when there is no console, otherwise printed.

Port handling: tries 127.0.0.1 ports 8817-8826 in order.
  - A port answering /api/health as this app for this same folder  -> reuse it.
  - A port answering as anything else, or bound but silent            -> leave it alone, try next.
  - A free port                                                         -> start server.py there.
Unrelated processes are never stopped.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ID = "indian-macro-dashboard"
PORTS = range(8817, 8827)
READY_TIMEOUT_S = 15
LOG_PATH = os.path.join(HERE, "data", "server.log")


def open_browser(url: str) -> None:
    """MACRO_DASHBOARD_NO_BROWSER=1 (used by tests) prints the URL instead of opening a tab."""
    if os.environ.get("MACRO_DASHBOARD_NO_BROWSER") == "1":
        print("READY " + url)
    else:
        webbrowser.open(url)


def root_id() -> str:
    return os.path.normcase(os.path.realpath(HERE))


def notify(msg: str, error: bool = True) -> None:
    if sys.stdout is not None:          # console or redirected output (pythonw has none)
        print(msg, file=sys.stderr if error else sys.stdout)
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "Indian Macro Dashboard", 0x10 if error else 0x40)
    except Exception:
        pass


def health(port: int, timeout: float = 4.0) -> dict | None | str:
    """dict = a dashboard server answered; 'other' = something else is on the port; None = refused.
    Note: on Windows a refused localhost connection takes ~2s (SYN retries), so callers decide
    'free' with port_free() first and only probe ports that are actually bound."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data if isinstance(data, dict) and data.get("app") == APP_ID else "other"
    except (ConnectionRefusedError, urllib.error.URLError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ConnectionRefusedError) or "refused" in str(reason).lower():
            return None
        return "other"
    except Exception:
        return "other"


def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def python_for_server() -> str:
    """Prefer pythonw.exe next to the running interpreter so the server has no console window."""
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return pyw if os.path.exists(pyw) else exe


def start_server(port: int) -> subprocess.Popen:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    log = open(LOG_PATH, "a", encoding="utf-8")
    return subprocess.Popen([python_for_server(), os.path.join(HERE, "server.py"), "--port", str(port)],
                            cwd=HERE, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                            creationflags=flags, close_fds=True)


def wait_ready(port: int, proc: subprocess.Popen) -> bool:
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        h = None if port_free(port) else health(port, timeout=2.0)
        if isinstance(h, dict) and h.get("root") == root_id():
            return True
        if proc.poll() is not None:     # server exited (e.g. lost a race for the port)
            return False
        time.sleep(0.25)
    return False


def log_tail(n: int = 8) -> str:
    try:
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return "(no log)"


def main() -> int:
    if sys.version_info < (3, 9):
        notify(f"Python 3.9 or newer is required (found {sys.version.split()[0]}).")
        return 1
    others = []
    for port in PORTS:
        h = None if port_free(port) else health(port)
        if isinstance(h, dict):
            if h.get("root") == root_id():
                open_browser(f"http://127.0.0.1:{port}{h.get('entry', '/')}")
                return 0
            others.append(f"{port}: dashboard from another folder")
            continue
        if h is not None:
            others.append(f"{port}: in use by another program")
            continue
        proc = start_server(port)
        if wait_ready(port, proc):
            open_browser(f"http://127.0.0.1:{port}/india_macro_dashboard_v5.html")
            return 0
        if proc.poll() is None:
            notify(f"The dashboard server started on port {port} but did not become ready within "
                   f"{READY_TIMEOUT_S}s.\n\nLog ({LOG_PATH}):\n{log_tail()}")
            return 1
        others.append(f"{port}: server could not start")
    notify("Could not start the dashboard server: no usable port in 8817-8826.\n\n"
           + "\n".join(others) + f"\n\nLog ({LOG_PATH}):\n{log_tail()}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # pythonw has no console: always surface the failure
        notify(f"Launcher error: {type(e).__name__}: {e}")
        sys.exit(1)
