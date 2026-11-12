"""Spain ("Los Leones") international pool.

rugbydata has zero player-level rows for Spain in any season (their matches
are recorded at team level only - every row's `players` list is empty,
unlike most other unions). For season="2026" this is a non-issue though:
`build_union_pool_2026` fills the whole squad from Wikipedia's "Current
squad" section instead (cross-referenced against rugbydata's global player
registry for real stats where possible). The manual list below is now only
a last-resort safety net for other seasons / if that ever comes back empty.
"""

from __future__ import annotations

from typing import List

from ...models.attributes import Attributes
from ...models.player import Player
from ...models.position import Position
from ..sources.pool_builder import DEFAULT_SEASON, build_union_pool, build_union_pool_2026

_MANUAL_POOL: List[Player] = [
    Player("Fernando Lopez", "Spain", Position.LOCK_1,
           Attributes(lineout_jumping=68, strength=74, tackling=72, scrummaging=66,
                      leadership=80, versatility=40),
           era="'25", notes="Captain, Rugby Europe Championship squad.", data_source="manual"),
    Player("Thierry Futeu", "Spain", Position.LOOSEHEAD_PROP,
           Attributes(scrummaging=68, strength=72, tackling=62, fitness=68, versatility=30),
           era="'25", notes="Front-row squad option.", data_source="manual"),
    Player("Jon Zabala", "Spain", Position.TIGHTHEAD_PROP,
           Attributes(scrummaging=70, strength=73, tackling=60, fitness=66, versatility=30),
           era="'25", notes="Front-row squad option.", data_source="manual"),
    Player("Joel Merkler", "Spain", Position.HOOKER,
           Attributes(scrummaging=64, lineout_throwing=62, tackling=64, handling=62, versatility=35),
           era="'25", notes="Front-row squad option.", data_source="manual"),
    Player("Hugo Gonzalez", "Spain", Position.TIGHTHEAD_PROP,
           Attributes(scrummaging=66, strength=70, tackling=60, fitness=64, versatility=30),
           era="'25", notes="Front-row squad option.", data_source="manual"),
    Player("Egoitz Garcia", "Spain", Position.RIGHT_WING,
           Attributes(pace=78, footwork=70, aerial=58, tackling=58, agility=72, versatility=35),
           era="'25", notes="Winger, squad newcomer.", data_source="manual"),
]


def get_pool(season: str = DEFAULT_SEASON) -> List[Player]:
    pool = build_union_pool_2026("ESP") if season == "2026" else build_union_pool("ESP", season=season)
    if pool:
        return pool
    return list(_MANUAL_POOL)
