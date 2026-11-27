"""Historical Six Nations Championship squads (2009-2021) from Wikipedia's
dedicated "`<year>` Six Nations Championship squads" pages, PLUS (new,
below) full-season real-fixture-order replay for 2000-2008 via the main
season article's own per-match `{{Rugbybox}}` + lineup-table format (see
`season_match_pages.py`) - a genuinely richer real source for those years:
real chronological match order (this module's own 2009-2021 path has no
real order at all, since the separate squads page it reads has no
fixture list), not just a synthetic round-robin shape.

Why this range: pages for this competition exist back further, but earlier
ones (checked live: 2000-2008) list players as a bare numbered wikilink
list with **no position** at all (`# [[Jonny Wilkinson]]`), which our
position-based drafting can't use - they only switch to the same
`{{nat rs player|pos=...}}` template the World Cup/current-squad pipelines
already parse from 2009 onward (verified live for 2009-2025). 2022 onward
is already covered by the *current* pipeline (`pool_builder.py`, real
rugbydata stats), so this module's useful range is 2009-2021.

Format differs from the World Cup squads page in two ways that matter for
parsing:
- No pool grouping - just one `==<Team>==` heading per team, six of them.
- The name field's own template is inconsistent year to year (confirmed
  live, 2009-2021): some editions use the same `{{sortname|First|Last}}`
  the World Cup squads pages use, others a plain wikilink
  (`name=[[Jonny Wilkinson]]` or `name=[[Alex Corbisiero|Corbisiero]]`) -
  both are tried per player line, falling back to the full display name
  (no separate first/last split needed for the wikilink case).

Ratings follow the same honest convention as `historical_rwc.py`: real
stats via name cross-reference into rugbydata wherever a career overlaps
2018+, position-archetype scaled by union strength otherwise.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ...models.player import Player
from ...models.position import Position
from .attribute_mapping import DEFAULT_UNION_STRENGTH, UNION_STRENGTH, scale_to_union_strength
from .season_match_pages import MATCH_POS_CODE_MAP, parse_season_matches
from .wikipedia_squad import (
    POS_CODE_MAP,
    _archetype_attributes,
    _cross_reference_attributes,
    fetch_wikitext,
)

_NATION_TO_STRENGTH_CODE = {
    "England": "ENG", "France": "FRA", "Ireland": "IRE",
    "Italy": "ITA", "Scotland": "SCO", "Wales": "WAL",
}

# Verified live: 2009-2025 all use the `{{nat rs player|pos=...}}` template
# throughout; 2022+ is already covered by the current-season pipeline (real
# rugbydata stats), so only the pre-rugbydata years are exposed here.
AVAILABLE_SIX_NATIONS_YEARS = list(range(2000, 2022))

_SIX_NATIONS_TEAMS = ("England", "France", "Ireland", "Italy", "Scotland", "Wales")
_CODE_TO_TEAM = {"ENG": "England", "FRA": "France", "IRE": "Ireland", "ITA": "Italy", "SCO": "Scotland", "WAL": "Wales"}

_team_heading = re.compile(r"^==\s*(?:\[\[[^\]|]*\|)?([A-Za-z]+)\]?\]?\s*==\s*$")
# Some editions (e.g. 2014) use a flag template instead of the plain name:
# `=={{Ru|ENG}}==` or `=={{Ru|FRA|1974}}==`.
_team_heading_flag = re.compile(r"^==\s*\{\{[Rr]u\|([A-Za-z]+)(?:\|[^}]*)?\}\}\s*==\s*$")
# The name field's template varies by year - some use the same
# `{{sortname|First|Last}}` the World Cup squads pages use, others a plain
# wikilink (`[[Name]]`/`[[Name|Display]]`) - both are tried per line.
_name_field_sortname = re.compile(r"name=\{\{sortname\|([^|}]+)\|([^|}]+)")
_name_field_wikilink = re.compile(r"name=\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def six_nations_squads_page_title(year: int) -> str:
    return f"{year} Six Nations Championship squads"


def fetch_six_nations_squads_wikitext(year: int):
    return fetch_wikitext(six_nations_squads_page_title(year))


def parse_six_nations_squads(wikitext: str) -> Dict[str, List[dict]]:
    """Walks `==<Team>==` headers, collecting `{{nat rs player}}` entries
    for each of the six teams. Returns `{team_name: [entry, ...]}`."""
    teams: Dict[str, List[dict]] = {}
    current_team = None
    seen_names: set = set()

    for line in wikitext.splitlines():
        stripped = line.strip()
        m_flag = _team_heading_flag.match(stripped)
        m = _team_heading.match(stripped) if not m_flag else None
        if m_flag or m:
            candidate = _CODE_TO_TEAM.get(m_flag.group(1).upper()) if m_flag else m.group(1).strip()
            if candidate in _SIX_NATIONS_TEAMS:
                current_team = candidate
                teams.setdefault(current_team, [])
                seen_names = set()
            else:
                current_team = None
            continue

        if not current_team or "nat rs player" not in line:
            continue
        pos_m = re.search(r"pos=(\w+)", line)
        if not pos_m:
            continue
        sortname_m = _name_field_sortname.search(line)
        if sortname_m:
            full_name = f"{sortname_m.group(1).strip()} {sortname_m.group(2).strip()}"
        else:
            wikilink_m = _name_field_wikilink.search(line)
            if not wikilink_m:
                continue
            full_name = (wikilink_m.group(2) or wikilink_m.group(1)).strip()
        key = full_name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        caps_m = re.search(r"\|caps=(\d+)", line)
        teams[current_team].append({
            "pos": pos_m.group(1),
            "name": full_name,
            "caps": int(caps_m.group(1)) if caps_m else 0,
        })

    return teams


def build_historical_six_nations_pool(year: int, nation: str, entries: List[dict]) -> List[Player]:
    strength_code = _NATION_TO_STRENGTH_CODE.get(nation)
    strength = UNION_STRENGTH.get(strength_code, DEFAULT_UNION_STRENGTH) if strength_code else DEFAULT_UNION_STRENGTH

    from .pool_builder import _global_reference_peer_proxies
    peer_proxies_by_position = _global_reference_peer_proxies("2026")

    era = f"'{str(year)[-2:]}"
    pool: List[Player] = []
    for entry in entries:
        position = POS_CODE_MAP.get(entry["pos"])
        if position is None:
            continue
        full_name = entry["name"]
        attrs, source = _cross_reference_attributes(
            full_name, peer_proxies=peer_proxies_by_position.get(position),
            position=position, nation=nation,
        )
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
        pool.append(Player(
            name=full_name,
            nation=nation,
            natural_position=position,
            attributes=attrs,
            era=era,
            notes=(
                f"{year} Six Nations Championship squad. "
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


_SIX_NATIONS_CACHE: Dict[int, Dict[str, List[Player]]] = {}


def get_six_nations_year_data(year: int) -> Dict[str, List[Player]]:
    """Returns `{team_name: [Player, ...]}` for one Six Nations edition -
    all six teams, a fixed field for this competition (unlike the World
    Cup's varying participant list). For 2000-2008, this now dispatches to
    the real-fixture-order season-page path below; for 2009-2021 it's the
    original squads-page path (no real match order survives there)."""
    if 2000 <= year < 2009:
        return _get_six_nations_year_squads_from_season_page(year)
    if year in _SIX_NATIONS_CACHE:
        return _SIX_NATIONS_CACHE[year]

    wikitext = fetch_six_nations_squads_wikitext(year)
    if not wikitext:
        raise ValueError(f"No squads page found for the {year} Six Nations Championship.")
    parsed = parse_six_nations_squads(wikitext)
    if not parsed or any(not entries for entries in parsed.values()):
        raise ValueError(
            f"Squads page for {year} didn't parse cleanly into all six teams - format may differ."
        )

    squads = {
        team_name: build_historical_six_nations_pool(year, team_name, entries)
        for team_name, entries in parsed.items()
    }
    _SIX_NATIONS_CACHE[year] = squads
    return squads


# ---------------------------------------------------------------------------
# 2000-2008: real per-match lineup tables + real fixture order, straight off
# the main "`<year>` Six Nations Championship" season article (NOT the
# separate squads page above) - see `season_match_pages.py`'s own module
# docstring for why this is both available and a strictly richer real
# source for these years. Verified live for all of 2000-2008 (one postponed
# fixture in 2002 aside, confirmed a real, not a parsing, gap).
AVAILABLE_SIX_NATIONS_REAL_ORDER_YEARS = list(range(2000, 2009))

_CODE_TO_SIX_NATIONS_TEAM = _CODE_TO_TEAM
_SIX_NATIONS_SEASON_FIXTURES_CACHE: Dict[int, list] = {}
_SIX_NATIONS_SEASON_SQUADS_CACHE: Dict[int, Dict[str, List[Player]]] = {}


def _season_page_title(year: int) -> str:
    return f"{year} Six Nations Championship"


def _build_pool_from_season_entries(year: int, nation: str, entries) -> List[Player]:
    """Same real cross-reference/archetype/union-strength pipeline as
    `build_historical_six_nations_pool` above, just fed from
    `season_match_pages.SeasonMatchLineupEntry` (deduped by name across
    every match that nation played this season) instead of the squads
    page's own entry dicts."""
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
        pool.append(Player(
            name=entry.name, nation=nation, natural_position=position, attributes=attrs, era=era,
            notes=(
                f"{year} Six Nations Championship - real match-day lineup (season article). "
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


def _get_six_nations_season_matches(year: int):
    if year not in _SIX_NATIONS_SEASON_FIXTURES_CACHE:
        wikitext = fetch_wikitext(_season_page_title(year))
        matches = parse_season_matches(wikitext)
        if not matches:
            raise ValueError(f"{_season_page_title(year)} didn't parse into any real matches.")
        _SIX_NATIONS_SEASON_FIXTURES_CACHE[year] = matches
    return _SIX_NATIONS_SEASON_FIXTURES_CACHE[year]


def _get_six_nations_year_squads_from_season_page(year: int) -> Dict[str, List[Player]]:
    if year in _SIX_NATIONS_SEASON_SQUADS_CACHE:
        return _SIX_NATIONS_SEASON_SQUADS_CACHE[year]
    matches = _get_six_nations_season_matches(year)
    entries_by_nation: Dict[str, dict] = {}
    for m in matches:
        for code, lineup in ((m.home_code, m.home_lineup), (m.away_code, m.away_lineup)):
            nation = _CODE_TO_SIX_NATIONS_TEAM.get(code)
            if nation is None:
                continue
            bucket = entries_by_nation.setdefault(nation, {})
            for e in lineup:
                bucket.setdefault(e.name, e)  # first real sighting wins, no duplicate players
    squads = {
        nation: _build_pool_from_season_entries(year, nation, entries.values())
        for nation, entries in entries_by_nation.items()
    }
    if len(squads) < 6 or any(len(p) < 15 for p in squads.values()):
        raise ValueError(
            f"{_season_page_title(year)} didn't parse into all six teams' full real lineups - format may differ."
        )
    _SIX_NATIONS_SEASON_SQUADS_CACHE[year] = squads
    return squads


def get_six_nations_year_fixtures(year: int) -> Optional[List[Tuple[str, str, int, int]]]:
    """The REAL chronological fixture list for a 2000-2008 edition -
    `(home_nation, away_nation, home_score, away_score)` in real page
    order - or `None` for a year that only has the squads-page path (no
    real order recoverable there, see `get_six_nations_year_data`'s own
    docstring). A match this project's own simulation doesn't need the
    REAL score for (only the real pairing/order matters for replay), kept
    here anyway since it's free and useful for display."""
    if not (2000 <= year < 2009):
        return None
    matches = _get_six_nations_season_matches(year)
    fixtures = []
    for m in matches:
        home = _CODE_TO_SIX_NATIONS_TEAM.get(m.home_code)
        away = _CODE_TO_SIX_NATIONS_TEAM.get(m.away_code)
        if home is None or away is None or m.home_score is None or m.away_score is None:
            continue
        fixtures.append((home, away, m.home_score, m.away_score))
    return fixtures
