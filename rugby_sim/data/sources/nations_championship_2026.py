"""The 2026 Nations Championship - real fixture list recovered from
Wikipedia, used as a `real_fixtures.load_real_fixtures` fallback.

Why this exists at all: this is a brand-new competition (see
`real_fixtures.TOURNAMENTS["nations_championship"]`'s comment) and, as of
this writing (2026-11-16), our primary stats source `rugbydata` has NO
fixture rows for it at all - its 2026 coverage stops 2026-09-06, well
before this competition's November window even starts, let alone its July
window. So `fetch_season_fixture_index("2026")` can never recover these
matches the normal way `real_fixtures.py` recovers Six Nations/Rugby
Championship/Autumn Nations Series fixtures.

What IS available: the competition's actual fixture list (including real
results for the rounds already played) is already up on Wikipedia, built
from a plain wikitable (NOT a `{{footballbox}}`/`{{nat fs player}}`-style
template - just `{| ... |}` rows with `align=right|<date>||align=right|
{{ru-rt|CODE}}||align=center|[[...|<score or "v">]]||{{ru|CODE}}||<venue>`
per match). Confirmed live against
https://en.wikipedia.org/wiki/2026_Nations_Championship on 2026-11-16:
Rounds 1-5 (30 matches, 4 July - 15 November 2026) are played with real
scores; Round 6 (21 November 2026, 6 matches) is a real, firmly-scheduled
fixture list with known opponents/dates but not yet played ("v" in place
of a score - same convention `world_cup_2027.py` uses for a competition
that hadn't started at all when it was built: a real fixture replays with
OUR engine regardless of whether the real match has already happened).

The `===Finals===` section (27-29 Nov 2026, Twickenham) is NOT included:
those pairings are explicitly ranking-dependent ("each team matched
against its equivalently ranked team") and are not yet determined by the
live page - including them would mean fabricating pairings, which this
project's house rule on real-fixture sourcing forbids. Re-check this
module against the live page once the finals bracket is actually
confirmed, and extend it then - do not guess ahead of the source.

This is scoped to EXACTLY this one competition/season. It is a narrow,
documented, temporary-until-rugbydata-catches-up patch (see
`real_fixtures.load_real_fixtures`'s fallback branch), not a general
Wikipedia-fixture mechanism.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from .wikipedia_squad import fetch_wikitext

PAGE_TITLE = "2026 Nations Championship"

# Wikipedia's `{{ru-rt|...}}`/`{{ru|...}}` three-letter codes -> the same
# full nation display names used everywhere else in this project (matches
# `real_fixtures.TOURNAMENTS["nations_championship"].teams` exactly).
CODE_TO_NATION = {
    "ENG": "England", "FRA": "France", "IRE": "Ireland", "SCO": "Scotland",
    "WAL": "Wales", "ITA": "Italy",
    "NZL": "New Zealand", "AUS": "Australia", "RSA": "South Africa",
    "ARG": "Argentina", "JPN": "Japan", "FIJ": "Fiji",
}

# The two real hemisphere pools (confirmed against the live Wikipedia page,
# same date as the module docstring's verification) - the Six Nations
# unions vs. the six Southern Hemisphere/Asia-Pacific unions. Every one of
# the 36 round-robin fixtures parsed above is between a NORTH_POOL team and
# a SOUTH_POOL team (never a same-pool pairing), so each team's 6 fixtures
# already form a complete head-to-head record against every member of the
# other pool - this is what `Tournament.run_nations_championship` (see
# `tournament.py`) uses to build each pool's own standings table and then
# pair the pools' same-rank finishers for the Nov 27-29 2026 finals
# weekend. Defined here once (not duplicated in `real_fixtures.py` or
# `tournament.py`) since this module already owns the canonical team set
# for this competition/season.
NORTH_POOL = frozenset({"England", "France", "Ireland", "Scotland", "Wales", "Italy"})
SOUTH_POOL = frozenset({"New Zealand", "Australia", "South Africa", "Argentina", "Japan", "Fiji"})

_MONTH_NUM = {
    "January": "01", "February": "02", "March": "03", "April": "04",
    "May": "05", "June": "06", "July": "07", "August": "08",
    "September": "09", "October": "10", "November": "11", "December": "12",
}

_ROUND_HEADING_RE = re.compile(r"^====\s*Round\s+(\d+)\s*====\s*$")
# One match row, e.g.:
#   | align="right" |4 July 2026|| align="right" |{{ru-rt|NZL}}|| align="center" |[[...|34-32]]||{{ru|FRA}}||venue
# or the more compact style used from Round 2 onward:
#   |align=right|11 July 2026||align=right|{{ru-rt|NZL}}||align=center|[[...|47-17]]||{{ru|ITA}}||venue
_ROW_RE = re.compile(
    r'align="?right"?\s*\|\s*(\d{1,2} \w+ 2026)\s*\|\|'
    r'\s*align="?right"?\s*\|\s*\{\{ru-rt\|(\w+)\}\}\s*\|\|'
    r'\s*align="?center"?\s*\|\s*\[\[[^\]]*\|([^\]]+)\]\]\s*\|\|'
    r'\s*\{\{ru\|(\w+)\}\}'
)
# Finals section starts here - everything from this heading on is excluded
# (ranking-dependent pairings not yet determined - see module docstring).
_STOP_HEADING_RE = re.compile(r"^===\s*Finals\s*===\s*$")


@dataclass
class NCFixture:
    round_no: int
    date: str  # YYYYMMDD
    home: str
    away: str
    played: bool  # False for a scheduled-but-not-yet-played match (score == "v")


def _parse_wiki_date(raw: str) -> Optional[str]:
    """"4 July 2026" -> "20260704"."""
    parts = raw.strip().split()
    if len(parts) != 3:
        return None
    day, month_name, year = parts
    month = _MONTH_NUM.get(month_name)
    if month is None:
        return None
    return f"{year}{month}{int(day):02d}"


def parse_fixtures(wikitext: str) -> List[NCFixture]:
    """Walks the `====Round N====` sections under `==Fixtures==`, stopping
    before `===Finals===` (whose pairings are ranking-dependent and not
    yet determined - see module docstring). Each match row is parsed
    regardless of whether it carries a real score or the "v" placeholder
    Wikipedia uses for a scheduled-but-unplayed fixture."""
    fixtures: List[NCFixture] = []
    current_round: Optional[int] = None

    for line in wikitext.splitlines():
        stripped = line.strip()

        if _STOP_HEADING_RE.match(stripped):
            break

        m_round = _ROUND_HEADING_RE.match(stripped)
        if m_round:
            current_round = int(m_round.group(1))
            continue

        if current_round is None:
            continue

        m_row = _ROW_RE.search(line)
        if not m_row:
            continue
        raw_date, home_code, score, away_code = m_row.groups()
        date = _parse_wiki_date(raw_date)
        home = CODE_TO_NATION.get(home_code)
        away = CODE_TO_NATION.get(away_code)
        if date is None or home is None or away is None:
            continue
        played = score.strip().lower() != "v"
        fixtures.append(NCFixture(
            round_no=current_round, date=date, home=home, away=away, played=played,
        ))

    return fixtures


def fetch_nations_championship_2026_fixtures(use_cache: bool = True) -> List[NCFixture]:
    wikitext = fetch_wikitext(PAGE_TITLE, use_cache=use_cache)
    if not wikitext:
        return []
    return parse_fixtures(wikitext)
