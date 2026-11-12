"""Namibia ("Welwitschias") international pool.

rugbydata has rows for Namibia's team_id, but none carry a player-level
roster list (every match's `players` list is empty). For season="2026",
`build_union_pool_2026` fills the squad from Wikipedia instead (cross-
referenced against rugbydata's global player registry for real stats where
possible); the manual list below is a last-resort safety net otherwise.
"""

from __future__ import annotations

from typing import List

from ...models.attributes import Attributes
from ...models.player import Player
from ...models.position import Position
from ..sources.pool_builder import DEFAULT_SEASON, build_union_pool, build_union_pool_2026

_MANUAL_POOL: List[Player] = [
    Player("Johan Deysel", "Namibia", Position.INSIDE_CENTRE,
           Attributes(strength=78, pace=72, tackling=76, passing=68, offload=64,
                      game_intelligence=72, versatility=45),
           era="'25", notes="Veteran centre, recalled for 2027 RWC qualification.",
           data_source="manual"),
    Player("Divan Rossouw", "Namibia", Position.OUTSIDE_CENTRE,
           Attributes(pace=80, footwork=72, tackling=68, passing=66, offload=62,
                      versatility=40),
           era="'25", notes="Returned from Seattle Seawolves.", data_source="manual"),
    Player("Johannes Coetzee", "Namibia", Position.LOOSEHEAD_PROP,
           Attributes(scrummaging=78, strength=80, tackling=64, fitness=58, versatility=25),
           era="'25", notes="Veteran prop (late 30s).", data_source="manual"),
    Player("Torsten van Jaarsveld", "Namibia", Position.HOOKER,
           Attributes(scrummaging=70, lineout_throwing=68, tackling=66, handling=64,
                      versatility=30),
           era="'25", notes="Veteran hooker, 2025 tour squad.", data_source="manual"),
    Player("Prince Gaoseb", "Namibia", Position.OPENSIDE_FLANKER,
           Attributes(tackling=80, fitness=78, tackle_technique=76, game_intelligence=74,
                      leadership=82, versatility=45),
           era="'25", notes="Captain.", data_source="manual"),
    Player("Danco Burger", "Namibia", Position.NUMBER_8,
           Attributes(strength=76, tackling=74, pace=62, fitness=72, leadership=70,
                      versatility=40),
           era="'25", notes="Vice-captain.", data_source="manual"),
]


def get_pool(season: str = DEFAULT_SEASON) -> List[Player]:
    pool = build_union_pool_2026("NAM") if season == "2026" else build_union_pool("NAM", season=season)
    if pool:
        return pool
    return list(_MANUAL_POOL)
