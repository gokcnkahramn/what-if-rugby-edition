"""Fiji international pool.

rugbydata has no 2026 rows for Fiji's team_id (confirmed: their team file's
most recent matches are from 2025's Pacific Nations Cup). For season="2026",
`build_union_pool_2026` fills the actual 2026 squad from Wikipedia instead
(cross-referenced against rugbydata's global player registry for real stats
where possible), so this no longer needs to silently substitute 2025 data
or lean on the small manual list - both stay only as last-resort fallbacks.
"""

from __future__ import annotations

from typing import List

from ...models.attributes import Attributes
from ...models.player import Player
from ...models.position import Position
from ..sources.pool_builder import DEFAULT_SEASON, build_union_pool, build_union_pool_2026

_MANUAL_POOL: List[Player] = [
    Player("Semi Radradra", "Fiji", Position.OUTSIDE_CENTRE,
           Attributes(strength=90, pace=86, footwork=84, offload=84, tackling=72,
                      game_intelligence=76, versatility=55),
           era="'26", notes="2026 Nations Championship squad.", data_source="manual"),
    Player("Josua Tuisova", "Fiji", Position.INSIDE_CENTRE,
           Attributes(strength=94, pace=84, footwork=70, tackling=78, offload=70,
                      versatility=45),
           era="'26", notes="2026 Nations Championship squad.", data_source="manual"),
    Player("Levani Botia", "Fiji", Position.BLINDSIDE_FLANKER,
           Attributes(tackling=90, strength=84, fitness=82, tackle_technique=86,
                      game_intelligence=76, versatility=60),
           era="'26", notes="2026 Nations Championship squad - return to Test rugby.",
           data_source="manual"),
    Player("Filimoni Botitu", "Fiji", Position.INSIDE_CENTRE,
           Attributes(strength=82, pace=76, tackling=74, passing=70, offload=68,
                      versatility=45),
           era="'26", notes="2026 Nations Championship squad.", data_source="manual"),
    Player("Selestino Ravutaumada", "Fiji", Position.RIGHT_WING,
           Attributes(pace=90, footwork=82, aerial=66, tackling=64, agility=84,
                      versatility=40),
           era="'26", notes="2026 Nations Championship squad.", data_source="manual"),
]


def get_pool(season: str = DEFAULT_SEASON) -> List[Player]:
    pool = build_union_pool_2026("FIJ") if season == "2026" else build_union_pool("FIJ", season=season)
    if pool:
        return pool
    if season == DEFAULT_SEASON:
        return list(_MANUAL_POOL)
    return []
