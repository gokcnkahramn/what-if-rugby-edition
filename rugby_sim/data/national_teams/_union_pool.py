"""Shared lazy-loading helper for the per-union pool modules.

Each union module (england.py, france.py, ...) is a thin wrapper around
`build_union_pool` so importing `rugby_sim.data.national_teams` doesn't
trigger a dozen network pulls - a given season's pool is only fetched (and
then cached on disk by `rugby_data_client`) the first time `get_pool()` is
called for that season.
"""

from __future__ import annotations

from typing import Callable, List

from ...models.player import Player
from ..sources.pool_builder import DEFAULT_SEASON, build_union_pool, build_union_pool_2026


def lazy_pool(short_code: str) -> Callable[..., List[Player]]:
    cache: dict = {}

    def get_pool(season: str = DEFAULT_SEASON) -> List[Player]:
        if season not in cache:
            cache[season] = build_union_pool(short_code, season=season)
        return cache[season]

    return get_pool


def lazy_pool_2026_via_wikipedia(short_code: str) -> Callable[..., List[Player]]:
    """Like `lazy_pool`, but for `season="2026"` specifically it uses
    `build_union_pool_2026` - real rugbydata 2026 caps topped up with that
    union's actual 2026 Wikipedia squad - instead of rugbydata alone (which,
    for several Tier 2 unions, has thin or no 2026 player-level data). Any
    other season still goes through plain `build_union_pool`."""
    cache: dict = {}

    def get_pool(season: str = DEFAULT_SEASON) -> List[Player]:
        if season not in cache:
            if season == "2026":
                cache[season] = build_union_pool_2026(short_code)
            else:
                cache[season] = build_union_pool(short_code, season=season)
        return cache[season]

    return get_pool
