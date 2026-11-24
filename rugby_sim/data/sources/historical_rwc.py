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
from .wiki_table_utils import (
    clean_wiki_cell as _clean_wiki_cell,
    split_wiki_row_cells as _split_wiki_row_cells,
    strip_wiki_cell_attrs as _strip_wiki_cell_attrs,
)
from .wikipedia_squad import (
    POS_CODE_MAP,
    _archetype_attributes,
    _cross_reference_attributes,
    _proxy_attributes,
    describe_attribute_source,
    fetch_wikitext,
    with_twin_position_duplicates,
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

        pos_m = re.search(r"pos=\s*(\w+)", line)
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


def rwc_statistics_page_title(year: int) -> str:
    return f"{year} Rugby World Cup statistics"


def fetch_rwc_statistics_wikitext(year: int):
    return fetch_wikitext(rwc_statistics_page_title(year))




def parse_rwc_tournament_stats(wikitext: str) -> Dict[str, dict]:
    """Parses the real `{|class="wikitable sortable"|}` "Top point scorers"/
    "Top try scorers" tables on a "`<year>` Rugby World Cup statistics"
    Wikipedia page - a genuinely different wikitext structure from the
    `{{nat rs player}}` template used elsewhere in this module (plain
    MediaWiki table syntax: `|-` row separators, cells spread across
    lines and/or packed with `||`/`!!`).

    Confirmed live for 1995 and 2003: both have "Player/Team/Position/
    Played/Tries/Conversions(or Conv/a `{{tooltip}}`-wrapped header)/
    Penalties/Drop goals/Total points" columns in that order, but the
    exact column set DOES drift between editions (2003 adds trailing
    Yellow/Red cards columns 1995 doesn't have, and the sorted column in
    each table gets a `! scope=row` wiki-markup quirk instead of a plain
    `|`) - so this reads each table's own header row to map column names
    to cell positions, rather than assuming a fixed layout or markup.

    Returns `{player_name_lower: {played, tries, conversions, penalties,
    drop_goals, points}}` (any field that didn't have a column in that
    table's header, or didn't parse as a number, is simply absent, not
    guessed)."""
    results: Dict[str, dict] = {}
    lines = wikitext.splitlines()
    in_relevant_section = False
    i = 0
    n = len(lines)
    field_map = {
        "played": ("Played",),
        "tries": ("Tries",),
        "conversions": ("Conversions", "Conv"),
        "penalties": ("Penalties",),
        "drop_goals": ("Drop goals",),
        "points": ("Total points",),
    }

    while i < n:
        stripped = lines[i].strip()
        low = stripped.lower()
        if "point scorers" in low or "try scorers" in low:
            in_relevant_section = True
        elif stripped.startswith("==") and "scorers" not in low:
            in_relevant_section = False

        if in_relevant_section and stripped.startswith("{|"):
            i += 1
            headers: List[str] = []
            headers_done = False
            row_lines: List[str] = []

            def _flush_row():
                if not row_lines or not headers_done:
                    return
                cells = _split_wiki_row_cells(row_lines)
                if not cells:
                    return
                row = dict(zip(headers, cells))
                name_raw = row.get("Player", cells[0])
                name = name_raw.strip()
                if not name:
                    return
                entry = results.setdefault(name.lower(), {})
                for field_name, keys in field_map.items():
                    for key in keys:
                        val = row.get(key)
                        if val is None:
                            continue
                        digits = re.sub(r"[^\d]", "", val)
                        if digits:
                            entry[field_name] = int(digits)
                        break

            while i < n and not lines[i].strip().startswith("|}"):
                row_line = lines[i]
                stripped_row = row_line.strip()
                if stripped_row.startswith("|+"):
                    pass  # table caption - not a header or data row
                elif stripped_row.startswith("|-"):
                    _flush_row()
                    row_lines = []
                    if headers:
                        headers_done = True
                elif stripped_row.startswith("!") and not headers_done:
                    header_text = stripped_row.lstrip("!").strip()
                    for cell in re.split(r"!!", header_text):
                        headers.append(_clean_wiki_cell(_strip_wiki_cell_attrs(cell)))
                else:
                    row_lines.append(row_line)
                i += 1
            _flush_row()
            in_relevant_section = False
        i += 1
    return results


_RWC_TOURNAMENT_STATS_CACHE: Dict[int, Dict[str, dict]] = {}


def get_rwc_tournament_stats(year: int) -> Dict[str, dict]:
    """Disk/process-cached `parse_rwc_tournament_stats` result for one RWC
    edition's "`<year>` Rugby World Cup statistics" page. Returns `{}` if
    the page doesn't exist or didn't parse (never raises - this is a bonus
    nudge, not a required input)."""
    if year in _RWC_TOURNAMENT_STATS_CACHE:
        return _RWC_TOURNAMENT_STATS_CACHE[year]
    wikitext = fetch_rwc_statistics_wikitext(year)
    stats = parse_rwc_tournament_stats(wikitext) if wikitext else {}
    _RWC_TOURNAMENT_STATS_CACHE[year] = stats
    return stats


def build_historical_pool(year: int, nation: str, entries: List[dict]) -> List[Player]:
    strength_code = _NATION_TO_STRENGTH_CODE.get(nation)
    strength = UNION_STRENGTH.get(strength_code, DEFAULT_UNION_STRENGTH) if strength_code else DEFAULT_UNION_STRENGTH

    from .pool_builder import _global_reference_peer_proxies
    peer_proxies_by_position = _global_reference_peer_proxies("2026")

    try:
        tournament_stats = get_rwc_tournament_stats(year)
    except Exception:
        tournament_stats = {}

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
            attrs, source = _proxy_attributes(
                position, entry.get("caps"), tournament_stats.get(full_name.lower())
            )
        if source not in ("legends_curated", "ea_rugby08_rating"):
            attrs = scale_to_union_strength(attrs, strength)
        # Keep the real-vs-archetype distinction visible (same honesty
        # convention as the current-squad Wikipedia pipeline), just
        # prefixed so it's obviously a *historical* pull either way - except
        # a curated Hall-of-Fame legend or a real EA-rated player, whose
        # provenance is tagged honestly as such rather than folded into
        # either historical bucket.
        if source in ("legends_curated", "ea_rugby08_rating"):
            data_source = source
        elif source == "wikipedia":
            data_source = "historical_wikipedia"
        elif source == "historical_proxy":
            data_source = "historical_proxy"
        else:
            data_source = "historical_archetype"
        pool.append(Player(
            name=full_name,
            nation=nation,
            natural_position=position,
            attributes=attrs,
            era=era,
            caps=entry.get("caps"),
            notes=(
                f"{year} Rugby World Cup squad. "
                + (describe_attribute_source(source, historical=True) or
                   "Attributes from real rugbydata career stats (cross-referenced by name) - "
                   "likely a career that extended into rugbydata's 2018+ coverage."
                   if source == "wikipedia" else
                   "No rugbydata history for this era/name, but real caps and/or this "
                   "tournament's real scoring-table stats gave a small, bounded nudge "
                   "off the generic position archetype."
                   if source == "historical_proxy" else
                   "No rugbydata history found for this era/name, so attributes are a "
                   "generic position-archetype estimate, not a scouted rating.")
            ),
            data_source=data_source,
        ))
    return with_twin_position_duplicates(pool)


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
