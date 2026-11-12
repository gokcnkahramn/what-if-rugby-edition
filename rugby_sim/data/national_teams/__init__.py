"""Registry of international player pools: Tier 1 + Tier 2 unions (via the
rugbydata pipeline) plus the Barbarians (manual, since they're not a union
and aren't in that dataset at all).

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
"""

from __future__ import annotations

from typing import Callable, Dict, List

from . import (
    argentina,
    australia,
    barbarians,
    canada,
    chile,
    england,
    fiji,
    france,
    georgia,
    hongkong,
    ireland,
    italy,
    japan,
    namibia,
    new_zealand,
    portugal,
    romania,
    samoa,
    scotland,
    south_africa,
    spain,
    tonga,
    uruguay,
    usa,
    wales,
    zimbabwe,
)
from ...models.player import Player

POOLS: Dict[str, Callable[[], List[Player]]] = {
    # Tier 1
    "ENG": england.get_pool,
    "FRA": france.get_pool,
    "IRE": ireland.get_pool,
    "SCO": scotland.get_pool,
    "WAL": wales.get_pool,
    "ITA": italy.get_pool,
    "NZL": new_zealand.get_pool,
    "AUS": australia.get_pool,
    "RSA": south_africa.get_pool,
    "ARG": argentina.get_pool,
    "JPN": japan.get_pool,
    "FIJ": fiji.get_pool,
    # Tier 2 (2027 Rugby World Cup picture)
    "GEO": georgia.get_pool,
    "ROU": romania.get_pool,
    "ESP": spain.get_pool,
    "POR": portugal.get_pool,
    "SAM": samoa.get_pool,
    "TGA": tonga.get_pool,
    "USA": usa.get_pool,
    "CAN": canada.get_pool,
    "URU": uruguay.get_pool,
    "CHI": chile.get_pool,
    "NAM": namibia.get_pool,
    "HKG": hongkong.get_pool,
    "ZIM": zimbabwe.get_pool,
    # Invitational
    "BAR": barbarians.get_pool,
}

__all__ = ["POOLS"]
