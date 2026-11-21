"""macOS adapter: volumes from `mount`, osascript elevation, .app bundles as programs."""
from __future__ import annotations

import os
import plistlib
import re
import shlex
import subprocess
from pathlib import Path

from . import common

NAME = "macos"
SEP = "/"
ELEVATED_LABEL = "root"
ELEVATE_TIP = ("Without root, other users' folders and parts of /private are unreadable. "
               "Restarting as root (macOS asks for your password) helps with those. "
               "Folders protected by macOS privacy (Mail, Messages, Photos, Safari) "
               "also need Full Disk Access for your terminal or Python: System "
               "Settings > Privacy & Security > Full Disk Access.")
CLOUD_ATTRS = 0
_LOCAL_FS = {"apfs", "hfs", "exfat", "msdos", "ntfs", "udf"}
_NETWORK_FS = {"smbfs", "nfs", "afpfs", "webdav"}
_ALWAYS_PRUNE = {"/private/var/vm"}         # swap files: not user data
_MOUNT_RX = re.compile(r"^(?P<dev>.*?) on (?P<mount>/.*?) \((?P<fs>[\w+-]+)(?:, (?P<opts>.*))?\)$")


def path_vars() -> dict[str, str]:
    lib = os.path.join(common.home(), "Library")
    return {"home": common.home(), "lib": lib,
            "support": os.path.join(lib, "Application Support"),
            "caches": os.path.join(lib, "Caches")}


def data_dir() -> Path:
    return Path(common.home(), "Library", "Application Support", "DiskStrata")


def entry_size(st: os.stat_result) -> int:
    return st.st_blocks * 512


def prune_paths(root: str) -> frozenset[str]:
    """Every other mount point (other volumes, the Data volume that firmlinks already expose,
    simulator images, translocation mounts) so nothing is walked twice."""
    mounts = {os.path.normpath(m) for _, m, _ in parse_mount(common.run_text(["/sbin/mount"]))}
    return frozenset((mounts - {os.path.normpath(root)}) | _ALWAYS_PRUNE)


def skip_dir(entry: os.DirEntry, pruned: frozenset[str]) -> bool:
    return entry.path in pruned


def fs_path(path: str) -> str:
    return path


def clean_path(path: str) -> str:
    return path


def init() -> None:
    pass


def is_elevated() -> bool:
    return os.geteuid() == 0


def parse_mount(text: str) -> list[tuple[str, str, str]]:
    """(device, mountpoint, fstype) for each line of `mount` output."""
    rows = []
    for line in text.splitlines():
        m = _MOUNT_RX.match(line)
        if m:
            rows.append((m["dev"], m["mount"], m["fs"]))
    return rows


def _system_name() -> str:
    """The /Volumes entry that links to / carries the startup disk's name."""
    try:
        for entry in os.scandir("/Volumes"):
            if entry.is_symlink() and os.path.realpath(entry.path) == "/":
                return entry.name
    except OSError:
        pass
    return "Macintosh HD"


def list_volumes() -> list[dict]:
    out = []
    for _, mount, fs in parse_mount(common.run_text(["/sbin/mount"])):
        is_system = mount == "/"
        name = os.path.basename(mount)
        if not is_system and (not mount.startswith("/Volumes/") or name.startswith(".")):
            continue
        if fs not in _LOCAL_FS and fs not in _NETWORK_FS:
            continue
        # On APFS the user's files live on the Data volume; its numbers describe the container
        data = "/System/Volumes/Data"
        probe = data if is_system and os.path.isdir(data) else mount
        try:
            vfs = os.statvfs(probe)
        except OSError:
            continue
        total = vfs.f_blocks * vfs.f_frsize
        free = vfs.f_bavail * vfs.f_frsize
        out.append({"id": mount, "root": mount, "name": _system_name() if is_system else name,
                    "fs": fs, "kind": "Network" if fs in _NETWORK_FS else "Local disk",
                    "total": total, "used": total - free, "free": free, "is_system": is_system})
    return sorted(out, key=lambda v: (not v["is_system"], v["root"]))


def relaunch_elevated(args: list[str], announce: str) -> str | None:
    """Ask for the password with the standard macOS dialog and start a root copy."""
    inner = " ".join(shlex.quote(a) for a in common.app_args([*args, "--announce", announce]))
    quoted = (inner + " >/dev/null 2>&1 &").replace("\\", "\\\\").replace('"', '\\"')
    proc = subprocess.Popen(
        ["osascript", "-e", f'do shell script "{quoted}" with administrator privileges'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None if common.wait_for_announce(proc, announce, exit_ok=True) \
        else "Administrator permission was not granted."


def reveal(path: str, select: bool) -> None:
    # `open <dir>` would launch a .app bundle (it is a directory): only plain folders are opened
    bundle = path.endswith((".app", ".bundle", ".pkg", ".framework"))
    plain = os.path.isdir(path) and not bundle and not select
    cmd = ["open", path] if plain else ["open", "-R", path]
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def installed_programs() -> list[dict]:
    """Application bundles in /Applications and ~/Applications."""
    out = []
    for base in ("/Applications", os.path.join(common.home(), "Applications")):
        try:
            entries = [e for e in os.scandir(base) if e.name.endswith(".app")]
        except OSError:
            continue
        for e in entries:
            info = {}
            try:
                with open(os.path.join(e.path, "Contents", "Info.plist"), "rb") as fh:
                    info = plistlib.load(fh)
            except (OSError, plistlib.InvalidFileException, ValueError):
                pass
            out.append({"name": info.get("CFBundleDisplayName") or e.name[:-4],
                        "pub": "", "ver": str(info.get("CFBundleShortVersionString", "")),
                        "date": "", "est": 0, "loc": e.path})
    return out
