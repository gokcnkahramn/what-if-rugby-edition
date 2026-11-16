"""Season mode's 12d follow-up: a small, honestly-scoped "uncapped / eligible
but never capped internationally" player pool, sourced from domestic CLUB
squad pages on Wikipedia - NOT from rugbydata, which has no nationality/
eligibility field on club-match rows at all (confirmed: only a `team` column,
the club name, for club competitions - see `rugby_data_client.py`).

How this works, end to end (confirmed live before writing any regex, same
house rule `wikipedia_squad.py` follows):
1. A domestic club's Wikipedia page has a `==Current squad==` section with a
   `===Senior squad===` subsection built from `{{Rugby union squad start}}`
   / `{{Rugby union squad end}}` wrapping one `{{RU squad player|NAT|Name|
   ...}}` line per player, grouped under bold position headings ('''Props''',
   '''Hookers''', '''Locks''', '''Back row''', '''Scrum-halves''',
   '''Fly-halves''', '''Centres''', '''Wings''', '''Fullbacks'''). Checked
   live for Leicester Tigers, Saracens (Premiership/England) and Stade
   Toulousain, Racing 92 (Top 14/France) - identical template, same markup
   each time.
2. `NAT` is the player's nationality flag code (ISO-3166-ish rugby code,
   e.g. ENG/FRA/WAL/ARG) - this is the SAME mechanism Wikipedia editors use
   to mark national-team eligibility on every page this project already
   relies on (national squad pages use the identical flag convention), so
   treating it as "registered/eligible for that union" is consistent with
   how the rest of this project already reads Wikipedia flags.
3. `cap=y` (confirmed via `{{Template:RU squad player}}`'s own wikitext:
   `{{#switch:{{{cap|}}}|yes|y=<b>...` ) bolds the player's name specifically
   to mark a current full international - the same "bold = capped" display
   convention rugby union sources use everywhere. A player listed under a
   club's own nationality flag WITHOUT `cap=y` on that club's own page is,
   per that club's own editors, not (yet) a capped international for that
   flag's union - this is the signal this module filters on. It is an
   honest proxy for "eligible, never capped", not a verified legal
   eligibility check (residency/ancestry rules aren't visible from a squad
   list) - documented as such in every player's `notes`.

Expanded (12e follow-up) to go LEAGUE-by-league instead of hand-picking
individual clubs, because a hardcoded club list goes stale the moment a
club is relegated (last season's page no longer reflects who is actually
in the league). For each major domestic league this project's unions
care about, `LEAGUE_PAGES` points at the real, current-season Wikipedia
page (confirmed live, 2026-11-16 - see each entry's comment for how the
title was found), `fetch_league_club_names` parses that page's "Teams"
wikitable into the real list of current member clubs for that season
(so a relegated club simply won't be on the list to fetch), and
`build_uncapped_pool` fetches every one of those clubs' own squad pages
with the SAME `_parse_senior_squad` parser used for the original
hand-picked clubs, then groups every `{nat, name, pos, capped}` row
across the whole league by nationality flag - so e.g. the URC (Ireland/
Scotland/Wales/Italy/South Africa clubs) contributes to five unions'
pools from one league pull, not one union at a time.

Leagues covered (confirmed live): Premiership Rugby (England-only
clubs), Top 14 (France-only clubs), United Rugby Championship (Benetton/
Zebre = Italy, Bulls/Lions/Sharks/Stormers = South Africa, Cardiff/
Dragons/Ospreys/Scarlets = Wales, Connacht/Leinster/Munster/Ulster =
Ireland, Edinburgh/Glasgow = Scotland). `CLUB_PAGES` below is kept as a
small manual fallback/supplement (and the original two-union starting
point), merged with whatever `LEAGUE_PAGES` resolves for each union.

Super Rugby Pacific (New Zealand/Australia/Fiji) follow-up (confirmed
live 2026-11-16): the evergreen competition page (e.g. "Super Rugby
Pacific") indeed has no plain-wikitext team list - its roster is only
reachable via a transcluded standings template, matching the earlier
finding. However a SEPARATE, season-specific article
("2026 Super Rugby Pacific season") DOES carry its own plain wikitext,
including a "==Teams and personnel==" / "===Overview===" wikitable -
but that table names each club using the `{{Rut|<short name>}}`
rugby-team-link template (e.g. `{{Rut|Brumbies}}`, `{{Rut|Drua}}`)
rather than a plain `[[Wikipedia page title]]` wikilink like the other
three leagues' tables use, so `_parse_league_team_titles`'s wikilink
regex does not find anything there. `{{Rut|...}}` resolves to a real
page title via `Template:Rugby union team/link`'s `{{#switch:...}}`
(fetched and read live), which is a small, stable, closed set (11
current Super Rugby Pacific clubs) - so rather than writing a second,
more fragile template-expanding parser for a one-off table shape, this
module follows the same documented-fallback convention
`pool_builder.py` uses for Spain/Namibia: `SUPER_RUGBY_TEAM_TITLES`
below is a short, explicitly-sourced name->title map (every entry
confirmed live against that switch template and by fetching the
resulting page), combined with a small parser
(`_parse_super_rugby_team_names`) that only has to pull the `{{Rut|X}}`
short names out of the season page's Teams table, not resolve titles
itself. 10 of the 11 clubs' own pages have the standard
`{{Rugby union squad start}}` current-squad block and parse cleanly;
Moana Pasifika's page (confirmed live) has no such block at all (its
"Players" section only lists a historical "2020 squad", not a
maintained current senior squad template), so it is honestly skipped -
`_parse_senior_squad` returns [] for it like any page missing that
block, rather than being special-cased out of the title list (if a
future edit adds the standard block to that page, it will start
contributing automatically).
"""

from __future__ import annotations

import re
from typing import Dict, List

from ...models.attributes import Attributes
from ...models.player import Player
from ...models.position import Position
from .attribute_mapping import DEFAULT_UNION_STRENGTH, UNION_STRENGTH, scale_to_union_strength
from .wikipedia_squad import _ARCHETYPES, _cross_reference_attributes, fetch_wikitext

# Bold position-heading text (as it appears in the wikitext, case-sensitive)
# -> our Position enum. Same one-representative-slot-per-ambiguous-real-world
# -position limitation as `wikipedia_squad.POS_CODE_MAP` (no loosehead/
# tighthead, lock 4/5, left/right wing, inside/outside centre distinction in
# this markup either), draft into either freely.
CLUB_POS_HEADING_MAP = {
    "Props": Position.LOOSEHEAD_PROP,
    "Hookers": Position.HOOKER,
    "Locks": Position.LOCK_1,
    "Back row": Position.BLINDSIDE_FLANKER,
    "Scrum-halves": Position.SCRUM_HALF,
    "Fly-halves": Position.FLY_HALF,
    "Centres": Position.INSIDE_CENTRE,
    "Wings": Position.LEFT_WING,
    "Fullbacks": Position.FULLBACK,
}

# Union short code -> domestic club Wikipedia page titles to pull from.
# Confirmed live (2026-27 season squad listings, `{{RU squad player}}`
# template) for every club below. Deliberately small: two Tier 1 unions,
# two top-flight clubs each - a proof of the pattern, not full coverage.
# Every other union (including every Tier 2 union already in
# `pool_builder.TIER2_TEAM_IDS`) has NO uncapped pool yet - `build_uncapped_pool`
# returns [] for them rather than guessing at an unverified page/format.
CLUB_PAGES = {
    "ENG": ["Leicester Tigers", "Saracens F.C."],
    "FRA": ["Stade Toulousain", "Racing 92"],
}

# League short code -> current-season Wikipedia page title, each confirmed
# live (2026-11-16) by fetching the real wikitext rather than guessing a
# season label. Found via Wikipedia's search API
# (`action=query&list=search`) for e.g. "2025-26 Premiership Rugby season"
# and taking the actual page title that search returns (Wikipedia's season
# articles aren't always titled exactly "<season> <league> season" - e.g.
# the Premiership and URC pages below drop the trailing "season"). Super
# Rugby Pacific (Jan-Jun season, so "2025" not "2025-26" is the current
# completed/upcoming season as of this date) is NOT included - see module
# docstring for why.
LEAGUE_PAGES: Dict[str, str] = {
    "premiership": "2025–26 Premiership Rugby",
    "top14": "2025–26 Top 14 season",
    "urc": "2025–26 United Rugby Championship",
}

# Which section heading(s) each league page's club-list wikitable sits
# under - confirmed live per page (not identical across pages: Premiership/
# Top 14 use "== Teams ==" with a space, URC uses "==Teams==" without).
_LEAGUE_TEAMS_SECTION_NAMES: Dict[str, List[str]] = {
    "premiership": ["== Teams =="],
    "top14": ["== Teams =="],
    "urc": ["==Teams==", "== Teams =="],
}


def _parse_league_team_titles(wikitext: str, section_names: List[str]) -> List[str]:
    """Parses a league season page's "Teams" wikitable into the real
    Wikipedia page title of each current member club, by taking the first
    `[[Title|Display]]` (or `[[Title]]`) wikilink in each table row's first
    cell - confirmed live against Premiership Rugby, Top 14 and URC season
    pages, which all put the club link first (sometimes wrapped in
    `{{sort|...|[[Title|Display]]}}`, which this still finds since it looks
    for the first `[[` anywhere in that first cell, not at its start)."""
    idx = -1
    for name in section_names:
        idx = wikitext.find(name)
        if idx != -1:
            break
    if idx == -1:
        return []
    table_start = wikitext.find("{|", idx)
    if table_start == -1:
        return []
    table_end = wikitext.find("\n|}", table_start)
    if table_end == -1:
        table_end = len(wikitext)
    section = wikitext[table_start:table_end]

    titles: List[str] = []
    seen: set = set()
    for row in section.split("\n|-")[1:]:
        for line in row.splitlines():
            line = line.strip()
            if not line.startswith("|") or line.startswith("|-") or line.startswith("|+") or line.startswith("!"):
                continue
            cell = line[1:].strip()
            m = re.search(r"\[\[([^|\]]+)", cell)
            if m:
                title = m.group(1).strip()
                if title and title not in seen:
                    seen.add(title)
                    titles.append(title)
            break  # only the first content cell (the club column) per row
    return titles


# Current-season Super Rugby Pacific article (confirmed live 2026-11-16 -
# see module docstring). Kept separate from `LEAGUE_PAGES` since its table
# shape needs a different parser (`{{Rut|...}}` short names, not plain
# `[[wikilinks]]`).
SUPER_RUGBY_SEASON_PAGE = "2026 Super Rugby Pacific season"
_SUPER_RUGBY_TEAMS_SECTION_NAMES = ["==Teams and personnel=="]

# `{{Rut|<short name>}}` -> real Wikipedia page title, read live off
# `Template:Rugby union team/link`'s `{{#switch:{{{name}}}|...}}` on
# 2026-11-16 for exactly the 11 short names the season page's Teams table
# uses. A small, closed, hand-verified map (same convention as
# `pool_builder.py`'s manual Spain/Namibia fallback) rather than a second
# template-expanding parser, since this set rarely changes (a relegation/
# promotion in Super Rugby Pacific is a rare, newsworthy event, unlike
# Premiership/Top14/URC's annual-ish Teams tables).
SUPER_RUGBY_TEAM_TITLES: Dict[str, str] = {
    "Brumbies": "ACT Brumbies",
    "Force": "Western Force",
    "Reds": "Queensland Reds",
    "Waratahs": "New South Wales Waratahs",
    "Drua": "Fijian Drua",
    "Blues": "Blues (Super Rugby)",
    "Chiefs": "Chiefs (Super Rugby)",
    "Crusaders": "Crusaders (rugby union)",
    "Highlanders": "Highlanders (rugby union)",
    "Hurricanes": "Hurricanes (rugby union)",
    "Moana Pasifika": "Moana Pasifika",
}


def _parse_super_rugby_team_names(wikitext: str) -> List[str]:
    """Extracts the unique `{{Rut|<short name>}}` team names from the Super
    Rugby Pacific season page's "Teams and personnel" section (confirmed
    live - see module docstring), order-preserving, deduped."""
    idx = -1
    for name in _SUPER_RUGBY_TEAMS_SECTION_NAMES:
        idx = wikitext.find(name)
        if idx != -1:
            break
    if idx == -1:
        return []
    m = re.search(r"\n==[^=\n][^\n]*==\s*\n", wikitext[idx + 5:])
    section_end = idx + 5 + m.start() if m else len(wikitext)
    section = wikitext[idx:section_end]

    names: List[str] = []
    seen: set = set()
    for name in re.findall(r"\{\{Rut\|([^|}]+)", section):
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def fetch_super_rugby_club_titles() -> List[str]:
    """Real club Wikipedia page titles for the current Super Rugby Pacific
    season, via `SUPER_RUGBY_SEASON_PAGE` + `SUPER_RUGBY_TEAM_TITLES`. Empty
    list (not a crash) if the live/disk-cached fetch or parse fails, or if a
    parsed short name isn't in `SUPER_RUGBY_TEAM_TITLES` (an unmapped new
    team shows up on the season page before this module is updated for it -
    skip it, don't guess its title)."""
    try:
        wikitext = fetch_wikitext(SUPER_RUGBY_SEASON_PAGE)
    except Exception:
        return []
    if not wikitext:
        return []
    titles: List[str] = []
    for short_name in _parse_super_rugby_team_names(wikitext):
        title = SUPER_RUGBY_TEAM_TITLES.get(short_name)
        if title:
            titles.append(title)
    return titles


def fetch_league_club_names(league_key: str) -> List[str]:
    """Real, current-season club Wikipedia page titles for one of
    `LEAGUE_PAGES`'s leagues - e.g. `fetch_league_club_names("urc")` ->
    `["Benetton Rugby", "Bulls (rugby union)", ...]`. Empty list (not a
    crash) for an unknown league key or if the live/disk-cached fetch or
    parse fails, so a problem with one league never breaks the others."""
    page_title = LEAGUE_PAGES.get(league_key)
    if not page_title:
        return []
    try:
        wikitext = fetch_wikitext(page_title)
    except Exception:
        return []
    if not wikitext:
        return []
    section_names = _LEAGUE_TEAMS_SECTION_NAMES.get(league_key, ["==Teams==", "== Teams =="])
    return _parse_league_team_titles(wikitext, section_names)


def _all_covered_club_titles() -> List[str]:
    """Union of every club page title this module can pull a squad from:
    the original hand-picked `CLUB_PAGES` plus every club resolved live
    from `LEAGUE_PAGES`. Deduped, order-preserving. A league fetch/parse
    failure for one league just contributes nothing, rather than failing
    the whole set (scope guardrail: fail gracefully to whatever's
    confirmed, never crash)."""
    titles: List[str] = []
    seen: set = set()
    for club_list in CLUB_PAGES.values():
        for title in club_list:
            if title not in seen:
                seen.add(title)
                titles.append(title)
    for league_key in LEAGUE_PAGES:
        for title in fetch_league_club_names(league_key):
            if title not in seen:
                seen.add(title)
                titles.append(title)
    for title in fetch_super_rugby_club_titles():
        if title not in seen:
            seen.add(title)
            titles.append(title)
    return titles


def _parse_senior_squad(wikitext: str) -> List[dict]:
    """Extracts {nat, name, pos, capped} entries from a club page's FIRST
    `{{Rugby union squad start}}...{{Rugby union squad end}}` block following
    the "Current squad" heading - that first block is always the senior
    squad on every page checked; later blocks (academy/women's/etc.) are
    deliberately not parsed."""
    start = wikitext.find("Current squad")
    if start == -1:
        return []
    block_start = wikitext.find("{{Rugby union squad start", start)
    if block_start == -1:
        return []
    block_end = wikitext.find("{{Rugby union squad end", block_start)
    if block_end == -1:
        return []
    section = wikitext[block_start:block_end]

    entries = []
    current_pos: str = None
    for line in section.splitlines():
        heading_m = re.match(r"'''([^']+)'''", line.strip())
        if heading_m:
            current_pos = heading_m.group(1).strip()
            continue
        if "{{RU squad player" not in line:
            continue
        # First two positional/{{{1}}}/{{{2}}}-equivalent params: nat, name.
        m = re.search(r"\{\{RU squad player\|([A-Za-z]{2,3})\|([^|}]+)", line)
        if not m:
            continue
        nat, raw_name = m.group(1), m.group(2)
        # Names are sometimes wikilinked, e.g. "[[:fr:Name|Name]]" - keep
        # only the display text (after the last '|' if present).
        name = raw_name.strip()
        if name.startswith("[["):
            name = name.rstrip("]")
            name = name.split("|")[-1] if "|" in name else name.lstrip("[")
        name = name.strip()
        if not name or current_pos is None:
            continue
        capped = bool(re.search(r"\|cap=y(es)?\b", line))
        entries.append({"nat": nat, "name": name, "pos": current_pos, "capped": capped})
    return entries


# Unions this module will ever return players for, even if a club squad
# page happens to list some other nationality's flag - scope guardrail:
# only nations this project already has full Player/pool support for (its
# `UNION_STRENGTH` table), never invent support for a new union just
# because a league-wide pull happened to surface its flag code (e.g. Top
# 14/URC/Premiership squads also carry ARG/NZL/AUS/GEO/TGA/SAM-flagged
# players - those are real rows this module parses, just not exposed here
# unless/until that union gets its own full Player pool treatment).
_SUPPORTED_NATION_CODES = set(UNION_STRENGTH.keys())


def build_uncapped_pool(nation_code: str, nation_display_name: str) -> List[Player]:
    """Real club-squad players who carry `nation_code`'s nationality flag on
    a covered club's current Wikipedia squad listing but aren't marked
    `cap=y` (capped international) there. Clubs are pulled from the union
    of `CLUB_PAGES` (hand-picked) and every current club in `LEAGUE_PAGES`'s
    leagues (Premiership, Top 14, URC) - so e.g. "WAL" or "ITA" now draw
    from their URC clubs even though neither has its own `CLUB_PAGES`
    entry. Empty list for a union this module doesn't support at all (not
    in `UNION_STRENGTH`) - honest scope limit, not a silent guess."""
    if nation_code not in _SUPPORTED_NATION_CODES:
        return []
    titles = _all_covered_club_titles()
    if not titles:
        return []

    strength = UNION_STRENGTH.get(nation_code, DEFAULT_UNION_STRENGTH)
    pool: List[Player] = []
    seen_names: set = set()

    for title in titles:
        wikitext = fetch_wikitext(title)
        if not wikitext:
            continue
        for entry in _parse_senior_squad(wikitext):
            if entry["capped"] or entry["nat"] != nation_code:
                continue
            key = entry["name"].strip().lower()
            if key in seen_names:
                continue
            position = CLUB_POS_HEADING_MAP.get(entry["pos"])
            if position is None:
                continue
            seen_names.add(key)

            attrs, source = _cross_reference_attributes(entry["name"])
            if attrs is None:
                attrs = Attributes(**_ARCHETYPES.get(position, {})).clamp()
                source = "uncapped_wikipedia_archetype"
            else:
                source = "uncapped_wikipedia"
            attrs = scale_to_union_strength(attrs, strength)

            note = (
                f"Listed on {title}'s current Wikipedia squad under the "
                f"{nation_display_name} flag with no 'cap=y' (capped "
                "international) marker - i.e. club-registered/eligible but "
                "never (yet) capped for the national side, per that club's "
                "own squad listing. Not a verified legal-eligibility check "
                "(residency/ancestry rules aren't visible from a squad "
                "list). " + (
                    "Attributes from that person's real rugbydata career stats "
                    "(cross-referenced by name)."
                    if source == "uncapped_wikipedia" else
                    "No rugbydata history found for this name, so attributes "
                    "are a generic position-archetype estimate, not a scouted "
                    "rating."
                )
            )
            pool.append(Player(
                name=entry["name"],
                nation=nation_display_name,
                natural_position=position,
                attributes=attrs,
                era="'26",
                notes=note,
                data_source=source,
            ))

    return pool
