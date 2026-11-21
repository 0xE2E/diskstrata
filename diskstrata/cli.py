"""Command line entry point."""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import APP_NAME, __version__
from .platforms import common
from .platforms import current as plat
from .server import App, bind
from .storage import Store

DEFAULT_PORT = 8765


def _sudo_home() -> str | None:
    """Under `sudo`, analyse the invoking user's home, not root's."""
    user = os.environ.get("SUDO_USER")
    if user and hasattr(os, "geteuid") and os.geteuid() == 0:
        import pwd
        try:
            return pwd.getpwnam(user).pw_dir
        except KeyError:
            return None
    return None


def _read_secret(path: Path | None) -> str | None:
    """The elevating copy passes its session secret in a private file (not on the command line)."""
    if not path:
        return None
    try:
        return path.read_text().strip() or None
    except OSError:
        return None
    finally:
        path.unlink(missing_ok=True)


def _exit_if_stuck() -> None:
    """A scan worker blocked on a dead network mount would keep the process alive."""
    def others() -> list[threading.Thread]:
        return [t for t in threading.enumerate() if t is not threading.main_thread()
                and not t.daemon]
    if others():
        time.sleep(1.5)
        if others():
            sys.stdout.flush()
            os._exit(0)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="diskstrata", description=f"{APP_NAME}: local, read-only "
                                "disk-space analyzer. Opens a web UI on 127.0.0.1.")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    p.add_argument("--port", type=int, help=f"port to listen on (default {DEFAULT_PORT})")
    p.add_argument("--no-open", action="store_true", help="do not open a browser")
    p.add_argument("--data-dir", type=Path, help="where reports are stored")
    p.add_argument("--home", help="user home to analyse (used by the elevated copy)")
    # internal: elevation hand-off
    p.add_argument("--announce", type=Path, help=argparse.SUPPRESS)
    p.add_argument("--secret-file", type=Path, help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    common.set_home(args.home or _sudo_home())
    plat.init()
    if sys.version_info < (3, 11):              # deep folder trees need a big stack before 3.11
        threading.stack_size(64 * 1024 * 1024)
    store = Store(args.data_dir or plat.data_dir())
    secret = _read_secret(args.secret_file)
    if args.announce:
        args.announce.touch()                   # tells the launching copy that we are running
    app = App(store, secret)
    try:
        server = bind(args.port, DEFAULT_PORT, app)
    except SystemExit as exc:                   # an elevated copy has no visible console
        with_log = store.root / "startup-error.log"
        try:
            store.root.mkdir(parents=True, exist_ok=True)
            with_log.write_text(f"{exc}\n")
        except OSError:
            pass
        raise
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={app.secret}"
    label = f" ({plat.ELEVATED_LABEL})" if plat.is_elevated() else ""
    print(f"{APP_NAME}{label} running. Open: {url}\n(Ctrl+C or the Quit button stops it)",
          flush=True)
    # An elevated copy normally continues the browser tab that asked for it. If that session
    # could not be handed over, open a fresh tab instead of leaving the user without a link.
    inherited = bool(args.secret_file) and secret is not None
    if not args.no_open or (args.secret_file and not inherited):
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        app.runner.cancel()
        server.server_close()
    _exit_if_stuck()
