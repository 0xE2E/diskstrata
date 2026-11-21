"""Knowledge base: cross-platform meanings plus the active OS's known locations."""
from __future__ import annotations

import sys

from .knowledge import AGENTS, EXT_CAT, describe

if sys.platform == "win32":
    from .windows import AGENT_BASES, HOTSPOTS, STALE, SYSTEM_ITEMS
elif sys.platform == "darwin":
    from .macos import AGENT_BASES, HOTSPOTS, STALE, SYSTEM_ITEMS
else:
    from .linux import AGENT_BASES, HOTSPOTS, STALE, SYSTEM_ITEMS

__all__ = ["AGENTS", "AGENT_BASES", "EXT_CAT", "HOTSPOTS", "STALE", "SYSTEM_ITEMS", "describe"]
