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
from ..sources.wikipedia_squad import build_wikipedia_pool


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


def lazy_wikipedia_only_pool(short_code: str, nation: str) -> Callable[..., List[Player]]:
    """For a union rugbydata has no player-level data for in ANY season
    (e.g. Hong Kong, Zimbabwe) - every season's pool comes from that
    union's Wikipedia "Current squad" section instead (cross-referenced
    against rugbydata's global player registry for real stats where
    possible), via `wikipedia_squad.build_wikipedia_pool` directly."""
    cache: dict = {}

    def get_pool(season: str = DEFAULT_SEASON) -> List[Player]:
        if season not in cache:
            cache[season] = build_wikipedia_pool(short_code, nation, season=season)
        return cache[season]

    return get_pool


def lazy_pool_with_manual_fallback(
    short_code: str, manual_pool: List[Player]
) -> Callable[..., List[Player]]:
    """Like `lazy_pool_2026_via_wikipedia`, but with a small hand-entered
    `manual_pool` as a last-resort safety net for whenever the real
    build (rugbydata, or rugbydata+Wikipedia for 2026) comes back empty -
    for any season, not just the default one (an earlier, per-union-file
    version of this had Fiji's fallback only fire for `season ==
    DEFAULT_SEASON`, inconsistent with Spain/Namibia's - no evidence that
    restriction was intentional, so this shared version fixes it: the
    safety net fires whenever it's genuinely needed, any season)."""
    cache: dict = {}

    def get_pool(season: str = DEFAULT_SEASON) -> List[Player]:
        if season not in cache:
            pool = (
                build_union_pool_2026(short_code) if season == "2026"
                else build_union_pool(short_code, season=season)
            )
            cache[season] = pool if pool else list(manual_pool)
        return cache[season]

    return get_pool


def lazy_invitational_pool(builder: Callable[[], List[Player]]) -> Callable[..., List[Player]]:
    """For an invitational/composite side (Barbarians, British & Irish
    Lions, Pacific Islanders) that isn't a union with a per-year roster -
    `builder` is called once (a static list, or a real Wikipedia scrape)
    and cached; `season` is accepted for interface parity with every other
    pool but otherwise ignored, same convention each of these modules used
    individually before this helper existed."""
    cache: List[Player] = []

    def get_pool(season: str = "2026") -> List[Player]:
        if not cache:
            cache.extend(builder())
        return list(cache)

    return get_pool
