"""The 2027 Rugby World Cup (Australia) - real pool draw, no real fixtures.

The tournament hasn't been played (kicks off 1 Oct 2027 - in the future as
far as any data source is concerned), so there is no `rugbydata` fixture
list to replay the way `real_fixtures.py` does for Six Nations etc. What
IS real: the pool draw itself, held 3 December 2025 in Sydney, and the
confirmed 24-team/6-pool format with a Round of 16. Simulating this
tournament means generating round-robin fixtures *within* each real pool
(order is ours to choose - "specific"/seeded or "random", see
`Tournament.run_world_cup_2027`), then building the knockout stage from
real results rather than guessing who qualifies.

Pools (as drawn):
    A: New Zealand, Australia, Chile, Hong Kong
    B: South Africa, Italy, Georgia, Romania
    C: Argentina, Fiji, Spain, Canada
    D: Ireland, Scotland, Uruguay, Portugal
    E: France, Japan, USA, Samoa
    F: England, Wales, Tonga, Zimbabwe

Knockout qualification (official): top 2 of each pool (12 teams) plus the
4 best third-placed teams advance to a 16-team knockout. The fixed R16
pairings are: winners of Pools A-D each face one of the four qualifying
third-placed teams (which one depends on *which* four groups' thirds
qualified - see `THIRD_PLACE_PAIRINGS` below, the official permutation
table so no team faces an opponent from its own pool); the winners of
Pools E and F play the runners-up of Pools D and B; the runners-up of
Pools A and C play the runners-up of Pools E and F. Everything past the
Round of 16 (QF/SF/Final bracket pairing) hasn't been published, so that
part still uses a standard bracket-order pairing.
"""

from __future__ import annotations

# The official "if these four groups' third-placed teams qualify, here's
# who plays the winners of Pools A/B/C/D" permutation table (there are
# exactly C(6,4)=15 ways to pick 4 of the 6 groups' thirds, covered below).
# Key: the frozenset of group letters whose third-placed team qualified.
# Value: {winner's pool letter -> which pool's third-placed team they face}.
# This is the actual mechanism used to guarantee no Round-of-16 match pits
# two teams that were in the same pool.
THIRD_PLACE_PAIRINGS: dict[frozenset, dict[str, str]] = {
    frozenset("ABCD"): {"A": "C", "B": "D", "C": "A", "D": "B"},
    frozenset("ABCE"): {"A": "C", "B": "E", "C": "A", "D": "B"},
    frozenset("ABCF"): {"A": "C", "B": "F", "C": "A", "D": "B"},
    frozenset("ABDE"): {"A": "E", "B": "D", "C": "A", "D": "B"},
    frozenset("ABDF"): {"A": "F", "B": "D", "C": "A", "D": "B"},
    frozenset("ABEF"): {"A": "E", "B": "F", "C": "A", "D": "B"},
    frozenset("ACDE"): {"A": "C", "B": "D", "C": "A", "D": "E"},
    frozenset("ACDF"): {"A": "C", "B": "D", "C": "A", "D": "F"},
    frozenset("ACEF"): {"A": "C", "B": "E", "C": "A", "D": "F"},
    frozenset("ADEF"): {"A": "E", "B": "D", "C": "A", "D": "F"},
    frozenset("BCDE"): {"A": "C", "B": "D", "C": "E", "D": "B"},
    frozenset("BCDF"): {"A": "C", "B": "D", "C": "F", "D": "B"},
    frozenset("BCEF"): {"A": "C", "B": "E", "C": "F", "D": "B"},
    frozenset("BDEF"): {"A": "E", "B": "D", "C": "F", "D": "B"},
    frozenset("CDEF"): {"A": "C", "B": "D", "C": "E", "D": "F"},
}

POOLS_2027 = {
    "A": ["New Zealand", "Australia", "Chile", "Hong Kong"],
    "B": ["South Africa", "Italy", "Georgia", "Romania"],
    "C": ["Argentina", "Fiji", "Spain", "Canada"],
    "D": ["Ireland", "Scotland", "Uruguay", "Portugal"],
    "E": ["France", "Japan", "USA", "Samoa"],
    "F": ["England", "Wales", "Tonga", "Zimbabwe"],
}

# Nation display name -> POOLS union short code, so a caller only has to
# supply Team objects keyed the way `POOLS`/`get_all_legends` already name
# them. ("Hong Kong" is nicknamed "Hong Kong China" in some contexts, but
# the dataset/Wikipedia pipeline both use the plain "Hong Kong" pool code.)
CODE_BY_NATION = {
    "New Zealand": "NZL", "Australia": "AUS", "Chile": "CHI", "Hong Kong": "HKG",
    "South Africa": "RSA", "Italy": "ITA", "Georgia": "GEO", "Romania": "ROU",
    "Argentina": "ARG", "Fiji": "FIJ", "Spain": "ESP", "Canada": "CAN",
    "Ireland": "IRE", "Scotland": "SCO", "Uruguay": "URU", "Portugal": "POR",
    "France": "FRA", "Japan": "JPN", "USA": "USA", "Samoa": "SAM",
    "England": "ENG", "Wales": "WAL", "Tonga": "TGA", "Zimbabwe": "ZIM",
}

ALL_TEAMS_2027 = [name for pool in POOLS_2027.values() for name in pool]
