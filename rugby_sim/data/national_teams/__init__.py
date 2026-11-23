"""Registry of international player pools: Tier 1 + Tier 2 unions (via the
rugbydata pipeline) plus invitational/composite sides (the Barbarians, the
British & Irish Lions, the Pacific Islanders - manual or Wikipedia-only,
since none of them is a World Rugby union, so none is in that dataset).

Tier 2 unions are here because they're part of the 2027 Rugby World Cup
picture - some (Georgia, Romania, Spain, Portugal) have 2026 rows already;
the rest (Samoa, Tonga, USA, Canada, Uruguay, Chile, Namibia) fall back
to their latest available season automatically (see
`pool_builder.build_union_pool`'s fallback) since the dataset hasn't
scraped their most recent fixtures yet.

`POOLS[code]` is a zero-arg callable, not a pre-built list - calling it
triggers (and disk-caches) the data pull the first time. Building an actual
starting XV from a pool is still a manual step (see `rugby_sim/cli.py`):
drafting the lineup is the point of the project, not something this
registry should do for you.

`POOLS` itself is built by auto-discovery, not a hand-maintained dict: every
submodule in this package that exposes BOTH a module-level `CODE: str`
(its union/pool short code) and a `get_pool` callable is picked up
automatically. Adding a new union/pool therefore needs only a new file in
this package - no edit here - as long as that file sets `CODE` to its
intended key. A submodule name starting with `_` (today, only
`_union_pool.py`, the shared lazy-loading-helper module) is skipped, since
it's a private helper, not a per-union module.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, Dict, List

from ...models.player import Player

POOLS: Dict[str, Callable[[], List[Player]]] = {}

for _mod_info in pkgutil.iter_modules(__path__):
    if _mod_info.name.startswith("_"):
        continue
    _module = importlib.import_module(f".{_mod_info.name}", __name__)
    _code = getattr(_module, "CODE", None)
    _get_pool = getattr(_module, "get_pool", None)
    if _code and _get_pool:
        POOLS[_code] = _get_pool

__all__ = ["POOLS"]
