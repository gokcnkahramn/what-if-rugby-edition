"""Generic parser for a REAL, whole-season rugby union Wikipedia article of
the "`<year> <Competition>`" family (confirmed live for both Six Nations/
Five Nations and Tri Nations/Rugby Championship pages) - a genuinely
richer real source than the separate "squads" page `historical_six_nations.py`
already uses for 2009-2021: each real match on the season page is a
`{{Rugbybox|...}}` score/date block immediately followed by a real,
match-specific two-team lineup table (position code, squad number, player
name) - the SAME real lineup-table format
`classic_matches_tier_b_six_nations.py`'s `MATCH_POS_CODE_MAP` already
parses for its 18 curated 2000-2017 matches, just walked across an entire
season's worth of matches instead of one hand-picked fixture.

Confirmed live (this session): Six Nations/Five Nations match-lineup
tables start with the 2000 edition - 1995-1999 (Five Nations) pages have
`{{Rugbybox}}` score blocks but NO lineup table at all (matches Tier B's
own documented reason for hand-assigning those 5 years' positions
instead). Tri Nations/Rugby Championship pages have the same lineup-table
format at least as far back as 1996 (spot-checked 1996/2011/2012/2020/2024
live) - not confirmed for every single year in between, so a caller should
still treat "did this year actually parse into real, full lineups" as the
ground truth, never assume every year in a nominal range works.

This module does NOT itself build `Player` objects or decide which years
are "available" - it only turns real wikitext into a real, structured
`SeasonMatch` list (`parse_season_matches`). The two competition-specific
modules (`historical_six_nations.py`'s pre-2009 extension,
`historical_rugby_championship.py`) turn that into `Player`/fixture data
using their own real cross-reference/archetype pipeline, same convention
as `historical_rwc.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Same lineup-table code set `classic_matches_tier_b_six_nations.py`'s own
# `MATCH_POS_CODE_MAP` already uses, confirmed against real match-lineup
# tables for both competitions (Rugby Championship/Tri Nations pages use
# the identical code vocabulary - verified live for 2005/2012/2024).
# Deliberately duplicated here rather than imported from that Tier-B
# catalog module (a "data sources" module importing from a "classic
# matches" data module would be a backwards dependency) - keep both in
# sync by hand if either ever needs a new code.
MATCH_POS_CODE_MAP: Dict[str, str] = {
    "FB": "Fullback", "RW": "Right Wing", "OC": "Outside Centre", "IC": "Inside Centre",
    "LW": "Left Wing", "FH": "Fly-half", "SH": "Scrum-half", "N8": "Number 8",
    "OF": "Openside Flanker", "BF": "Blindside Flanker", "RL": "Lock (5)", "LL": "Lock (4)",
    "TP": "Tighthead Prop", "HK": "Hooker", "LP": "Loosehead Prop",
    # Looser replacement-only codes (no left/right or loosehead/tighthead
    # distinction on the page itself) - same best-effort assignment
    # Tier B's own `MATCH_POS_CODE_MAP` already uses for these.
    "PR": "Loosehead Prop", "LK": "Lock (4)", "FL": "Blindside Flanker",
    "CE": "Inside Centre", "WG": "Left Wing", "C": "Inside Centre", "W": "Left Wing",
}


@dataclass
class SeasonMatchLineupEntry:
    position_code: str
    name: str
    jersey_number: int
    is_starter: bool


@dataclass
class SeasonMatch:
    date: str
    home_code: str
    away_code: str
    home_score: Optional[int]
    away_score: Optional[int]
    home_lineup: List[SeasonMatchLineupEntry] = field(default_factory=list)
    away_lineup: List[SeasonMatchLineupEntry] = field(default_factory=list)


_TEAM_CODE_RE = re.compile(r"\{\{Ru(?:-rt)?\|([A-Za-z]{2,3})(?:\|[^}]*)?\}\}", re.IGNORECASE)
_SCORE_RE = re.compile(r"[–−\-]")  # en dash / minus sign / hyphen, whichever the page used
_LINEUP_ROW_RE = re.compile(r"^\|\s*([A-Za-z0-9]{1,3})\s*\|\|\s*'''?\s*(\d+)\s*'''?\s*\|\|\s*(.+?)\s*$")
_INNER_TABLE_START_RE = re.compile(r'\{\|[^\n{}]*cellspacing\s*=\s*"0"', re.IGNORECASE)


def _clean_name_cell(raw: str) -> str:
    """Strips captaincy/sub markers and wikilink/ref markup down to a real
    plain player name - e.g. `[[John Smit]] ([[Captain (sports)|c]])` ->
    `John Smit`, `{{subst|...}}`-free `[[Gary Botha]]` -> `Gary Botha`."""
    raw = re.sub(r"<ref[^>]*>.*?</ref>", "", raw, flags=re.S)
    raw = re.sub(r"<ref[^>]*/?>", "", raw)
    raw = re.sub(r"\([^()]*\)", "", raw)  # drop "(c)"/"(Captain)" trailer
    raw = re.sub(r"\{\{[^{}]*\}\}", "", raw)
    m = re.search(r"\[\[([^\]|]*)(?:\|[^\]]*)?\]\]", raw)
    name = m.group(1) if m else raw
    return name.strip()


def _find_matching_close(text: str, open_pos: int) -> int:
    """Returns the index right after the `}}` that closes the `{{` opening
    at `open_pos`, tracking nesting depth - a naive first-`}}` search cuts
    the block off inside a NESTED template (e.g. `{{Ru-rt|RSA}}` inside
    `{{Rugbybox|home={{Ru-rt|RSA}}|...}}`), which is exactly what a real
    Rugbybox block always contains."""
    depth = 0
    i = open_pos
    n = len(text)
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


def _parse_rugbybox_fields(block: str) -> dict:
    fields: Dict[str, str] = {}
    for m in re.finditer(r"\|\s*(\w+)\s*=\s*(.*)", block):
        key, value = m.group(1), m.group(2).strip()
        if key not in fields:  # first occurrence wins (home/away are unique keys)
            fields[key] = value
    return fields


def _parse_lineup_lines(lines: List[str]) -> List[SeasonMatchLineupEntry]:
    entries = []
    for line in lines:
        m = _LINEUP_ROW_RE.match(line.strip())
        if not m:
            continue
        code, number, raw_name = m.group(1), int(m.group(2)), m.group(3)
        name = _clean_name_cell(raw_name)
        if not name:
            continue
        entries.append(SeasonMatchLineupEntry(
            position_code=code.upper(), name=name, jersey_number=number, is_starter=number <= 15,
        ))
    return entries


def parse_season_matches(wikitext: str) -> List[SeasonMatch]:
    """Walks every real `{{Rugbybox|...}}` block on a season page, in the
    page's own order (= chronological order - matches are grouped under
    `===Round N===`/`===Week N===` headers in real date order), pairing
    each with the real two-team lineup table immediately following it (if
    any - a match with no lineup table, e.g. a scorer-only pre-2000 Six
    Nations block, is still returned with empty `home_lineup`/
    `away_lineup`, never a fabricated one). Returns a REAL fixture list a
    caller can both replay in actual historical order and use to build a
    real per-team roster from (merging every match's real lineup,
    deduping by name)."""
    matches: List[SeasonMatch] = []
    # Split on each real Rugbybox occurrence - the text between one and
    # the next is "that match's own content" (lineup tables, if present).
    starts = [m.start() for m in re.finditer(r"\{\{\s*[Rr]ugbybox", wikitext)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(wikitext)
        chunk = wikitext[start:end]
        box_close = _find_matching_close(chunk, 0)
        box_block = chunk[:box_close]
        rest = chunk[box_close:]

        fields = _parse_rugbybox_fields(box_block)
        # Most years use `home=`/`away=`; some early Tri Nations editions
        # (confirmed live: 1996) use `team1=`/`team2=` instead - same
        # template, just an older field-naming convention.
        home_raw = fields.get("home") or fields.get("team1", "")
        away_raw = fields.get("away") or fields.get("team2", "")
        home_m = _TEAM_CODE_RE.search(home_raw)
        away_m = _TEAM_CODE_RE.search(away_raw)
        if not home_m or not away_m:
            continue
        home_code, away_code = home_m.group(1).upper(), away_m.group(1).upper()

        home_score: Optional[int] = None
        away_score: Optional[int] = None
        score_raw = fields.get("score", "")
        parts = _SCORE_RE.split(score_raw, maxsplit=1)
        if len(parts) == 2:
            try:
                home_score, away_score = int(parts[0].strip()), int(re.sub(r"\D.*$", "", parts[1].strip()))
            except ValueError:
                home_score = away_score = None

        # Two side-by-side inner lineup tables (home then away), each its
        # own `{| cellspacing="0"...|}` block - split the "rest" of this
        # match's chunk at the boundary between them.
        table_starts = [m.start() for m in _INNER_TABLE_START_RE.finditer(rest)]
        home_lineup: List[SeasonMatchLineupEntry] = []
        away_lineup: List[SeasonMatchLineupEntry] = []
        if len(table_starts) >= 2:
            home_text = rest[table_starts[0]:table_starts[1]]
            away_text = rest[table_starts[1]:table_starts[2] if len(table_starts) > 2 else None]
            home_lineup = _parse_lineup_lines(home_text.splitlines())
            away_lineup = _parse_lineup_lines(away_text.splitlines())

        matches.append(SeasonMatch(
            date=fields.get("date", ""), home_code=home_code, away_code=away_code,
            home_score=home_score, away_score=away_score,
            home_lineup=home_lineup, away_lineup=away_lineup,
        ))
    return matches
