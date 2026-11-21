"""Turns a finished scan into report data: known caches, system items, AI-agent folders,
programs and growth since the previous scan. Read-only."""
from __future__ import annotations

import glob
import os
import stat
from bisect import bisect_left

from .catalog import AGENT_BASES, AGENTS, HOTSPOTS, STALE, SYSTEM_ITEMS, describe
from .platforms import common
from .platforms import current as plat
from .scanner import MB, Result, Stats, path_key

DOT_FOLDER_MIN = 10 * MB
VIRTUAL_DISKS = (".vhdx", ".vhd", ".vmdk", ".vdi", ".qcow2")
MAX_PROGRAMS = 500


class Lookup:
    """Size lookups for paths the scan already measured."""

    def __init__(self, stats: Stats) -> None:
        self.stats = stats
        self.vars = plat.path_vars()
        self.denied = sorted({path_key(d) for d in stats.denied})

    def expand(self, template: str) -> list[str]:
        path = os.path.normpath(template.format(**self.vars))
        if "*" in path:
            return sorted(glob.glob(path))
        return [path] if os.path.lexists(path) else []

    def _denied_status(self, key: str) -> str:
        i = bisect_left(self.denied, key)
        if i < len(self.denied) and self.denied[i] == key:
            return "denied"
        prefix = key.rstrip(os.sep) + os.sep
        j = bisect_left(self.denied, prefix)
        return "partial" if j < len(self.denied) and self.denied[j].startswith(prefix) else "dir"

    def size(self, path: str, st: os.stat_result | None = None) -> tuple[int, str]:
        """(bytes, status) where status is file / dir / partial / denied.
        Pass `st` (an lstat result) when the caller already has it."""
        if st is None:
            try:
                st = os.lstat(path)
            except OSError:
                return 0, "denied"
        if not stat.S_ISDIR(st.st_mode):
            return plat.entry_size(st), "file"
        key = path_key(path)
        return self.stats.dir_sizes.get(key, 0), self._denied_status(key)

    def breakdown(self, path: str, agent: str | None, depth: int = 0) -> list[dict]:
        """Immediate children of a folder with size and meaning."""
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except OSError:
            return []
        items = []
        for e in entries:
            try:
                size, status = self.size(e.path, e.stat(follow_symlinks=False))
            except OSError:
                size, status = 0, "denied"
            desc, hint = describe(agent, e.name, status == "file")
            items.append({"n": e.name, "p": e.path, "s": size, "file": status == "file",
                          "st": status, "desc": desc, "hint": hint})
        items.sort(key=lambda i: -i["s"])
        if depth == 0:
            for item in items[:12]:
                if not item["file"] and item["s"] >= 50 * MB:
                    item["c"] = self.breakdown(item["p"], agent, 1)[:15]
        limit = 40 if depth == 0 else 15
        if len(items) > limit:
            rest = items[limit:]
            items = items[:limit] + [{"n": f"({len(rest)} more items)", "p": "",
                                      "s": sum(i["s"] for i in rest), "rest": True}]
        return items

    def hotspots(self, known: bool) -> list[dict]:
        out = []
        for cat, label, template, advice in (HOTSPOTS if known else ()):
            for path in self.expand(template):
                size, status = self.size(path)
                if size or status in ("denied", "partial"):
                    out.append({"cat": cat, "label": label, "path": path, "s": size,
                                "st": status, "advice": advice})
        for path, size, _ in self.stats.big_files:
            if path.lower().endswith(VIRTUAL_DISKS):
                out.append({"cat": "VMs", "label": "Virtual disk file", "path": path, "s": size,
                            "st": "file", "advice": "VM disk; shrink from inside the VM or "
                                                    "container runtime, then compact it."})
        return out

    def system_items(self) -> list[dict]:
        out = []
        for label, template, advice in SYSTEM_ITEMS:
            for path in self.expand(template):
                size, status = self.size(path)
                out.append({"label": label, "path": path, "s": size, "st": status,
                            "advice": advice, "stale": label in STALE})
        return out

    def _agent_locations(self) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {key: [] for key, _, _ in AGENTS}
        for base_t, dot_only in AGENT_BASES:
            for base in self.expand(base_t):
                try:
                    with os.scandir(base) as it:
                        names = [(e.name, e.path) for e in it]
                except OSError:
                    continue
                for name, path in names:
                    if dot_only and not name.startswith("."):
                        continue
                    for key, _, rx in AGENTS:
                        if rx.search(name):
                            found[key].append(path)
                            break
        keys = sorted({path_key(p) for v in found.values() for p in v})
        nested = {k for k in keys if any(k.startswith(q + os.sep) for q in keys if q != k)}
        return {k: sorted({p for p in v if path_key(p) not in nested}, key=str.lower)
                for k, v in found.items()}

    def agents(self) -> tuple[list[dict], set[str]]:
        names = {key: label for key, label, _ in AGENTS}
        agents, used = [], set()
        for key, paths in self._agent_locations().items():
            locs = []
            for path in paths:
                used.add(path_key(path))
                size, status = self.size(path)
                loc = {"path": path, "s": size, "st": status, "file": status == "file"}
                if status != "file":
                    loc["c"] = self.breakdown(path, key)
                locs.append(loc)
            if locs:
                locs.sort(key=lambda loc: -loc["s"])
                agents.append({"key": key, "name": names[key], "locs": locs,
                               "s": sum(loc["s"] for loc in locs)})
        agents.sort(key=lambda a: -a["s"])
        return agents, used

    def dotfolders(self, used: set[str]) -> list[dict]:
        out = []
        try:
            with os.scandir(common.home()) as it:
                entries = [e for e in it if e.name.startswith(".")]
        except OSError:
            return out
        for e in entries:
            if path_key(e.path) in used or not e.is_dir(follow_symlinks=False):
                continue
            size, status = self.size(e.path)
            if size >= DOT_FOLDER_MIN:
                out.append({"path": e.path, "s": size, "st": status,
                            "desc": describe(None, e.name, False)[0],
                            "c": self.breakdown(e.path, None)})
        out.sort(key=lambda d: -d["s"])
        return out


def is_under(path: str, root: str) -> bool:
    key, base = path_key(path), path_key(root).rstrip(os.sep)
    return key == base or key.startswith(base + os.sep)


def programs(stats: Stats, root: str, is_system: bool, installed: list[dict]) -> list[dict]:
    """Installed programs that live on this volume (location-less ones go to the system volume)."""
    out = []
    for p in installed:
        loc = p["loc"]
        if loc:
            if not is_under(loc, root):
                continue
        elif not is_system:
            continue
        out.append({**p, "measured": stats.dir_sizes.get(path_key(loc), 0) if loc else 0})
    out.sort(key=lambda p: -max(p["est"], p["measured"]))
    return out[:MAX_PROGRAMS]


def summarize_docs(stats: Stats) -> dict:
    return {bucket: {"total": a["total"], "old": a["old"], "cats": a["cats"],
                     "top": [{"path": p, "s": s, "m": m}
                             for p, s, m in sorted(a["files"], key=lambda f: -f[1])[:15]]}
            for bucket, a in stats.docs.items()}


# --------------------------------------------------------------------------- #
# Growth since the previous scan
# --------------------------------------------------------------------------- #
def apply_deltas(node: dict, path: str, prev: dict[str, int]) -> None:
    """Annotate the tree with growth since the previous scan (`prev` maps path_key -> bytes)."""
    before = prev.get(path_key(path))
    node["d"] = node["s"] - (before or 0)
    if before is None:
        node["nw"] = 1
    for child in node.get("c", []):
        apply_deltas(child, os.path.join(path, child["n"]), prev)


def build_volume(vol: dict, res: Result, stats: Stats, elapsed: float, prev: str | None,
                 owns_home: bool, installed: list[dict]) -> dict:
    """Report data for one scanned volume (schema: see diskstrata/web/report.html).
    System items belong to the system volume, per-user sections to the volume that holds
    the user's home folder (they can be different volumes)."""
    look = Lookup(stats)
    is_sys = vol["is_system"]
    agents, used = look.agents() if owns_home else ([], set())
    big = sorted(stats.big_files, key=lambda f: -f[1])[:150]
    return {
        "id": vol["id"], "root": vol["root"], "name": vol["name"], "is_system": is_sys,
        "elapsed": round(elapsed), "prev": prev,
        "disk": {"total": vol["total"], "used": vol["used"], "free": vol["free"]},
        "scan": {"size": res.size, "files": res.files, "dirs": stats.dirs_scanned,
                 "denied": len(stats.denied), "denied_sample": stats.denied[:40],
                 "cloud": stats.cloud},
        "tree": res.node,
        "hotspots": look.hotspots(owns_home),
        "envs": sorted(({"path": p, "s": s, "t": t} for p, s, t in stats.envs),
                       key=lambda e: -e["s"]),
        "node_modules": sorted(({"path": p, "s": s} for p, s in stats.node_modules),
                               key=lambda e: -e["s"])[:300],
        "agents": agents,
        "dotfolders": look.dotfolders(used) if owns_home else [],
        "system": look.system_items() if is_sys else [],
        "programs": programs(stats, vol["root"], is_sys, installed),
        "big_files": [{"path": p, "s": s, "m": m} for p, s, m in big],
        "docs": summarize_docs(stats),
    }
