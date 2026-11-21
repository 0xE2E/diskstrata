"""Where results live: one report per scan, a small history index, growth snapshots.

Files in the data directory:
  scan_<id>.html        the report (self-contained)
  scan_<id>.json        history entry (written last, so half-written scans never list)
  snap_<volume>_<id>.json   folder sizes used to show growth on the next scan of that volume
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent / "web"
SCAN_ID_RX = re.compile(r"^\d{8}_\d{6}$")
_NOT_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def slug(volume_id: str) -> str:
    """Filename-safe form of a volume id ("C:" -> "C", "/Volumes/Backup" -> "Volumes_Backup")."""
    return _NOT_ALNUM.sub("_", volume_id).strip("_") or "root"


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if os.name != "nt":
        tmp.chmod(0o600)                                # reports list your file paths
    os.replace(tmp, path)
    _give_to_owner(path)


def _give_to_owner(path: Path) -> None:
    """An elevated copy hands what it creates back to the account that owns the data folder."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        owner = path.parent.stat()
        with contextlib.suppress(OSError):              # e.g. FAT/exFAT or network folders
            os.chown(path, owner.st_uid, owner.st_gid)


def make_private_dir(path: Path) -> None:
    """Create the data folder (private to the user; folders created by an elevated copy
    are handed to the nearest existing parent's owner)."""
    missing = []
    for p in (path, *path.parents):
        if p.exists():
            break
        missing.append(p)
    for p in reversed(missing):
        p.mkdir(mode=0o700 if p == path else 0o777)
        _give_to_owner(p)


def embed_json(template: str, data: dict) -> str:
    """Put data into the report template. '<' is escaped so data can never close the script tag."""
    payload = json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")
    return template.replace("__DS_DATA__", payload, 1)


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root

    def new_scan_id(self) -> str:
        """UTC timestamp id (sorts correctly across daylight-saving changes); unique per store."""
        when = datetime.now(timezone.utc)
        while (self.root / f"scan_{when:%Y%m%d_%H%M%S}.json").exists():
            when += timedelta(seconds=1)
        return f"{when:%Y%m%d_%H%M%S}"

    def save_snapshot(self, volume_id: str, scan_id: str, sizes: dict[str, int]) -> None:
        make_private_dir(self.root)
        atomic_write(self.root / f"snap_{slug(volume_id)}_{scan_id}.json", json.dumps(sizes))

    def latest_snapshot(self, volume_id: str) -> tuple[str | None, dict[str, int]]:
        rx = re.compile(rf"^snap_{re.escape(slug(volume_id))}_(\d{{8}}_\d{{6}})\.json$")
        found = sorted((m.group(1), p) for p in self.root.glob("snap_*.json")
                       if (m := rx.match(p.name)))
        if not found:
            return None, {}
        try:
            return found[-1][0], json.loads(found[-1][1].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, {}

    def save_report(self, scan_id: str, data: dict) -> None:
        """Write the report, then its history entry."""
        make_private_dir(self.root)
        html = embed_json((WEB_DIR / "report.html").read_text(encoding="utf-8"), data)
        atomic_write(self.root / f"scan_{scan_id}.html", html)
        entry = {"id": scan_id, "generated": data["meta"]["generated"],
                 "volumes": [{"id": v["id"], "name": v["name"], "root": v["root"]}
                             for v in data["volumes"]]}
        atomic_write(self.root / f"scan_{scan_id}.json", json.dumps(entry))

    def history(self) -> list[dict]:
        """Saved scans, newest first."""
        out = []
        for meta in self.root.glob("scan_*.json"):
            try:
                entry = json.loads(meta.read_text(encoding="utf-8"))
                entry["size"] = meta.with_suffix(".html").stat().st_size
            except (OSError, ValueError):
                continue                    # incomplete or damaged: ignore
            if SCAN_ID_RX.fullmatch(str(entry.get("id", ""))):
                out.append(entry)
        return sorted(out, key=lambda e: e["id"], reverse=True)

    def read_report(self, scan_id: str) -> str | None:
        if not SCAN_ID_RX.fullmatch(scan_id):
            return None
        try:
            return (self.root / f"scan_{scan_id}.html").read_text(encoding="utf-8")
        except OSError:
            return None
