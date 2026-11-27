"""Historical Rugby Championship / Tri Nations full-season replay
(1996-2025) - the real per-match lineup tables and real chronological
fixture order parsed straight off each season's own Wikipedia article (see
`season_match_pages.py`'s own module docstring for why this works and
what's confirmed). There is no separate "squads" page for this
competition at all (unlike Six Nations) - the season article alone is a
complete, real source for both the roster and the fixture list.

Verified live (this session), every single year 1996-2025: a real
`{{Rugbybox|...}}` block per match plus a real two-team position-coded
lineup table immediately after it. 2026 is deliberately NOT in
`AVAILABLE_RUGBY_CHAMPIONSHIP_YEARS` - the Rugby Championship wasn't held
that year (absorbed into the new Nations Championship), not a parsing gap.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ...models.player import Player
from ...models.position import Position
from .attribute_mapping import DEFAULT_UNION_STRENGTH, UNION_STRENGTH, scale_to_union_strength
from .season_match_pages import MATCH_POS_CODE_MAP, parse_season_matches
from .wikipedia_squad import _archetype_attributes, _cross_reference_attributes, fetch_wikitext

AVAILABLE_RUGBY_CHAMPIONSHIP_YEARS = list(range(1996, 2026))

_CODE_TO_NATION = {
    "NZL": "New Zealand", "AUS": "Australia",
    # South Africa is tagged "RSA" most years but "ZAF" (ISO code) on some
    # pages (confirmed live: 2015) - both real, both meant the same team.
    "RSA": "South Africa", "ZAF": "South Africa",
    "ARG": "Argentina",
}
_NATION_TO_STRENGTH_CODE = {
    "New Zealand": "NZL", "Australia": "AUS", "South Africa": "RSA", "Argentina": "ARG",
}

_SEASON_FIXTURES_CACHE: Dict[int, list] = {}
_SEASON_SQUADS_CACHE: Dict[int, Dict[str, List[Player]]] = {}
_SEASON_FIXTURES_RESULT_CACHE: Dict[int, List[Tuple[str, str, int, int]]] = {}


def rugby_championship_page_title(year: int) -> str:
    return f"{year} Tri Nations Series" if year < 2012 else f"{year} Rugby Championship"


def _build_pool_from_season_entries(year: int, nation: str, entries) -> List[Player]:
    """Same real cross-reference/archetype/union-strength pipeline every
    other historical-Wikipedia pool in this project already uses (see
    `historical_six_nations.py`'s own equivalent) - fed from
    `season_match_pages.SeasonMatchLineupEntry`, deduped by name across
    every real match that nation played this season."""
    strength_code = _NATION_TO_STRENGTH_CODE.get(nation)
    strength = UNION_STRENGTH.get(strength_code, DEFAULT_UNION_STRENGTH) if strength_code else DEFAULT_UNION_STRENGTH
    era = f"'{str(year)[-2:]}"
    pool: List[Player] = []
    for entry in entries:
        position_name = MATCH_POS_CODE_MAP.get(entry.position_code)
        if position_name is None:
            continue
        position = Position(position_name)
        attrs, source = _cross_reference_attributes(entry.name, position=position, nation=nation)
        if attrs is None:
            attrs = _archetype_attributes(position)
        if source != "rugby08_dataset":
            attrs = scale_to_union_strength(attrs, strength)
        if source == "rugby08_dataset":
            data_source = source
        elif source == "wikipedia":
            data_source = "historical_wikipedia"
        else:
            data_source = "historical_archetype"
        competition = "Tri Nations Series" if year < 2012 else "Rugby Championship"
        pool.append(Player(
            name=entry.name, nation=nation, natural_position=position, attributes=attrs, era=era,
            notes=(
                f"{year} {competition} - real match-day lineup (season article). "
                + ("Attributes from real rugbydata career stats (cross-referenced by name)."
                   if source == "wikipedia" else
                   "Real individual ratings from the 2007 EA Sports Rugby 08 game database "
                   "(see rugby08_dataset.py)."
                   if source == "rugby08_dataset" else
                   "No rugbydata history found for this era/name, so attributes are a "
                   "generic position-archetype estimate, not a scouted rating.")
            ),
            data_source=data_source,
        ))
    return pool


def _get_season_matches(year: int):
    if year not in _SEASON_FIXTURES_CACHE:
        wikitext = fetch_wikitext(rugby_championship_page_title(year))
        matches = parse_season_matches(wikitext)
        if not matches:
            raise ValueError(f"{rugby_championship_page_title(year)} didn't parse into any real matches.")
        _SEASON_FIXTURES_CACHE[year] = matches
    return _SEASON_FIXTURES_CACHE[year]


def get_rugby_championship_year_data(year: int) -> Tuple[Dict[str, List[Player]], List[Tuple[str, str, int, int]]]:
    """Returns `(squads, fixtures)` for one real Tri Nations/Rugby
    Championship edition: `squads` = `{nation: [Player, ...]}` (every real
    team that played this season - 3 for 1996-2011 Tri Nations, 4 from
    2012's Rugby Championship onward, since Argentina joined that year);
    `fixtures` = `[(home_nation, away_nation, home_score, away_score), ...]`
    in the REAL chronological order the matches were actually played."""
    if year in _SEASON_SQUADS_CACHE:
        return _SEASON_SQUADS_CACHE[year], _SEASON_FIXTURES_RESULT_CACHE[year]

    matches = _get_season_matches(year)
    entries_by_nation: Dict[str, dict] = {}
    fixtures: List[Tuple[str, str, int, int]] = []
    for m in matches:
        home = _CODE_TO_NATION.get(m.home_code)
        away = _CODE_TO_NATION.get(m.away_code)
        for code, nation, lineup in ((m.home_code, home, m.home_lineup), (m.away_code, away, m.away_lineup)):
            if nation is None:
                continue
            bucket = entries_by_nation.setdefault(nation, {})
            for e in lineup:
                bucket.setdefault(e.name, e)  # first real sighting wins, no duplicate players
        if home is not None and away is not None and m.home_score is not None and m.away_score is not None:
            fixtures.append((home, away, m.home_score, m.away_score))

    squads = {
        nation: _build_pool_from_season_entries(year, nation, entries.values())
        for nation, entries in entries_by_nation.items()
    }
    # Not a fixed "3 before 2012, 4 after" count: 2020's real Rugby
    # Championship genuinely had only 3 teams (South Africa withdrew,
    # COVID-19) - a real historical fact, not a parsing gap, so the floor
    # here is just "a genuine competition happened" (>= 3 real full
    # squads), never a hardcoded expectation of who took part.
    if len(squads) < 3 or any(len(p) < 15 for p in squads.values()) or not fixtures:
        raise ValueError(
            f"{rugby_championship_page_title(year)} didn't parse into all real teams' full real "
            "lineups and a real fixture list - format may differ."
        )
    _SEASON_SQUADS_CACHE[year] = squads
    _SEASON_FIXTURES_RESULT_CACHE[year] = fixtures
    return squads, fixtures
