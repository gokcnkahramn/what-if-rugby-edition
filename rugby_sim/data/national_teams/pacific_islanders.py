"""Pacific Islanders - a real, now-discontinued (2004-2009) composite side
(Fiji/Samoa/Tonga), never a World Rugby union, so not in rugbydata.
Squad is its last real tour (2008, to Europe), scraped from Wikipedia. See
`rugby_sim.data.sources.invitational_squads.build_pacific_islanders_pool`.
"""

from __future__ import annotations

from ._union_pool import lazy_invitational_pool
from ..sources.invitational_squads import build_pacific_islanders_pool

CODE = "PAC"
get_pool = lazy_invitational_pool(build_pacific_islanders_pool)
