"""Volume listing that cannot freeze the app when a network mount stops answering."""
from __future__ import annotations

import threading

from .platforms import current as plat

_last: list[dict] = []


def list_volumes(timeout: float = 5.0) -> list[dict]:
    """The platform's volume list. If probing blocks (a dead NFS/SMB share makes stat/statvfs
    hang), the previous answer is returned and the stuck probe is abandoned."""
    global _last
    box: list[list[dict]] = []
    probe = threading.Thread(target=lambda: box.append(plat.list_volumes()), daemon=True)
    probe.start()
    probe.join(timeout)
    if box:
        _last = box[0]
    return _last
