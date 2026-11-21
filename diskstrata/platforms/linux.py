"""Linux adapter: mounts from /proc, pkexec elevation, dpkg/rpm package lists."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import common

NAME = "linux"
SEP = "/"
ELEVATED_LABEL = "root"
ELEVATE_TIP = ("Without root, system folders such as /var, /root and other users' homes "
               "are partly unreadable and their size is missing from the results. "
               "Restarting as root (a system dialog asks for your password) gives the "
               "complete picture.")
CLOUD_ATTRS = 0
_LOCAL_FS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "f2fs", "jfs", "reiserfs",
             "bcachefs", "ntfs", "ntfs3", "vfat", "exfat", "fuseblk"}
_NETWORK_FS = {"nfs", "nfs4", "cifs", "smb3"}
_REMOVABLE_PREFIXES = ("/media/", "/run/media/")


def _xdg(var: str, default: str) -> str:
    return os.environ.get(var) or os.path.join(common.home(), default)


def path_vars() -> dict[str, str]:
    return {"home": common.home(), "config": _xdg("XDG_CONFIG_HOME", ".config"),
            "cache": _xdg("XDG_CACHE_HOME", ".cache"),
            "data": _xdg("XDG_DATA_HOME", ".local/share"),
            "state": _xdg("XDG_STATE_HOME", ".local/state")}


def data_dir() -> Path:
    return Path(_xdg("XDG_DATA_HOME", ".local/share")) / "diskstrata"


def entry_size(st: os.stat_result) -> int:
    return st.st_blocks * 512                   # allocated size, like du/df (handles sparse files)


def prune_paths(root: str) -> frozenset[str]:
    """Every other mount point (pseudo filesystems, bind mounts, other volumes): they are
    listed or measured separately, so walking into them would skip or double count data."""
    try:
        rows = parse_mounts(Path("/proc/self/mounts").read_text(errors="replace"))
    except OSError:
        return frozenset()
    return frozenset(os.path.normpath(m) for _, m, _ in rows) - {os.path.normpath(root)}


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


def _unescape(field: str) -> str:
    """/proc/mounts escapes space, tab, newline and backslash as octal."""
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), field)


def parse_mounts(text: str) -> list[tuple[str, str, str]]:
    """(device, mountpoint, fstype) for every line of /proc/self/mounts."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            rows.append((_unescape(parts[0]), _unescape(parts[1]), parts[2]))
    return rows


def _labels() -> dict[str, str]:
    """Resolved device path -> filesystem label."""
    out = {}
    base = Path("/dev/disk/by-label")
    try:
        for link in base.iterdir():
            out[os.path.realpath(link)] = re.sub(
                r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), link.name)
    except OSError:
        pass
    return out


def list_volumes() -> list[dict]:
    try:
        rows = parse_mounts(Path("/proc/self/mounts").read_text(errors="replace"))
    except OSError:
        return []
    labels, by_dev = _labels(), {}
    for device, mount, fs in rows:
        if fs not in _LOCAL_FS and fs not in _NETWORK_FS:
            continue
        try:
            st = os.stat(mount)
            vfs = os.statvfs(mount)
        except OSError:
            continue
        # one entry per device (bind mounts of the same filesystem): keep the shortest mount
        known = by_dev.get(st.st_dev)
        if known and len(known["root"]) <= len(mount):
            continue
        total = vfs.f_blocks * vfs.f_frsize
        free = vfs.f_bavail * vfs.f_frsize
        kind = ("Network" if fs in _NETWORK_FS else
                "Removable" if mount.startswith(_REMOVABLE_PREFIXES) else "Local disk")
        name = labels.get(os.path.realpath(device)) or (
            "Root filesystem" if mount == "/" else os.path.basename(mount) or device)
        by_dev[st.st_dev] = {"id": mount, "root": mount, "name": name, "fs": fs, "kind": kind,
                             "total": total, "used": total - vfs.f_bfree * vfs.f_frsize,
                             "free": free, "is_system": mount == "/"}
    return sorted(by_dev.values(), key=lambda v: (not v["is_system"], v["root"]))


def relaunch_elevated(args: list[str], announce: str) -> str | None:
    if not shutil.which("pkexec"):
        return ("pkexec (polkit) is not installed. Start DiskStrata from a terminal "
                "with: sudo python3 -m diskstrata")
    cmd = ["pkexec", *common.app_args([*args, "--announce", announce])]
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    if common.wait_for_announce(proc, announce):
        return None
    return ("Permission was not granted, or no polkit authentication agent is available. "
            "You can also start DiskStrata with: sudo python3 -m diskstrata")


def reveal(path: str, select: bool) -> None:
    target = os.path.dirname(path) if os.path.isfile(path) else path
    subprocess.Popen(["xdg-open", target], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _packages_dpkg() -> list[dict]:
    fmt = "${db:Status-Abbrev}\t${Package}\t${Version}\t${Installed-Size}\t${Maintainer}\n"
    text = common.run_text(["dpkg-query", "-W", "-f", fmt], 30)
    out = []
    for line in text.splitlines():
        status, name, ver, size, pub = (line.split("\t") + ["", "", "", "0", ""])[:5]
        if status.strip() == "ii":                  # installed (skips removed-but-configured "rc")
            out.append({"name": name, "ver": ver, "est": int(size or 0) * 1024, "pub": pub})
    return out


def _packages_rpm() -> list[dict]:
    fmt = "%{NAME}\t%{VERSION}-%{RELEASE}\t%{SIZE}\t%{VENDOR}\n"
    text = common.run_text(["rpm", "-qa", "--qf", fmt], 30)
    out = []
    for line in text.splitlines():
        name, ver, size, pub = (line.split("\t") + ["", "", "0", ""])[:4]
        out.append({"name": name, "ver": ver, "est": int(size) if size.isdigit() else 0,
                    "pub": "" if pub == "(none)" else pub})
    return out


def installed_programs() -> list[dict]:
    """Installed packages from dpkg or rpm (other package managers are not listed)."""
    rows = _packages_dpkg() if shutil.which("dpkg-query") else (
        _packages_rpm() if shutil.which("rpm") else [])
    return [{"date": "", "loc": "", **r} for r in rows]
