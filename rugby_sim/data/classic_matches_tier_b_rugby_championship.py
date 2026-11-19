""""Classic Matches" catalog - Tier B, Tri Nations (1996-2011) / Rugby
Championship (2012-2017): one real, notable match from every edition of
that competition, 1996-2017 inclusive (22 candidate years).

Kept in a SEPARATE module from `classic_matches.py` on purpose (a parallel
agent is adding the other Tier-B tournament's matches to its own separate
file) - `TIER_B_RUGBY_CHAMPIONSHIP_MATCHES` below is meant to be merged into
the main `CLASSIC_MATCHES` list, and this module's `resolve_pools` wired
into the main `resolve_pools`, by a later pass. Nothing here edits
`classic_matches.py` itself.

Why the lineups needed fresh sourcing (unlike `classic_matches.py`'s
2018+ Rugby Championship entries, which just call `pool_builder` against
live rugbydata): rugbydata only covers 2018+, and there's no "historical
squad as of year X" pipeline for Tri Nations/Rugby Championship outside
Rugby World Cup years (`historical_rwc.py` handles those separately, via a
dedicated "`<year>` Rugby World Cup squads" Wikipedia page - not relevant
here). Instead, each `<year> Tri Nations Series` / `<year> Rugby
Championship` Wikipedia page (confirmed live, 1997-2017) carries a
`{{rugbybox}}` infobox per match plus, directly beneath it, two wikitables
(starting XV + replacements, one per team) in a consistent
`|POS||'''JERSEY'''||[[Player Name]]` layout - a genuinely different page
structure from `wikipedia_squad.py`'s `{{nat rs player}}` "Current squad"
template, so it needed its own small parser (`_find_rugbyboxes`/
`_parse_lineup_tables` below). Every name is a REAL player scraped from
that match's own real Wikipedia lineup table - nothing here is invented.
Each name is then cross-referenced into rugbydata's global player registry
via `wikipedia_squad._cross_reference_attributes` (same mechanism
`historical_rwc.py` uses for pre-2018 Rugby World Cup squads) for real
career stats where a career extends into rugbydata's 2018+ coverage, with
`wikipedia_squad._archetype_attributes`'s fixed position-baseline rating as
the honest fallback otherwise (`data_source="historical_wikipedia"` or
`"historical_archetype"` - same two-tier provenance tag `historical_rwc.py`
already uses, not a new scheme).

`real_score`/`blurb`/date/story details below are real, sourced facts
(researched via a prior web-search pass, then the real lineups verified
live against each match's own Wikipedia page in this one). `objectives`
thresholds are OUR OWN game-design choice layered on top (deliberately at
or beyond what actually happened), same convention as `classic_matches.py`.

Coverage: 21 of the 22 candidate years (1997-2017). **1996 is skipped** -
the researched fact ("New Zealand 33-26 South Africa, Loftus Versfeld,
24 Aug 1996") does not match any of the "1996 Tri Nations Series" Wikipedia
page's own 6 round-robin results (43-6, 21-16, 15-11, 25-32, 25-19, 18-29 -
confirmed live), nor does any round fall on 24 August 1996 (the 6 rounds
run 6 Jul-10 Aug 1996). That 33-26 scoreline most likely belongs to a
separate bilateral NZ-South Africa tour series, not the Tri Nations itself
- rather than guess at a lineup for an unverifiable match, 1996 is left out
entirely, per this project's "skip rather than invent" rule.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ..models.attributes import Attributes
from ..models.player import Player
from ..models.position import Position
from .classic_match_objectives import (
    ClassicMatch,
    no_cards,
    team_tries_at_least,
    total_points_at_least,
    win,
    win_margin_at_least,
)
from .sources.attribute_mapping import DEFAULT_UNION_STRENGTH, UNION_STRENGTH, scale_to_union_strength
from .sources.historical_rwc import _NATION_TO_STRENGTH_CODE
from .sources.wikipedia_squad import _archetype_attributes, _cross_reference_attributes, fetch_wikitext

# ---------------------------------------------------------------------------
# Wikipedia match-lineup scraping - a `{{rugbybox}}` + two-wikitable parser,
# independent of `wikipedia_squad.parse_current_squad`'s `{{nat rs player}}`
# template (a different page structure entirely).
# ---------------------------------------------------------------------------


def _find_template_end(text: str, start: int) -> int:
    """`start` points at a template's opening `{{`. Returns the index just
    after its matching `}}`, accounting for nested templates/citations."""
    depth, i, n = 0, start, len(text)
    while i < n - 1:
        two = text[i:i + 2]
        if two == "{{":
            depth += 1
            i += 2
            continue
        if two == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return i
            continue
        i += 1
    return n


def _find_table_end(text: str, start: int) -> int:
    """`start` points at a wikitable's opening `{|`. Returns the index just
    after its matching `|}`, accounting for nested tables."""
    depth, i, n = 0, start, len(text)
    while i < n - 1:
        two = text[i:i + 2]
        if two == "{|":
            depth += 1
            i += 2
            continue
        if two == "|}":
            depth -= 1
            i += 2
            if depth == 0:
                return i
            continue
        i += 1
    return n


def _find_rugbyboxes(wikitext: str) -> List[Tuple[str, str]]:
    """Returns `[(box_text, trailing_text), ...]` for every `{{rugbybox}}`
    template on the page - `trailing_text` is the wikitext right after one
    box up to the next (or 7000 chars), where its two lineup tables live."""
    out = []
    for m in re.finditer(r"\{\{[Rr]ugbybox", wikitext):
        start = m.start()
        box_end = _find_template_end(wikitext, start)
        box_text = wikitext[start:box_end]
        next_m = re.search(r"\{\{[Rr]ugbybox", wikitext[box_end:box_end + 8000])
        trailing_cap = box_end + (next_m.start() if next_m else 7000)
        out.append((box_text, wikitext[box_end:trailing_cap]))
    return out


_LINE_RE = re.compile(
    r"\|\s*([A-Za-z0-9]{1,3})\s*\|\|\s*'''(\d+)'''\s*\|\|\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]"
)


def _parse_lineup_tables(trailing_text: str) -> Tuple[List[dict], List[dict]]:
    """Finds the (up to two) lineup wikitables after a rugbybox - identified
    by their distinctive `{| ... cellspacing` opening tag, regardless of
    what wrapper table or `{{Football kit}}` template precedes them (this
    varies year to year) - and extracts `{pos, jersey, name}` entries per
    side, starting XV first then replacements."""
    nested, i = [], 0
    while len(nested) < 2:
        nm = re.search(r"\{\|[^\n]*cellspacing", trailing_text[i:])
        if not nm:
            break
        nstart = i + nm.start()
        nend = _find_table_end(trailing_text, nstart)
        nested.append(trailing_text[nstart:nend])
        i = nend

    def _extract(block: str) -> List[dict]:
        entries = []
        for lm in _LINE_RE.finditer(block):
            pos, jersey, name1, name2 = lm.groups()
            name = (name2 or name1).strip()
            entries.append({"pos": pos, "jersey": int(jersey), "name": name})
        return entries

    home = _extract(nested[0]) if len(nested) >= 1 else []
    away = _extract(nested[1]) if len(nested) >= 2 else []
    return home, away


def _norm_score(s: str) -> str:
    return re.sub(r"[^0-9\-]", "-", s.replace("−", "-")).strip("-")


# Box-template position code -> our Position enum. A different, slightly
# richer code set than `wikipedia_squad.POS_CODE_MAP` (that one's `{{nat rs
# player}}` template; this one's `{{rugbybox}}` lineup tables distinguish
# e.g. left/right wing and inside/outside centre in the starting XV, falling
# back to a generic code for bench replacements) - kept local to this module
# rather than overloading the other map's meaning.
_BOX_POS_MAP = {
    "FB": Position.FULLBACK,
    "RW": Position.RIGHT_WING,
    "LW": Position.LEFT_WING,
    "WG": Position.LEFT_WING,  # generic bench wing
    "OC": Position.OUTSIDE_CENTRE,
    "IC": Position.INSIDE_CENTRE,
    "CE": Position.INSIDE_CENTRE,  # generic bench centre
    "FH": Position.FLY_HALF,
    "SH": Position.SCRUM_HALF,
    "N8": Position.NUMBER_8,
    "OF": Position.OPENSIDE_FLANKER,
    "BF": Position.BLINDSIDE_FLANKER,
    "FL": Position.BLINDSIDE_FLANKER,  # generic bench flanker
    "RL": Position.LOCK_2,
    "LL": Position.LOCK_1,
    "LK": Position.LOCK_1,  # generic bench lock
    "TP": Position.TIGHTHEAD_PROP,
    "LP": Position.LOOSEHEAD_PROP,
    "PR": Position.LOOSEHEAD_PROP,  # generic bench prop
    "HK": Position.HOOKER,
}


def _build_pool(entries: List[dict], nation: str, year: int) -> List[Player]:
    strength_code = _NATION_TO_STRENGTH_CODE.get(nation)
    strength = UNION_STRENGTH.get(strength_code, DEFAULT_UNION_STRENGTH) if strength_code else DEFAULT_UNION_STRENGTH

    from .sources.pool_builder import _global_reference_peer_proxies
    peer_proxies_by_position = _global_reference_peer_proxies("2026")

    era = f"'{str(year)[-2:]}"
    pool: List[Player] = []
    seen = set()
    for entry in entries:
        position = _BOX_POS_MAP.get(entry["pos"])
        if position is None:
            continue
        full_name = entry["name"].strip()
        key = full_name.lower()
        if not full_name or key in seen:
            continue
        seen.add(key)
        attrs, source = _cross_reference_attributes(
            full_name, peer_proxies=peer_proxies_by_position.get(position)
        )
        if attrs is None:
            attrs = _archetype_attributes(position)
        if source != "legends_curated":
            attrs: Attributes = scale_to_union_strength(attrs, strength)
        data_source = (
            "legends_curated" if source == "legends_curated" else
            "historical_wikipedia" if source == "wikipedia" else "historical_archetype"
        )
        pool.append(Player(
            name=full_name,
            nation=nation,
            natural_position=position,
            attributes=attrs,
            era=era,
            notes=(
                f"{year} {'Tri Nations Series' if year <= 2011 else 'Rugby Championship'} "
                f"match lineup (real Wikipedia-sourced). "
                + ("World Rugby Hall of Fame - hand-tuned curated rating from "
                   "legends.CURATED_LEGENDS, not a Wikipedia/archetype estimate."
                   if source == "legends_curated" else
                   "Attributes from real rugbydata career stats (cross-referenced by name)."
                   if source == "wikipedia" else
                   "No rugbydata history found for this era/name, so attributes are a "
                   "generic position-archetype estimate, not a scouted rating.")
            ),
            data_source=data_source,
        ))
    return pool


# ---------------------------------------------------------------------------
# Per-match lineup source: (wiki page title, date string as it appears in
# that page's rugbybox, real home score, real away score, home nation name,
# away nation name) - `home`/`away` here are OUR chosen "team A"/"team B"
# labelling (team A is always the match's real winner, matching
# `display_name`/`blurb`/`real_score` below), NOT necessarily which side
# Wikipedia's own infobox lists first - `_resolve_match_pools` below checks
# the wiki page's own score string and swaps sides if needed so the right
# real lineup always ends up attached to the right team name.
# ---------------------------------------------------------------------------

_LINEUP_SOURCES: Dict[str, Tuple[str, str, int, int, str, str]] = {
    "rugby_championship_tb_1997": ("1997 Tri Nations Series", "9 August 1997", 55, 35, "New Zealand", "South Africa"),
    "rugby_championship_tb_1998": ("1998 Tri Nations Series", "15 August 1998", 24, 23, "South Africa", "New Zealand"),
    "rugby_championship_tb_1999": ("1999 Tri Nations Series", "28 August 1999", 28, 7, "Australia", "New Zealand"),
    "rugby_championship_tb_2000": ("2000 Tri Nations Series", "15 July 2000", 39, 35, "New Zealand", "Australia"),
    "rugby_championship_tb_2001": ("2001 Tri Nations Series", "1 September 2001", 29, 26, "Australia", "New Zealand"),
    "rugby_championship_tb_2002": ("2002 Tri Nations Series", "10 August 2002", 30, 23, "New Zealand", "South Africa"),
    "rugby_championship_tb_2003": ("2003 Tri Nations Series", "16 August 2003", 21, 17, "New Zealand", "Australia"),
    "rugby_championship_tb_2004": ("2004 Tri Nations Series", "21 August 2004", 23, 19, "South Africa", "Australia"),
    "rugby_championship_tb_2005": ("2005 Tri Nations Series", "27 August 2005", 31, 27, "New Zealand", "South Africa"),
    "rugby_championship_tb_2006": ("2006 Tri Nations Series", "19 August 2006", 34, 27, "New Zealand", "Australia"),
    "rugby_championship_tb_2007": ("2007 Tri Nations Series", "21 July 2007", 26, 12, "New Zealand", "Australia"),
    "rugby_championship_tb_2008": ("2008 Tri Nations Series", "12 July 2008", 30, 28, "South Africa", "New Zealand"),
    "rugby_championship_tb_2009": ("2009 Tri Nations Series", "12 September 2009", 32, 29, "South Africa", "New Zealand"),
    "rugby_championship_tb_2010": ("2010 Tri Nations Series", "21 August 2010", 29, 22, "New Zealand", "South Africa"),
    "rugby_championship_tb_2011": ("2011 Tri Nations Series", "27 August 2011", 25, 20, "Australia", "New Zealand"),
    "rugby_championship_tb_2012": ("2012 Rugby Championship", "6 October 2012", 32, 16, "New Zealand", "South Africa"),
    "rugby_championship_tb_2013": ("2013 Rugby Championship", "5 October 2013", 38, 27, "New Zealand", "South Africa"),
    "rugby_championship_tb_2014": ("2014 Rugby Championship", "27 September 2014", 34, 13, "New Zealand", "Argentina"),
    "rugby_championship_tb_2015": ("2015 Rugby Championship", "8 August 2015", 27, 19, "Australia", "New Zealand"),
    "rugby_championship_tb_2016": ("2016 Rugby Championship", "10 September 2016", 23, 17, "Australia", "South Africa"),
    "rugby_championship_tb_2017": ("2017 Rugby Championship", "7 October 2017", 25, 24, "New Zealand", "South Africa"),
}

_POOLS_CACHE: Dict[str, Tuple[List[Player], List[Player]]] = {}


def resolve_pools(match_id_or_match) -> Tuple[List[Player], List[Player]]:
    """Returns `(home_pool, away_pool)` for one of this module's matches -
    a `ClassicMatch` (checked by `.id`) or a bare match id string both work.
    Scrapes that match's own real Wikipedia lineup tables (disk-cached via
    `fetch_wikitext`), cross-references each name, and caches the built
    `Player` lists in-process so repeated calls (e.g. from tests) don't
    re-parse/re-cross-reference."""
    match_id = getattr(match_id_or_match, "id", match_id_or_match)
    if match_id in _POOLS_CACHE:
        return _POOLS_CACHE[match_id]

    title, datestr, home_score, away_score, home_name, away_name = _LINEUP_SOURCES[match_id]
    year = int(match_id.rsplit("_", 1)[-1])
    wikitext = fetch_wikitext(title)
    if not wikitext:
        raise ValueError(f"Could not fetch '{title}' for classic match '{match_id}'.")

    chosen = None
    for box_text, trailing in _find_rugbyboxes(wikitext):
        if datestr not in box_text:
            continue
        sm = re.search(r"score\s*=\s*([^\n|]+)", box_text)
        if not sm:
            continue
        parts = [p for p in _norm_score(sm.group(1)).split("-") if p]
        if len(parts) != 2:
            continue
        a, b = int(parts[0]), int(parts[1])
        if (a, b) == (home_score, away_score):
            chosen = (trailing, False)  # wiki's own "home" side == our home team
            break
        if (a, b) == (away_score, home_score):
            chosen = (trailing, True)  # wiki's own "home" side == our away team
            break
    if chosen is None:
        raise ValueError(f"Could not locate the real lineup tables for '{match_id}' on '{title}'.")

    trailing, swap = chosen
    wiki_first_entries, wiki_second_entries = _parse_lineup_tables(trailing)
    home_entries, away_entries = (
        (wiki_second_entries, wiki_first_entries) if swap else (wiki_first_entries, wiki_second_entries)
    )

    home_pool = _build_pool(home_entries, home_name, year)
    away_pool = _build_pool(away_entries, away_name, year)
    _POOLS_CACHE[match_id] = (home_pool, away_pool)
    return home_pool, away_pool


# ---------------------------------------------------------------------------
# The 21-entry Tier-B catalog (1997-2017; 1996 skipped - see module
# docstring). `home_code`/`away_code` follow the same union codes already
# used throughout the repo (`NZL`/`AUS`/`RSA`/`ARG`).
# ---------------------------------------------------------------------------

TIER_B_RUGBY_CHAMPIONSHIP_MATCHES: List[ClassicMatch] = [
    ClassicMatch(
        id="rugby_championship_tb_1997", tournament="rugby_championship", year=1997,
        display_name="1997 Tri Nations Series, Pretoria",
        date="1997-08-09", home_code="NZL", home_name="New Zealand",
        away_code="RSA", away_name="South Africa",
        blurb="A 90-point, 13-try thriller at Loftus Versfeld.",
        real_score="New Zealand 55-35 South Africa",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 15), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(95),  # real total: 90
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_1998", tournament="rugby_championship", year=1998,
        display_name="1998 Tri Nations Series, Durban",
        date="1998-08-15", home_code="RSA", home_name="South Africa",
        away_code="NZL", away_name="New Zealand",
        blurb="South Africa's first-ever Tri Nations title, won with this narrow home win.",
        real_score="South Africa 24-23 New Zealand",
        focus_team="home",
        objectives=[
            win("South Africa"), win_margin_at_least("South Africa", 1), no_cards("South Africa"),
            team_tries_at_least("South Africa", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(55),  # real total: 47
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_1999", tournament="rugby_championship", year=1999,
        display_name="1999 Tri Nations Series, Sydney",
        date="1999-08-28", home_code="AUS", home_name="Australia",
        away_code="NZL", away_name="New Zealand",
        blurb="Australia routed New Zealand in Sydney, though the All Blacks still won the title overall.",
        real_score="Australia 28-7 New Zealand",
        focus_team="home",
        objectives=[
            win("Australia"), win_margin_at_least("Australia", 15), no_cards("Australia"),
            team_tries_at_least("Australia", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            team_tries_at_least("Australia", 3),
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2000", tournament="rugby_championship", year=2000,
        display_name="2000 Tri Nations Series, Sydney (\"The Greatest Test\")",
        date="2000-07-15", home_code="NZL", home_name="New Zealand",
        away_code="AUS", away_name="Australia",
        blurb=(
            "Played in front of a world-record rugby union crowd of 109,874 at "
            "Stadium Australia; Jonah Lomu's late try sealed it - often called "
            "the greatest test match ever played."
        ),
        real_score="New Zealand 39-35 Australia",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 1), no_cards("New Zealand"),
            total_points_at_least(80),  # real total: 74
            team_tries_at_least("New Zealand", 6),
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2001", tournament="rugby_championship", year=2001,
        display_name="2001 Tri Nations Series, Sydney",
        date="2001-09-01", home_code="AUS", home_name="Australia",
        away_code="NZL", away_name="New Zealand",
        blurb="Toutai Kefu's last-gasp try won it - also John Eales' final Test.",
        real_score="Australia 29-26 New Zealand",
        focus_team="home",
        objectives=[
            win("Australia"), win_margin_at_least("Australia", 1), no_cards("Australia"),
            team_tries_at_least("Australia", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(60),  # real total: 55
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2002", tournament="rugby_championship", year=2002,
        display_name="2002 Tri Nations Series, Durban",
        date="2002-08-10", home_code="NZL", home_name="New Zealand",
        away_code="RSA", away_name="South Africa",
        blurb="A title-clinching bonus-point win for New Zealand in Durban.",
        real_score="New Zealand 30-23 South Africa",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 1), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            team_tries_at_least("New Zealand", 4),
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2003", tournament="rugby_championship", year=2003,
        display_name="2003 Tri Nations Series, Auckland",
        date="2003-08-16", home_code="NZL", home_name="New Zealand",
        away_code="AUS", away_name="Australia",
        blurb="A title decider at Eden Park - New Zealand finished the tournament unbeaten.",
        real_score="New Zealand 21-17 Australia",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 1), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(45),  # real total: 38
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2004", tournament="rugby_championship", year=2004,
        display_name="2004 Tri Nations Series, Durban",
        date="2004-08-21", home_code="RSA", home_name="South Africa",
        away_code="AUS", away_name="Australia",
        blurb="South Africa's 2nd title, completed with a comeback from 7-3 down at Kings Park.",
        real_score="South Africa 23-19 Australia",
        focus_team="home",
        objectives=[
            win("South Africa"), win_margin_at_least("South Africa", 1), no_cards("South Africa"),
            team_tries_at_least("South Africa", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(48),  # real total: 42
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2005", tournament="rugby_championship", year=2005,
        display_name="2005 Tri Nations Series, Dunedin",
        date="2005-08-27", home_code="NZL", home_name="New Zealand",
        away_code="RSA", away_name="South Africa",
        blurb="A late Keven Mealamu try sealed it for New Zealand in Dunedin.",
        real_score="New Zealand 31-27 South Africa",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 1), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(65),  # real total: 58
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2006", tournament="rugby_championship", year=2006,
        display_name="2006 Tri Nations Series, Auckland",
        date="2006-08-19", home_code="NZL", home_name="New Zealand",
        away_code="AUS", away_name="Australia",
        blurb="Two late tries clinched the title for New Zealand at Eden Park.",
        real_score="New Zealand 34-27 Australia",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 1), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            team_tries_at_least("New Zealand", 4),
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2007", tournament="rugby_championship", year=2007,
        display_name="2007 Tri Nations Series, Auckland",
        date="2007-07-21", home_code="NZL", home_name="New Zealand",
        away_code="AUS", away_name="Australia",
        blurb="Dan Carter kicked 7 penalties at Eden Park.",
        real_score="New Zealand 26-12 Australia",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 10), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(42),  # real total: 38
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2008", tournament="rugby_championship", year=2008,
        display_name="2008 Tri Nations Series, Dunedin",
        date="2008-07-12", home_code="RSA", home_name="South Africa",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "South Africa's first-ever win at Carisbrook, playing 10 minutes "
            "with 14 men, ending New Zealand's 30-match home win streak."
        ),
        real_score="South Africa 30-28 New Zealand",
        focus_team="home",
        objectives=[
            win("South Africa"), win_margin_at_least("South Africa", 1), no_cards("South Africa"),
            team_tries_at_least("South Africa", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(62),  # real total: 58
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2009", tournament="rugby_championship", year=2009,
        display_name="2009 Tri Nations Series, Hamilton",
        date="2009-09-12", home_code="RSA", home_name="South Africa",
        away_code="NZL", away_name="New Zealand",
        blurb="South Africa's first title since 2004, with Jean de Villiers' intercept try.",
        real_score="South Africa 32-29 New Zealand",
        focus_team="home",
        objectives=[
            win("South Africa"), win_margin_at_least("South Africa", 1), no_cards("South Africa"),
            team_tries_at_least("South Africa", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(65),  # real total: 61
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2010", tournament="rugby_championship", year=2010,
        display_name="2010 Tri Nations Series, Johannesburg",
        date="2010-08-21", home_code="NZL", home_name="New Zealand",
        away_code="RSA", away_name="South Africa",
        blurb="A comeback win at Soccer City that spoiled John Smit's 100th cap.",
        real_score="New Zealand 29-22 South Africa",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 1), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(56),  # real total: 51
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2011", tournament="rugby_championship", year=2011,
        display_name="2011 Tri Nations Series, Brisbane (Final Tri Nations Match)",
        date="2011-08-27", home_code="AUS", home_name="Australia",
        away_code="NZL", away_name="New Zealand",
        blurb="Kurtley Beale's late try won the final-ever Tri Nations match at Suncorp Stadium.",
        real_score="Australia 25-20 New Zealand",
        focus_team="home",
        objectives=[
            win("Australia"), win_margin_at_least("Australia", 1), no_cards("Australia"),
            team_tries_at_least("Australia", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(50),  # real total: 45
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2012", tournament="rugby_championship", year=2012,
        display_name="2012 Rugby Championship, Johannesburg",
        date="2012-10-06", home_code="NZL", home_name="New Zealand",
        away_code="RSA", away_name="South Africa",
        blurb="New Zealand finished the inaugural 4-team Rugby Championship unbeaten with this rout.",
        real_score="South Africa 16-32 New Zealand",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 10), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            team_tries_at_least("New Zealand", 4),
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2013", tournament="rugby_championship", year=2013,
        display_name="2013 Rugby Championship, Johannesburg",
        date="2013-10-05", home_code="NZL", home_name="New Zealand",
        away_code="RSA", away_name="South Africa",
        blurb="A classic 5-try title decider at Ellis Park, sealed by Beauden Barrett.",
        real_score="New Zealand 38-27 South Africa",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 5), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(70),  # real total: 65
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2014", tournament="rugby_championship", year=2014,
        display_name="2014 Rugby Championship, La Plata",
        date="2014-09-27", home_code="NZL", home_name="New Zealand",
        away_code="ARG", away_name="Argentina",
        blurb="A title-clinching bonus-point win for New Zealand in La Plata.",
        real_score="New Zealand 34-13 Argentina",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 15), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            team_tries_at_least("New Zealand", 4),
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2015", tournament="rugby_championship", year=2015,
        display_name="2015 Rugby Championship, Sydney",
        date="2015-08-08", home_code="AUS", home_name="Australia",
        away_code="NZL", away_name="New Zealand",
        blurb="Nic White sealed it, ending New Zealand's 3-year grip on the title.",
        real_score="Australia 27-19 New Zealand",
        focus_team="home",
        objectives=[
            win("Australia"), win_margin_at_least("Australia", 1), no_cards("Australia"),
            team_tries_at_least("Australia", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(50),  # real total: 46
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2016", tournament="rugby_championship", year=2016,
        display_name="2016 Rugby Championship, Round 5",
        date="2016-09-10", home_code="AUS", home_name="Australia",
        away_code="RSA", away_name="South Africa",
        blurb=(
            "Ended a 6-Test Australian losing streak against South Africa, "
            "in a year New Zealand went on to win the overall title unbeaten."
        ),
        real_score="Australia 23-17 South Africa",
        focus_team="home",
        objectives=[
            win("Australia"), win_margin_at_least("Australia", 1), no_cards("Australia"),
            team_tries_at_least("Australia", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(45),  # real total: 40
        ],
    ),
    ClassicMatch(
        id="rugby_championship_tb_2017", tournament="rugby_championship", year=2017,
        display_name="2017 Rugby Championship, Cape Town",
        date="2017-10-07", home_code="NZL", home_name="New Zealand",
        away_code="RSA", away_name="South Africa",
        blurb="New Zealand's 15th title, secured at Newlands while finishing the competition unbeaten.",
        real_score="New Zealand 25-24 South Africa",
        focus_team="home",
        objectives=[
            win("New Zealand"), win_margin_at_least("New Zealand", 1), no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 3),  # bonus: 3+ tries (margin bonus removed, duplicate win_margin tier bug)
            total_points_at_least(55),  # real total: 49
        ],
    ),
]


def get_tier_b_match(match_id: str) -> "ClassicMatch | None":
    for match in TIER_B_RUGBY_CHAMPIONSHIP_MATCHES:
        if match.id == match_id:
            return match
    return None
