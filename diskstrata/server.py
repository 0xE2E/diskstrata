"""Local web server: 127.0.0.1 only. Every request needs the session cookie (handed out once
through the launch link) and a loopback Host header; state-changing calls also need an API
token, so neither another local account nor another web page can drive it."""
from __future__ import annotations

import json
import os
import secrets
import socket
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .jobs import JobRunner
from .platforms import common
from .platforms import current as plat
from .storage import WEB_DIR, Store, make_private_dir

TOKEN_MARK = 'window.DS_TOKEN = "";'
COOKIE = "ds_session"
MAX_BODY = 64 * 1024
CSP = ("default-src 'none'; script-src {script}; style-src 'unsafe-inline'; "
       "img-src 'self' data:; font-src data:; connect-src 'self'; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'")


def same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode(), b.encode())


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # POSIX: SO_REUSEADDR only lets a restart reclaim a port in TIME_WAIT (it never allows two
    # listeners). Windows: it would let another process share the port, so bind exclusively.
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class App:
    """Shared state behind the HTTP handlers."""

    def __init__(self, store: Store, secret: str | None = None) -> None:
        self.store = store
        self.runner = JobRunner(store)
        self.secret = secret or secrets.token_urlsafe(24)   # session cookie value
        self.token = secrets.token_urlsafe(16)              # API token injected into pages
        self._elevating = threading.Lock()

    def state(self) -> dict:
        return {"version": __version__, "os": plat.NAME, "elevated": plat.is_elevated(),
                "elevated_label": plat.ELEVATED_LABEL, "elevate_tip": plat.ELEVATE_TIP,
                "volumes": self.runner.volumes(), "history": self.store.history(),
                "job": self.runner.status()}

    def elevate(self, port: int) -> str | None:
        """Start an elevated copy on the same port. None on success, else an error message."""
        if plat.is_elevated():
            return "Already running with elevated rights."
        if self.runner.running:
            return "Cancel the running scan first."
        if not self._elevating.acquire(blocking=False):
            return "Waiting for the permission prompt."
        data = self.store.root.resolve()        # the elevated copy runs from another directory
        secret_file = data / f"elevate_{secrets.token_hex(4)}.secret"
        flag = data / f"elevate_{secrets.token_hex(4)}.flag"
        try:
            make_private_dir(data)
            fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:      # the new copy keeps the browser's session valid
                fh.write(self.secret)
            args = ["--port", str(port), "--home", common.home(), "--data-dir", str(data),
                    "--secret-file", str(secret_file), "--no-open"]
            return plat.relaunch_elevated(args, str(flag))
        finally:
            secret_file.unlink(missing_ok=True)
            flag.unlink(missing_ok=True)
            self._elevating.release()

    def reveal(self, path: str, select: bool) -> str | None:
        if not os.path.isabs(path) or path.startswith("\\\\") or not os.path.lexists(path):
            return "Path not found."            # also refuses network (UNC) paths
        if plat.NAME != "windows" and plat.is_elevated():
            return "Opening the file manager is not available while running as root."
        try:
            plat.reveal(path, select)
        except OSError as exc:
            return f"Could not open the file manager: {exc.strerror or exc}"
        return None


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "DiskStrata"

        def _send(self, code: int, body: bytes, ctype: str = "text/plain",
                  nonce: str | None = None, headers: dict[str, str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy",
                             CSP.format(script=f"'nonce-{nonce}'" if nonce else "'none'"))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: dict, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _page(self, html: str) -> None:
            nonce = secrets.token_urlsafe(12)       # only our own inline scripts may run
            html = html.replace(TOKEN_MARK, f'window.DS_TOKEN = "{app.token}";', 1)
            html = html.replace("<script", f'<script nonce="{nonce}"')
            self._send(200, html.encode(), "text/html", nonce)

        def _allowed(self) -> bool:
            """Loopback Host header (DNS-rebinding guard) and a valid session cookie."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost"):
                self._send(403, b"bad host")
                return False
            jar = SimpleCookie(self.headers.get("Cookie") or "")
            if COOKIE not in jar or not same(jar[COOKIE].value, app.secret):
                self._send(403, b"Open DiskStrata with the link printed in its terminal window.")
                return False
            return True

        def _stop_soon(self) -> None:
            threading.Thread(target=lambda: (time.sleep(0.4), self.server.shutdown()),
                             daemon=True).start()

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/" and "t" in query:        # launch link: trade the secret for a cookie
                if not same(query["t"][0], app.secret):
                    return self._send(403, b"bad link")
                cookie = f"{COOKIE}={app.secret}; Path=/; HttpOnly; SameSite=Strict"
                return self._send(303, b"", headers={"Location": "/", "Set-Cookie": cookie})
            if not self._allowed():
                return None
            if url.path == "/":
                return self._page((WEB_DIR / "app.html").read_text(encoding="utf-8"))
            if url.path == "/api/status":
                return self._json(app.runner.status())
            if url.path == "/api/state":
                return self._json(app.state())
            if url.path.startswith("/scan/"):
                html = app.store.read_report(url.path[len("/scan/"):])
                return self._page(html) if html else self._send(404, b"not found")
            if url.path == "/open":
                if not same(query.get("token", [""])[0], app.token):
                    return self._send(403, b"bad token")
                err = app.reveal(query.get("path", [""])[0], query.get("file", ["0"])[0] == "1")
                return self._send(400 if err else 200, (err or "ok").encode())
            return self._send(404, b"not found")

        def do_POST(self) -> None:  # noqa: N802
            if not self._allowed():
                return None
            if not same(self.headers.get("X-DS-Token") or "", app.token):
                return self._json({"ok": False, "error": "bad token"}, 403)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 <= n <= MAX_BODY:
                    return self._json({"ok": False, "error": "bad request size"}, 413)
                body = json.loads(self.rfile.read(n)) if n else {}
            except ValueError:
                return self._json({"ok": False, "error": "bad request"}, 400)
            path = urlparse(self.path).path
            if path == "/api/scan":
                ids = body.get("volumes") if isinstance(body, dict) else None
                if not isinstance(ids, list):
                    return self._json({"ok": False, "error": "volumes must be a list"}, 400)
                err = app.runner.start([str(v) for v in ids])
                return self._json({"ok": not err, "error": err}, 400 if err else 200)
            if path == "/api/cancel":
                app.runner.cancel()
                return self._json({"ok": True})
            if path == "/api/elevate":
                err = app.elevate(self.server.server_address[1])
                self._json({"ok": not err, "error": err})
                return None if err else self._stop_soon()   # frees the port for the new copy
            if path == "/api/quit":
                app.runner.cancel()
                self._json({"ok": True})
                return self._stop_soon()
            return self._json({"ok": False, "error": "unknown action"}, 404)

        def log_message(self, *args) -> None:
            pass
    return Handler


def bind(port: int | None, default_port: int, app: App) -> Server:
    """Explicit port: wait for it (the previous copy is shutting down). Otherwise try the
    default port, then any free one."""
    wanted = port or default_port
    deadline = time.monotonic() + (30 if port else 0)
    handler = make_handler(app)
    while True:
        try:
            return Server(("127.0.0.1", wanted), handler)
        except OSError:
            if time.monotonic() < deadline:
                time.sleep(0.4)
            elif port:
                raise SystemExit(f"Port {wanted} is busy.") from None
            else:
                wanted = 0              # let the OS pick
