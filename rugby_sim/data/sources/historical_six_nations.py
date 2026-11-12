"""Historical Six Nations Championship squads (2009-2021) from Wikipedia's
dedicated "`<year>` Six Nations Championship squads" pages.

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
from typing import Dict, List

from ...models.player import Player
from .attribute_mapping import DEFAULT_UNION_STRENGTH, UNION_STRENGTH, scale_to_union_strength
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
AVAILABLE_SIX_NATIONS_YEARS = list(range(2009, 2022))

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
            full_name, peer_proxies=peer_proxies_by_position.get(position)
        )
        if attrs is None:
            attrs = _archetype_attributes(position)
        attrs = scale_to_union_strength(attrs, strength)
        data_source = "historical_wikipedia" if source == "wikipedia" else "historical_archetype"
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
    Cup's varying participant list). No real match order survives on this
    page, so a tournament replay built from this data uses a synthetic
    round-robin order, not the actual historical fixture sequence."""
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
