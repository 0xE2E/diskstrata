"""Read-only directory scanner: walks one volume and aggregates sizes.

It only lists directories and reads file metadata. Nothing is opened, modified or deleted.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .catalog import EXT_CAT
from .platforms import common
from .platforms import current as plat

MB = 1024 * 1024
TREE_MIN = 50 * MB          # folders kept in the tree
DIR_SIZE_MIN = 1 * MB       # folders whose size is remembered for lookups
SNAPSHOT_MIN = 5 * MB       # folders saved for the next scan's growth comparison
EXPAND_DEPTH = 1            # levels walked on the calling thread (3 measured 5x slower)
BIG_FILE_MIN = 200 * MB
DOC_FILE_MIN = 10 * MB
OLD_SECONDS = 180 * 86400
WORKERS = min(32, (os.cpu_count() or 4) * 2)
DOC_DIRS = {"documents", "downloads", "desktop", "pictures", "videos", "music"}


class ScanCancelled(Exception):
    pass


def path_key(path: str) -> str:
    """Normalised dictionary key for a folder path (case-folded where the OS is)."""
    return os.path.normcase(path.rstrip("\\/") or path)


@dataclass(slots=True)
class DirCtx:
    bucket: str | None = None   # Documents/Downloads/... area this dir is in
    in_nm: bool = False         # inside (or is) a node_modules folder
    kind: str | None = None     # badge for this dir (node_modules, ...)


class Listing:
    __slots__ = ("own", "count", "subdirs", "marker", "cloud", "docs", "doc_old", "doc_files")

    def __init__(self) -> None:
        self.own = 0
        self.count = 0
        self.subdirs: list[tuple[str, str]] = []
        self.marker: str | None = None
        self.cloud = 0
        self.docs: dict[str, list[int]] = {}
        self.doc_old = 0
        self.doc_files: list[tuple[str, int, float]] = []


@dataclass(slots=True)
class Result:
    size: int
    files: int
    node: dict | None


@dataclass(slots=True)
class Skel:
    path: str
    name: str
    listing: Listing
    ctx: DirCtx
    kids: list = field(default_factory=list)


@dataclass
class Stats:
    """Everything one volume scan collects. Counters are approximate while running."""
    home_key: str = ""
    pruned: frozenset[str] = frozenset()    # mount points / locations not to enter
    cancel: threading.Event = field(default_factory=threading.Event)
    seen_bytes: int = 0
    seen_files: int = 0
    current: str = ""
    links: set[tuple[int, int]] = field(default_factory=set)   # hard-linked files already counted
    dir_sizes: dict[str, int] = field(default_factory=dict)
    big_files: list[tuple[str, int, float]] = field(default_factory=list)
    envs: list[tuple[str, int, str]] = field(default_factory=list)
    node_modules: list[tuple[str, int]] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    docs: dict[str, dict] = field(default_factory=dict)
    cloud: int = 0
    dirs_scanned: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def merge(self, bucket: str | None, lst: Listing) -> None:
        """Fold one finished directory listing into the shared totals."""
        with self.lock:
            self.dirs_scanned += 1
            self.seen_bytes += lst.own
            self.seen_files += lst.count
            if bucket and lst.docs:
                area = self.docs.setdefault(bucket, {"cats": {}, "old": 0, "total": 0, "files": []})
                for cat, (size, count) in lst.docs.items():
                    slot = area["cats"].setdefault(cat, [0, 0])
                    slot[0] += size
                    slot[1] += count
                    area["total"] += size
                area["old"] += lst.doc_old
                area["files"].extend(lst.doc_files)
            self.cloud += lst.cloud


def _take_doc(name: str, path: str, size: int, mtime: float, lst: Listing) -> None:
    slot = lst.docs.setdefault(EXT_CAT.get(os.path.splitext(name)[1].lower(), "Other"), [0, 0])
    slot[0] += size
    slot[1] += 1
    if mtime < time.time() - OLD_SECONDS:
        lst.doc_old += size
    if size >= DOC_FILE_MIN:
        lst.doc_files.append((path, size, mtime))


def _take_entry(entry: os.DirEntry, lst: Listing, bucket: str | None, stats: Stats) -> None:
    try:
        if entry.is_dir(follow_symlinks=False):
            if not plat.skip_dir(entry, stats.pruned):
                lst.subdirs.append((plat.clean_path(entry.path), entry.name))
                if entry.name == "conda-meta":
                    lst.marker = "conda-env"
            return
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return
    if getattr(st, "st_file_attributes", 0) & plat.CLOUD_ATTRS:
        lst.cloud += st.st_size             # online-only OneDrive file: not on disk
        return
    size = plat.entry_size(st)
    if st.st_nlink > 1 and st.st_ino:       # hard link: count the data once (POSIX only;
        with stats.lock:                    # Windows scandir does not report inodes)
            counted = (st.st_dev, st.st_ino) in stats.links
            stats.links.add((st.st_dev, st.st_ino))
        if counted:
            size = 0
    lst.own += size
    lst.count += 1
    if size >= BIG_FILE_MIN:
        stats.big_files.append((plat.clean_path(entry.path), size, st.st_mtime))
    if entry.name == "pyvenv.cfg":
        lst.marker = "venv"
    if bucket:
        _take_doc(entry.name, plat.clean_path(entry.path), size, st.st_mtime, lst)


def list_dir(path: str, bucket: str | None, stats: Stats) -> Listing:
    """List one directory (metadata only)."""
    if stats.cancel.is_set():
        raise ScanCancelled()
    stats.current = path
    lst = Listing()
    try:
        with os.scandir(plat.fs_path(path)) as it:
            for entry in it:
                _take_entry(entry, lst, bucket, stats)
    except OSError:
        stats.denied.append(path)
    stats.merge(bucket, lst)
    return lst


def child_ctx(parent: str, name: str, ctx: DirCtx, stats: Stats) -> DirCtx:
    lname = name.lower()
    bucket = ctx.bucket
    if bucket is None and lname in DOC_DIRS:
        parent_key = path_key(parent)
        if parent_key == stats.home_key:
            bucket = name
        elif (path_key(os.path.dirname(parent)) == stats.home_key
              and os.path.basename(parent_key).startswith("onedrive")):
            bucket = "OneDrive " + name
    is_nm = lname == "node_modules"
    return DirCtx(bucket, ctx.in_nm or is_nm, "node_modules" if is_nm and not ctx.in_nm else None)


def build_result(path: str, name: str, lst: Listing, kids: list[Result],
                 ctx: DirCtx, stats: Stats) -> Result:
    size = lst.own + sum(k.size for k in kids)
    files = lst.count + sum(k.files for k in kids)
    if size >= DIR_SIZE_MIN:
        stats.dir_sizes[path_key(path)] = size
    if lst.marker and size >= 5 * MB:
        stats.envs.append((path, size, lst.marker))
    if ctx.kind == "node_modules" and size >= 5 * MB:
        stats.node_modules.append((path, size))
    if size < TREE_MIN:
        return Result(size, files, None)
    kept = sorted((k.node for k in kids if k.node), key=lambda n: -n["s"])
    small = [k.size for k in kids if not k.node]
    node: dict = {"n": name, "s": size, "f": files}
    if kept:
        node["c"] = kept
    if lst.own:
        node["o"] = lst.own
    if sum(small):
        node["r"], node["rn"] = sum(small), len(small)
    if ctx.kind or lst.marker:
        node["k"] = ctx.kind or lst.marker
    return Result(size, files, node)


def scan_dir(path: str, name: str, ctx: DirCtx, stats: Stats) -> Result:
    lst = list_dir(path, ctx.bucket, stats)
    kids = [scan_dir(p, n, child_ctx(path, n, ctx, stats), stats) for p, n in lst.subdirs]
    return build_result(path, name, lst, kids, ctx, stats)


def _expand(path: str, depth: int, stats: Stats) -> bool:
    """The top levels (and the user's profile) are walked on the calling thread so the
    deeper subtrees spread evenly over the worker pool."""
    if depth <= EXPAND_DEPTH:
        return True
    key = path_key(path)
    return depth <= 4 and (key == stats.home_key or key.startswith(stats.home_key + os.sep))


def expand_tree(path: str, name: str, depth: int, ctx: DirCtx, stats: Stats,
                pool: ThreadPoolExecutor) -> Skel:
    skel = Skel(path, name, list_dir(path, ctx.bucket, stats), ctx)
    for p, n in skel.listing.subdirs:
        cctx = child_ctx(path, n, ctx, stats)
        if _expand(p, depth + 1, stats):
            skel.kids.append(expand_tree(p, n, depth + 1, cctx, stats, pool))
        else:
            skel.kids.append(pool.submit(scan_dir, p, n, cctx, stats))
    return skel


def finalize(skel: Skel, stats: Stats) -> Result:
    kids = [finalize(k, stats) if isinstance(k, Skel) else k.result() for k in skel.kids]
    return build_result(skel.path, skel.name, skel.listing, kids, skel.ctx, stats)


def scan_volume(root: str, stats: Stats) -> Result:
    """Scan `root` and return its size tree. Raises ScanCancelled if stats.cancel is set."""
    sys.setrecursionlimit(20000)
    stats.home_key = path_key(common.home())
    stats.pruned = plat.prune_paths(root)
    with ThreadPoolExecutor(WORKERS) as pool:
        return finalize(expand_tree(root, root, 0, DirCtx(), stats, pool), stats)

