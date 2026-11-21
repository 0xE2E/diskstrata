"""Runs one scan job at a time in a background thread. A job covers one or more volumes
and produces a single report."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime

from . import __version__, volumes
from .analysis import apply_deltas, build_volume, is_under
from .platforms import common
from .platforms import current as plat
from .scanner import SNAPSHOT_MIN, ScanCancelled, Stats, scan_volume
from .storage import Store


class Job:
    def __init__(self, chosen: list[dict], home_id: str | None) -> None:
        self.volumes = chosen
        self.home_id = home_id              # volume that holds the user's home folder
        self.index = 0
        self.state = "running"              # running / done / cancelled
        self.cancel = threading.Event()
        self.stats = Stats(cancel=self.cancel)
        self.errors: list[dict] = []
        self.denied: dict[str, int] = {}
        self.scan_id: str | None = None
        self.t0 = time.time()
        self.elapsed = 0.0

    @property
    def volume(self) -> dict:
        return self.volumes[min(self.index, len(self.volumes) - 1)]

    def fail(self, volume_id: str, exc: Exception) -> None:
        self.errors.append({"volume": volume_id, "error": f"{type(exc).__name__}: {exc}"})


def home_volume_id(all_volumes: list[dict], home: str) -> str | None:
    """The deepest volume root that contains `home` (/home can be its own partition)."""
    holders = [v for v in all_volumes if is_under(home, v["root"])]
    return max(holders, key=lambda v: len(v["root"]))["id"] if holders else None


class JobRunner:
    def __init__(self, store: Store,
                 list_volumes: Callable[[], list[dict]] = volumes.list_volumes) -> None:
        self.store = store
        self._volumes = list_volumes
        self._job: Job | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return bool(self._job and self._job.state == "running")

    def volumes(self) -> list[dict]:
        return self._volumes()

    def start(self, volume_ids: list[str]) -> str | None:
        """Start scanning the given volume ids. Returns an error message or None."""
        available = self._volumes()
        by_id = {v["id"]: v for v in available}
        chosen = [by_id[i] for i in dict.fromkeys(volume_ids) if i in by_id]
        if not chosen:
            return "No valid volume selected."
        with self._lock:
            if self.running:
                return "A scan is already running."
            self._job = job = Job(chosen, home_volume_id(available, common.home()))
            threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return None

    def cancel(self) -> None:
        """Stop the running scan. The job is released at once, even if a worker is stuck
        on an unresponsive mount; such a worker just finishes (or leaks) in the background."""
        job = self._job
        if job:
            job.cancel.set()
            if job.state == "running":
                job.state = "cancelled"

    def _scan_volume(self, job: Job, vol: dict, installed: list[dict]) -> tuple[dict, dict]:
        prev, prev_sizes = self.store.latest_snapshot(vol["id"])
        t0 = time.time()
        res = scan_volume(vol["root"], job.stats)
        res.node = res.node or {"n": vol["root"], "s": res.size, "f": res.files}
        sizes = {k: v for k, v in job.stats.dir_sizes.items() if v >= SNAPSHOT_MIN}
        if prev_sizes:
            apply_deltas(res.node, vol["root"], prev_sizes)
        job.denied[vol["id"]] = len(job.stats.denied)
        data = build_volume(vol, res, job.stats, time.time() - t0, prev,
                            vol["id"] == job.home_id, installed)
        return data, sizes

    def _run(self, job: Job) -> None:
        try:
            installed = plat.installed_programs()
            done: list[tuple[dict, dict]] = []
            for i, vol in enumerate(job.volumes):
                job.index, job.stats = i, Stats(cancel=job.cancel)
                try:
                    done.append(self._scan_volume(job, vol, installed))
                except ScanCancelled:
                    return
                except Exception as exc:        # one bad volume must not lose the others
                    job.fail(vol["id"], exc)
            if done and not job.cancel.is_set():
                self._save(job, done)
        except Exception as exc:                # saving failed
            job.fail("", exc)
        finally:
            job.elapsed = time.time() - job.t0
            if job.state == "running":
                job.state = "done"

    def _save(self, job: Job, done: list[tuple[dict, dict]]) -> None:
        scan_id = self.store.new_scan_id()
        for data, sizes in done:
            self.store.save_snapshot(data["id"], scan_id, sizes)
        meta = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "version": __version__,
                "os": plat.NAME, "sep": plat.SEP, "admin": plat.is_elevated(),
                "elapsed": round(time.time() - job.t0)}
        self.store.save_report(scan_id, {"meta": meta, "volumes": [d for d, _ in done]})
        job.scan_id = scan_id

    def status(self) -> dict:
        out = {"elevated": plat.is_elevated(), "state": "idle"}
        job = self._job
        if not job:
            return out
        s = job.stats
        running = job.state == "running"
        used = job.volume["used"]
        elapsed = time.time() - job.t0 if running else job.elapsed
        out.update({
            "state": job.state, "volumes": [v["id"] for v in job.volumes], "index": job.index,
            "volume": job.volume["id"], "dirs": s.dirs_scanned, "files": s.seen_files,
            "bytes": s.seen_bytes,
            "pct": round(min(99.0, s.seen_bytes / used * 100), 1) if running and used else 0,
            "current": s.current, "elapsed": round(elapsed), "scan": job.scan_id,
            "errors": list(job.errors), "denied": dict(job.denied)})
        return out
