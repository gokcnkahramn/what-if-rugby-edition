"""British & Irish Lions - not a World Rugby union, so not in rugbydata at
all (same situation as the Barbarians - see `barbarians.py`). Unlike the
Barbarians' manual list, the real 2025 tour-squad Wikipedia page has a
full, clean, parseable wikitable - no manual entry needed. See
`rugby_sim.data.sources.invitational_squads.build_lions_pool`.
"""

from __future__ import annotations

from ._union_pool import lazy_invitational_pool
from ..sources.invitational_squads import build_lions_pool

CODE = "LIO"
get_pool = lazy_invitational_pool(build_lions_pool)
