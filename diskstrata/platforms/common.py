"""Helpers shared by the platform adapters."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

PACKAGE_PARENT = str(Path(__file__).resolve().parents[2])   # makes `-m diskstrata` importable
_home: str | None = None


def set_home(path: str | None) -> None:
    """Override the user's home (used when an elevated copy runs as another account)."""
    global _home
    _home = path


def home() -> str:
    return _home or os.path.expanduser("~")


_BOOT = ("import sys; sys.path.append(sys.argv.pop(1)); "
         "from diskstrata.cli import main; main()")


def app_args(args: list[str]) -> list[str]:
    """Command that starts DiskStrata in isolated mode (ignores PYTHONPATH and the current
    directory, so nothing next to the package can shadow the standard library). The package
    location is appended to sys.path last for the same reason."""
    return [sys.executable, "-I", "-c", _BOOT, PACKAGE_PARENT, *args]


def run_text(args: list[str], timeout: float = 15) -> str:
    """stdout of a command, or "" if it is missing, fails or times out. Never uses a shell."""
    try:
        return subprocess.run(args, capture_output=True, text=True, errors="replace",
                              timeout=timeout, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def wait_for_announce(proc: subprocess.Popen, path: str, timeout: float = 120,
                      exit_ok: bool = False) -> bool:
    """True once the elevated child has created `path` (it is running, so the user
    authenticated); False if the launcher failed first (declined) or time ran out.
    exit_ok: the launcher may exit with status 0 while the child keeps running."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if os.path.exists(path):
            return True
        rc = proc.poll()
        if rc is not None and not (exit_ok and rc == 0):
            return False
        time.sleep(0.2)
    proc.terminate()
    return False
