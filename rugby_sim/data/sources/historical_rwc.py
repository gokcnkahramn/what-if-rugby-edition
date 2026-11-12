"""Historical Rugby World Cup squads (professional era, 1995-) from
Wikipedia's dedicated "`<year>` Rugby World Cup squads" pages.

Why this is feasible at all: `rugbydata` (our real box-score source) only
covers 2018-2026 - nowhere near 1995, so there's no live stats source for
these eras. But every professional-era World Cup has a Wikipedia page
built from the *exact same* `{{nat rs player|pos=...|name=...|caps=...}}`
template `wikipedia_squad.parse_current_squad` already parses for current
national squads - just organized as `==Pool A==` -> `===<Team>===`
subsections for ~20 teams on one page, instead of one team's "Current
squad" section. Confirmed live for 1995 and 2003 (both match this format).

Ratings: these players have no real box-score stats for their career at
that era (pre-2018), so each one gets the same cross-reference-then-
archetype treatment as the current-squad Wikipedia pipeline (real stats
IF a name cross-references into rugbydata - realistic mainly for careers
that extend into 2018+, e.g. 2019/2023 squads - archetype otherwise), then
the same union-strength scaling. `data_source="historical_wikipedia"`
keeps this visually distinct from the current-squad pipeline even though
the underlying logic is shared.
"""

from __future__ import annotations

import re
from typing import Dict, List

from ...models.player import Player
from .attribute_mapping import DEFAULT_UNION_STRENGTH, UNION_STRENGTH, scale_to_union_strength
from .wikipedia_squad import (
    POS_CODE_MAP,
    _archetype_attributes,
    _cross_reference_attributes,
    fetch_wikitext,
)

# A handful of past participants have no `POOLS` code at all (not relevant
# to 2026/2027), but still need a union-strength lookup key - map them to
# the closest code we do track, or leave unmapped (falls back to
# `DEFAULT_UNION_STRENGTH`, a reasonable "competitive Tier 2" assumption).
_NATION_TO_STRENGTH_CODE = {
    "Australia": "AUS", "Ireland": "IRE", "Argentina": "ARG", "Romania": "ROU",
    "Namibia": "NAM", "France": "FRA", "Scotland": "SCO", "Fiji": "FIJ",
    "United States": "USA", "Japan": "JPN", "England": "ENG",
    "South Africa": "RSA", "Samoa": "SAM", "Western Samoa": "SAM",
    "Uruguay": "URU", "Georgia": "GEO",
    "New Zealand": "NZL", "Wales": "WAL", "Italy": "ITA", "Canada": "CAN",
    "Tonga": "TGA", "Spain": "ESP", "Portugal": "POR", "Chile": "CHI",
    "Zimbabwe": "ZIM", "Hong Kong": "HKG",
}

# Every professional-era (1995-) Rugby World Cup edition, confirmed live to
# have a "`<year>` Rugby World Cup squads" Wikipedia page in the expected
# `{{nat rs player}}` format - see plan item 11, Phase 2 (verification
# only, no new code needed once the 2003 pilot worked).
AVAILABLE_RWC_YEARS = [1995, 1999, 2003, 2007, 2011, 2015, 2019, 2023]


def rwc_squads_page_title(year: int) -> str:
    return f"{year} Rugby World Cup squads"


def fetch_rwc_squads_wikitext(year: int):
    return fetch_wikitext(rwc_squads_page_title(year))


def parse_rwc_squads(wikitext: str) -> Dict[str, Dict[str, List[dict]]]:
    """Walks `==Pool X==` / `===Team===` headers, collecting the same
    `{{nat rs player}}` entries `parse_current_squad` extracts from a
    single "Current squad" section - here, once per team on the page.
    Returns `{pool_name: {team_name: [entries]}}`."""
    pools: Dict[str, Dict[str, List[dict]]] = {}
    current_pool = None
    current_team = None
    seen_names: set = set()

    level2_heading = re.compile(r"^==([^=].*?)==\s*$")
    level3_heading = re.compile(r"^===\s*([^=]+?)\s*===\s*$")

    for line in wikitext.splitlines():
        stripped = line.strip()

        m2 = level2_heading.match(stripped)
        if m2:
            title = m2.group(1).strip()
            if title.lower().startswith("pool"):
                current_pool = title
                pools.setdefault(current_pool, {})
            else:
                current_pool = None
            current_team = None
            continue

        if current_pool:
            m3 = level3_heading.match(stripped)
            if m3:
                current_team = m3.group(1).strip()
                pools[current_pool][current_team] = []
                seen_names = set()
                continue

        if not (current_pool and current_team):
            continue
        if "nat rs player" not in line:
            continue

        pos_m = re.search(r"pos=(\w+)", line)
        name_m = re.search(r"name=\{\{sortname\|([^|}]+)\|([^|}]+)", line)
        caps_m = re.search(r"\|caps=(\d+)", line)
        if not (pos_m and name_m):
            continue
        first, last = name_m.group(1).strip(), name_m.group(2).strip()
        key = f"{first} {last}".lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        pools[current_pool][current_team].append({
            "pos": pos_m.group(1),
            "first": first,
            "last": last,
            "caps": int(caps_m.group(1)) if caps_m else 0,
        })

    return pools


def build_historical_pool(year: int, nation: str, entries: List[dict]) -> List[Player]:
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
        full_name = f"{entry['first']} {entry['last']}"
        attrs, source = _cross_reference_attributes(
            full_name, peer_proxies=peer_proxies_by_position.get(position)
        )
        if attrs is None:
            attrs = _archetype_attributes(position)
        attrs = scale_to_union_strength(attrs, strength)
        # Keep the real-vs-archetype distinction visible (same honesty
        # convention as the current-squad Wikipedia pipeline), just
        # prefixed so it's obviously a *historical* pull either way.
        data_source = "historical_wikipedia" if source == "wikipedia" else "historical_archetype"
        pool.append(Player(
            name=full_name,
            nation=nation,
            natural_position=position,
            attributes=attrs,
            era=era,
            notes=(
                f"{year} Rugby World Cup squad. "
                + ("Attributes from real rugbydata career stats (cross-referenced by name) - "
                   "likely a career that extended into rugbydata's 2018+ coverage."
                   if source == "wikipedia" else
                   "No rugbydata history found for this era/name, so attributes are a "
                   "generic position-archetype estimate, not a scouted rating.")
            ),
            data_source=data_source,
        ))
    return pool


_RWC_POOLS_CACHE: Dict[int, Dict[str, List[str]]] = {}
_RWC_SQUADS_CACHE: Dict[int, Dict[str, List[Player]]] = {}


def get_rwc_year_data(year: int) -> tuple:
    """Returns `(pools, squads)` for one World Cup edition:
    `pools` = `{pool_name: [team_name, ...]}` (the real historical draw,
    read straight off the squads page's own structure - nothing hand-entered);
    `squads` = `{team_name: [Player, ...]}`. Both disk-independent of the
    network after the first call within this process (module-level cache;
    the underlying `fetch_wikitext` call is itself disk-cached too)."""
    if year in _RWC_POOLS_CACHE:
        return _RWC_POOLS_CACHE[year], _RWC_SQUADS_CACHE[year]

    wikitext = fetch_rwc_squads_wikitext(year)
    if not wikitext:
        raise ValueError(f"No squads page found for the {year} Rugby World Cup.")
    parsed = parse_rwc_squads(wikitext)
    if not parsed:
        raise ValueError(f"Squads page for {year} didn't parse into any pools - format may differ.")

    pools: Dict[str, List[str]] = {}
    squads: Dict[str, List[Player]] = {}
    for pool_name, teams in parsed.items():
        pools[pool_name] = list(teams.keys())
        for team_name, entries in teams.items():
            squads[team_name] = build_historical_pool(year, team_name, entries)

    _RWC_POOLS_CACHE[year] = pools
    _RWC_SQUADS_CACHE[year] = squads
    return pools, squads
