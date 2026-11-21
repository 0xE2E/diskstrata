"""Windows adapter: drives via Win32, UAC elevation, registry for installed programs."""
from __future__ import annotations

import contextlib
import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import common

NAME = "windows"
SEP = "\\"
ELEVATED_LABEL = "Administrator"
ELEVATE_TIP = ("Standard mode cannot read parts of Windows, ProgramData, System Volume "
               "Information or other users' profiles. Restarting as Administrator "
               "(Windows asks you to confirm) gives the complete picture.")
CLOUD_ATTRS = 0x400000 | 0x40000 | 0x1000   # OneDrive online-only / offline files
_REPARSE_POINT = 0x400
_NAME_SURROGATE = 0x20000000                # reparse tags that redirect elsewhere
_DRIVE_KINDS = {2: "Removable", 3: "Local disk", 4: "Network", 6: "RAM disk"}


def system_drive() -> str:
    return os.environ.get("SYSTEMDRIVE", "C:").upper()


def path_vars() -> dict[str, str]:
    home = common.home()
    env = os.environ.get
    return {
        "home": home,
        "roaming": env("APPDATA", home + "\\AppData\\Roaming"),
        "local": env("LOCALAPPDATA", home + "\\AppData\\Local"),
        "temp": os.path.realpath(env("TEMP", home + "\\AppData\\Local\\Temp")),
        "win": env("WINDIR", "C:\\Windows"),
        "pd": env("PROGRAMDATA", "C:\\ProgramData"),
        "pf": env("PROGRAMFILES", "C:\\Program Files"),
        "pf86": env("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
        "sys": system_drive() + "\\",
    }


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", common.home() + "\\AppData\\Local")) / "DiskStrata"


def entry_size(st: os.stat_result) -> int:
    return st.st_size


def prune_paths(root: str) -> frozenset[str]:
    return frozenset()


def skip_dir(entry: os.DirEntry, pruned: frozenset[str]) -> bool:
    """Do not follow junctions, symlinks or mount points (they point at other places).
    Other reparse points, such as OneDrive placeholders, are real folders and are walked."""
    st = entry.stat(follow_symlinks=False)
    return bool(st.st_file_attributes & _REPARSE_POINT
                and getattr(st, "st_reparse_tag", 0) & _NAME_SURROGATE)


_LONG = "\\\\?\\"                       # the Windows extended-length path prefix


def fs_path(path: str) -> str:
    """Prefix long paths so folders deeper than 260 characters can still be read."""
    return _LONG + path if len(path) > 240 and not path.startswith("\\\\") else path


def clean_path(path: str) -> str:
    return path[len(_LONG):] if path.startswith(_LONG) else path


def init() -> None:
    ctypes.windll.kernel32.SetErrorMode(1)     # no "insert disk" dialogs for empty readers


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def list_volumes() -> list[dict]:
    k32 = ctypes.windll.kernel32
    mask = k32.GetLogicalDrives()
    out = []
    for i in range(26):
        if not mask & (1 << i):
            continue
        letter = chr(65 + i)
        root = f"{letter}:\\"
        kind = _DRIVE_KINDS.get(k32.GetDriveTypeW(root))
        if not kind:                            # optical, unknown, no root
            continue
        try:
            usage = shutil.disk_usage(root)
        except OSError:                         # empty card reader etc.
            continue
        label, fs = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
        k32.GetVolumeInformationW(root, label, 261, None, None, None, fs, 261)
        out.append({"id": f"{letter}:", "root": root, "name": label.value or "Local Disk",
                    "fs": fs.value, "kind": kind, "total": usage.total, "used": usage.used,
                    "free": usage.free, "is_system": f"{letter}:" == system_drive()})
    return out


def relaunch_elevated(args: list[str], announce: str) -> str | None:
    """Start an elevated copy through UAC. Returns an error message, or None on success.
    ShellExecute returns only after the user answered the prompt."""
    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteW.restype = ctypes.c_void_p
    params = subprocess.list2cmdline(common.app_args(args)[1:])
    rc = shell32.ShellExecuteW(None, "runas", sys.executable, params,
                               common.PACKAGE_PARENT, 1)
    return None if (rc or 0) > 32 else "Administrator permission was not granted."


def reveal(path: str, select: bool) -> None:
    if select or not os.path.isdir(path):       # never hand a file to Explorer to "open"
        subprocess.Popen(f'explorer.exe /select,"{os.path.normpath(path)}"')
    else:
        subprocess.Popen(["explorer.exe", os.path.normpath(path)])


def installed_programs() -> list[dict]:
    """Programs registered for uninstall (registry, read-only)."""
    import winreg
    keys = [(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
            (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
            (winreg.HKEY_CURRENT_USER, 0)]
    sub = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    names = ("DisplayName", "Publisher", "DisplayVersion", "InstallDate",
             "EstimatedSize", "InstallLocation", "SystemComponent")
    out, seen = [], set()
    for hive, flag in keys:
        try:
            root = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | flag)
        except OSError:
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as key:
                        v = {}
                        for n in names:
                            with contextlib.suppress(OSError):
                                v[n] = winreg.QueryValueEx(key, n)[0]
                except OSError:
                    continue
                name = str(v.get("DisplayName") or "").strip()
                ident = (name.lower(), str(v.get("DisplayVersion", "")))
                if not name or v.get("SystemComponent") == 1 or ident in seen:
                    continue
                seen.add(ident)
                est = v.get("EstimatedSize")
                loc = os.path.expandvars(str(v.get("InstallLocation") or ""))
                loc = loc.strip().strip('"').rstrip("\\")
                out.append({"name": name, "pub": str(v.get("Publisher") or ""),
                            "ver": str(v.get("DisplayVersion") or ""),
                            "date": str(v.get("InstallDate") or ""),
                            "est": int(est) * 1024 if isinstance(est, int) else 0,
                            "loc": loc if loc and os.path.isdir(loc) else ""})
    return out
