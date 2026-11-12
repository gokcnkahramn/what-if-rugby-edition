"""Hong Kong international pool - Wikipedia-only (no rugbydata team_id at
all for this union); needed for the 2027 Rugby World Cup draw (Pool A)."""

from typing import List

from ...models.player import Player
from ..sources.pool_builder import DEFAULT_SEASON
from ..sources.wikipedia_squad import build_wikipedia_pool

_cache: dict = {}


def get_pool(season: str = DEFAULT_SEASON) -> List[Player]:
    if season not in _cache:
        _cache[season] = build_wikipedia_pool("HKG", "Hong Kong", season=season)
    return _cache[season]
