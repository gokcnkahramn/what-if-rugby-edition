"""Real squads for international invitational/composite sides that are NOT
World Rugby unions (so never appear in rugbydata, no per-union caps concept)
but genuinely do play full test matches against national teams - the
British & Irish Lions and the discontinued Pacific Islanders. Same honesty
convention as `wikipedia_squad.py`'s Barbarians-adjacent pools: a real
name's attributes come from rugbydata's global player registry when that
name resolves there, a documented generic position archetype otherwise -
never invented. The two real Wikipedia pages involved use genuinely
different wikitext table shapes from `parse_current_squad`'s
`{{nat rs player}}` assumption, so each gets its own small parser here
rather than forcing them through that one.
"""

from __future__ import annotations

import re
from typing import List, Optional

from ...models.player import Player
from ...models.position import Position
from .wiki_table_utils import (
    clean_wiki_cell as _clean_wiki_cell,
    split_wiki_row_cells as _split_wiki_row_cells,
    strip_wiki_cell_attrs as _strip_wiki_cell_attrs,
)
from .wikipedia_squad import (
    POS_CODE_MAP,
    _cross_reference_attributes,
    _proxy_attributes,
    fetch_wikitext,
)

# -- British & Irish Lions -----------------------------------------------
# The real, current tour squad's Wikipedia page title. Unlike a permanent
# union, the Lions don't have a single "current squad" page - each real
# tour gets its own article, re-announced every ~4 years - so this is
# pinned to the latest real tour rather than derived from a pattern.
LIONS_TOUR_PAGE_TITLE = "2025 British & Irish Lions tour to Australia"

_LIONS_POSITION_WORDS = {
    "hooker": Position.HOOKER,
    "prop": Position.LOOSEHEAD_PROP,
    "second row": Position.LOCK_1,
    "second-row": Position.LOCK_1,
    "lock": Position.LOCK_1,
    # "Back row" (used by this table for both flanker and number 8 alike)
    # is genuinely ambiguous in this real wikitext - same single-slot
    # limitation `wikipedia_squad.POS_CODE_MAP`'s own "FL"/"BR" mapping
    # already documents, draft into either freely.
    "back row": Position.BLINDSIDE_FLANKER,
    "flanker": Position.BLINDSIDE_FLANKER,
    "number 8": Position.NUMBER_8,
    "number eight": Position.NUMBER_8,
    "scrum-half": Position.SCRUM_HALF,
    "scrum half": Position.SCRUM_HALF,
    "fly-half": Position.FLY_HALF,
    "fly half": Position.FLY_HALF,
    "centre": Position.INSIDE_CENTRE,
    "wing": Position.LEFT_WING,
    "full-back": Position.FULLBACK,
    "full back": Position.FULLBACK,
    "fullback": Position.FULLBACK,
}


def _lions_position_from_text(text: str) -> Optional[Position]:
    low = text.lower().strip()
    for key, pos in _LIONS_POSITION_WORDS.items():
        if key in low:
            return pos
    return None


def parse_lions_tour_squad(wikitext: str) -> List[dict]:
    """Parses the real `===British & Irish Lions===` wikitable under
    `==Squads==` on a `<year> British & Irish Lions tour to <country>` page
    - a plain `{|class="wikitable sortable"|}` table with real
    Player/Position/Date of birth/National team/Club/National caps (Lions
    caps)/Notes columns (confirmed live for the 2025 tour) - genuinely
    different markup from both `{{nat rs player}}` and the RWC statistics
    tables elsewhere in this project, so this reads the header row to map
    columns rather than assuming a fixed layout.

    Returns `[{name, position, nation, caps}]` - `nation` is the real
    `{{ru|<code>}}` union code (e.g. "ENG"/"IRE"/"SCO"/"WAL"), `caps` is
    that player's real national caps at selection (not Lions caps), `None`
    if it didn't parse."""
    start = wikitext.find("British & Irish Lions===")
    if start == -1:
        return []
    table_start = wikitext.find("{|", start)
    if table_start == -1:
        return []
    table_end = wikitext.find("|}", table_start)
    if table_end == -1:
        return []
    section = wikitext[table_start:table_end]

    entries: List[dict] = []
    headers: List[str] = []
    headers_done = False
    row_lines: List[str] = []

    def _flush_row() -> None:
        if not row_lines or not headers_done:
            return
        # The Player column is always a `{{sortname|First|Last[|dab=...]}}`
        # template - `_clean_wiki_cell`'s generic template-cleaning (built
        # for single-meaningful-param templates like `{{Ru|FRA}}`) keeps
        # only the LAST pipe-separated segment, which mangles a two-part
        # name (or picks up a stray `dab=...`/birth-year disambiguator
        # instead of the surname). So the name is extracted directly from
        # the raw first cell here, before any generic cleaning touches it;
        # every other real column in this table (nation code, club, caps)
        # genuinely does only have one meaningful trailing segment, so
        # those still go through the normal cell splitter/cleaner below.
        joined = "\n".join(row_lines).strip().lstrip("|")
        if "||" not in joined:
            return
        first_cell, rest = joined.split("||", 1)
        name_m = re.search(r"\{\{sortname\|([^|}]+)\|([^|}]+)", first_cell)
        if not name_m:
            return
        name = f"{name_m.group(1).strip()} {name_m.group(2).strip()}"
        other_cells = _split_wiki_row_cells([rest])
        if not other_cells:
            return
        row = dict(zip(headers[1:], other_cells))
        position = _lions_position_from_text(row.get("Position", ""))
        if position is None:
            return
        nation = (row.get("National team") or "").strip()
        caps_header = next((h for h in headers[1:] if "caps" in h.lower()), None)
        caps_raw = row.get(caps_header) if caps_header else None
        caps = None
        if caps_raw:
            caps_m = re.match(r"\s*(\d+)", caps_raw)
            if caps_m:
                caps = int(caps_m.group(1))
        entries.append({"name": name, "position": position, "nation": nation, "caps": caps})

    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("|+"):
            continue
        if stripped.startswith("|-"):
            _flush_row()
            row_lines = []
            if headers:
                headers_done = True
            continue
        if stripped.startswith("!") and not headers_done:
            header_text = re.sub(r"<br\s*/?>", " ", stripped.lstrip("!").strip())
            for cell in re.split(r"!!", header_text):
                headers.append(_clean_wiki_cell(_strip_wiki_cell_attrs(cell)))
            continue
        row_lines.append(line)
    _flush_row()
    return entries


def build_lions_pool() -> List[Player]:
    """Real 2025 British & Irish Lions tour squad (Australia), scraped from
    its own Wikipedia tour-squad table - no manual entry needed, unlike the
    Barbarians' hand-typed list, since this page's table is clean and
    regular. Every one of these names is a current Tier 1 international, so
    almost all resolve to a real rugbydata career-stats cross-reference; no
    union-strength scaling is applied (unlike a normal union pool) since the
    Lions aren't one real union with one real strength level - they're a
    hand-picked composite of the 4 home unions' own best players, each
    already correctly rated by their individual cross-referenced stats."""
    wikitext = fetch_wikitext(LIONS_TOUR_PAGE_TITLE)
    if not wikitext:
        return []
    entries = parse_lions_tour_squad(wikitext)

    from .pool_builder import NATION_DISPLAY

    pool: List[Player] = []
    for entry in entries:
        position = entry["position"]
        full_name = entry["name"]
        attrs, source = _cross_reference_attributes(full_name)
        if attrs is None:
            attrs, source = _proxy_attributes(position, entry.get("caps"))
        note = (
            "2025 British & Irish Lions tour squad (Australia) - real Wikipedia "
            "tour-squad listing, cross-referenced against rugbydata where possible."
        )
        pool.append(Player(
            full_name, NATION_DISPLAY.get(entry["nation"], entry["nation"] or "Unknown"),
            position, attrs, era="'25", notes=note, data_source=source,
            caps=entry.get("caps"),
        ))
    return pool


# -- Pacific Islanders (2004-2008, discontinued) --------------------------
# Not in rugbydata (confirmed by scanning the dataset), and no longer an
# active side (the Pacific Islands Rugby Alliance folded in 2009) - the
# only real squad to scrape is its last real tour, 2008.
PACIFIC_ISLANDERS_PAGE_TITLE = "Pacific Islanders rugby union team"


def parse_pacific_islanders_squad(wikitext: str) -> List[dict]:
    """Parses the real `{{rugby squad player|pos=...|name={{flagicon|NAT}}
    [[Name]]|...}}` lines under `==Squad==` on the Pacific Islanders'
    Wikipedia page (the 2008 tour squad - its last real one) - a third,
    genuinely different real template from both `{{nat rs player}}` and the
    Lions' plain wikitable, so reuses `wikipedia_squad.POS_CODE_MAP`'s
    jersey-code mapping but its own name/nation extraction. Returns
    `[{name, position, nation_code}]`."""
    start = wikitext.find("==Squad==")
    if start == -1:
        return []
    heading_match = re.search(r"\n==[^=]", wikitext[start + 9:])
    end = start + 9 + heading_match.start() if heading_match else len(wikitext)
    section = wikitext[start:end]

    entries: List[dict] = []
    for line in section.splitlines():
        if "rugby squad player" not in line:
            continue
        pos_m = re.search(r"\|\s*pos\s*=\s*(\w+)", line)
        if not pos_m:
            continue
        position = POS_CODE_MAP.get(pos_m.group(1))
        if position is None:
            continue
        name_field_m = re.search(r"name\s*=\s*(.*?)\s*\|(?:other|club)", line)
        name_field = name_field_m.group(1) if name_field_m else line
        nat_m = re.search(r"flagicon\|([A-Za-z]+)", name_field)
        name_m = re.search(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", name_field)
        if not name_m:
            continue
        entries.append({
            "name": name_m.group(1).strip(),
            "position": position,
            "nation_code": nat_m.group(1) if nat_m else None,
        })
    return entries


def build_pacific_islanders_pool() -> List[Player]:
    """Real 2008 Pacific Islanders tour-to-Europe squad (its last real
    season before the alliance folded) - a genuine historical composite
    side (Fiji/Samoa/Tonga), never a World Rugby union. No real caps field
    on this template, so every entry falls back to the flat position
    archetype unless its name cross-references a real rugbydata career."""
    wikitext = fetch_wikitext(PACIFIC_ISLANDERS_PAGE_TITLE)
    if not wikitext:
        return []
    entries = parse_pacific_islanders_squad(wikitext)

    from .pool_builder import NATION_DISPLAY

    pool: List[Player] = []
    for entry in entries:
        position = entry["position"]
        full_name = entry["name"]
        attrs, source = _cross_reference_attributes(full_name)
        if attrs is None:
            attrs, source = _proxy_attributes(position, None)
        note = (
            "2008 Pacific Islanders tour squad (last real season before the "
            "alliance folded in 2009) - real Wikipedia tour-squad listing."
        )
        nation_code = entry.get("nation_code")
        pool.append(Player(
            full_name, NATION_DISPLAY.get(nation_code, nation_code or "Unknown"),
            position, attrs, era="'08", notes=note, data_source=source,
        ))
    return pool
