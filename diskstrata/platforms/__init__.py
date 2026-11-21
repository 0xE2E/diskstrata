"""Platform adapters. `current` is the adapter for the running OS; every adapter provides:

    NAME, SEP, ELEVATED_LABEL, ELEVATE_TIP, CLOUD_ATTRS, path_vars(), data_dir(),
    entry_size(st), prune_paths(root), skip_dir(entry, pruned), fs_path(path),
    clean_path(path), init(), is_elevated(), list_volumes(),
    relaunch_elevated(args, announce), reveal(path, select), installed_programs()
"""
from __future__ import annotations

import sys

if sys.platform == "win32":
    from . import windows as current
elif sys.platform == "darwin":
    from . import macos as current
else:
    from . import linux as current

__all__ = ["current"]
