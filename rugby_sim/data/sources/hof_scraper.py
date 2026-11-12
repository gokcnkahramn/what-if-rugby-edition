"""Builds the *full* World Rugby Hall of Fame legend roster (all ~190
Wikipedia category members), not just a hand-picked subset.

Mechanism: fetch the category member list, then for each title fetch its
own Wikipedia page and look for an `{{Infobox rugby biography}}` - that's
what automatically filters out the non-player entries the category also
contains (teams, tours, clubs, schools, pure administrators/commentators/
coaches without a playing infobox, concepts like William Webb Ellis). For
every real player bio found, `position`, `repteam*` (national side) and
`repyears*` (international career span) are parsed straight out of the
infobox - these are real, not guessed.

What's *not* real: box-score-derived attributes. rugbydata doesn't reach
these careers (many predate it by decades), so every entry here gets a
position-archetype rating (`attribute_mapping`'s shared `_ARCHETYPES`),
tagged `data_source="hof_archetype"` - distinct from the ~30 hand-curated
`legends.py` entries (`data_source="manual"`) so it's clear which ratings
were individually tuned and which are a generic per-position template.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import List, Optional

from ...models.attributes import Attributes
from ...models.player import Player
from ...models.position import Position
from .rugby_data_client import CACHE_DIR
from .wikipedia_squad import USER_AGENT, WIKI_API, _archetype_attributes, fetch_wikitext

HOF_CATEGORY = "Category:World Rugby Hall of Fame inductees"

# Titles in the category that are demonstrably not individual rugby players
# (teams, tours, institutions, pure non-playing figures) - skipped before
# even trying to fetch them, since they'd never have a playing infobox
# anyway and some (e.g. national team pages) are huge.
_NON_PLAYER_TITLES = {
    "International Rugby Hall of Fame", "World Rugby Hall of Fame",
    "1888 British Lions tour to New Zealand and Australia",
    "1888–89 New Zealand Native football team",
    "Barbarian F.C.", "Cardiff RFC", "Melrose RFC", "Rugby School",
    "Romania national rugby union team",
    "United States men's national rugby union team",
    "The Varsity Match", "Pierre de Coubertin", "Nelson Mandela",
    "William Webb Ellis", "Bill McLaren", "Terry McLean",
    "Vladimir Ilyushin",
}

# Human-readable infobox position text -> our Position enum. Several real
# distinctions (loosehead/tighthead, lock 4/5, left/right wing, inside/
# outside centre, blindside/openside) aren't resolvable from this text
# alone, same limitation as the other scrapers - one representative slot.
_POSITION_KEYWORDS = [
    ("hooker", Position.HOOKER),
    ("loosehead", Position.LOOSEHEAD_PROP),
    ("tighthead", Position.TIGHTHEAD_PROP),
    ("prop", Position.LOOSEHEAD_PROP),
    ("lock", Position.LOCK_1),
    ("second row", Position.LOCK_1),
    ("number 8", Position.NUMBER_8),
    ("number eight", Position.NUMBER_8),
    ("eighthman", Position.NUMBER_8),
    ("flanker", Position.OPENSIDE_FLANKER),
    ("breakaway", Position.OPENSIDE_FLANKER),
    ("scrum-half", Position.SCRUM_HALF),
    ("scrum half", Position.SCRUM_HALF),
    ("fly-half", Position.FLY_HALF),
    ("fly half", Position.FLY_HALF),
    ("out-half", Position.FLY_HALF),
    ("outside half", Position.FLY_HALF),
    ("centre", Position.INSIDE_CENTRE),
    ("center", Position.INSIDE_CENTRE),
    ("wing", Position.LEFT_WING),
    ("fullback", Position.FULLBACK),
    ("full-back", Position.FULLBACK),
    ("full back", Position.FULLBACK),
]

# Known nation display names to recognize inside a `repteam`/`country` field
# that might be wrapped in any number of different templates/wikilinks.
_KNOWN_NATIONS = [
    "England", "France", "Ireland", "Scotland", "Wales", "Italy",
    "New Zealand", "Australia", "South Africa", "Argentina", "Japan",
    "Fiji", "Georgia", "Romania", "Spain", "Portugal", "Samoa", "Tonga",
    "United States", "Canada", "Uruguay", "Chile", "Namibia",
    "British Lions", "British and Irish Lions",
]


def _cache_path():
    path = CACHE_DIR / "wikipedia" / "_hof_category_members.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def fetch_hof_category_members() -> List[str]:
    """All page titles in the World Rugby Hall of Fame Wikipedia category."""
    cache_file = _cache_path()
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    params = {
        "action": "query", "list": "categorymembers", "cmtitle": HOF_CATEGORY,
        "cmlimit": "500", "format": "json",
    }
    url = f"{WIKI_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"[hof_scraper] could not list HoF category: {e}")
        return []

    titles = [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
    cache_file.write_text(json.dumps(titles), encoding="utf-8")
    return titles


def _strip_wikitext(raw: str) -> str:
    """Best-effort plain text out of a wikitext field: drop templates,
    keep a wikilink's display text, trim refs/whitespace."""
    text = re.sub(r"<ref[^/]*?/>|<ref.*?</ref>", "", raw, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    return text.strip(" \t\n|")


def _parse_position(wikitext: str) -> Optional[Position]:
    """Many infoboxes list more than one position as a career progressed
    (e.g. "Wing, Number 8" for someone who converted positions) - take
    whichever keyword appears *first* in that field's own text, which in
    practice is usually how the person is primarily known."""
    m = re.search(r"\|\s*position\s*=\s*([^\n]+)", wikitext)
    if not m:
        return None
    text = _strip_wikitext(m.group(1)).lower()
    best: Optional[tuple[int, Position]] = None
    for keyword, position in _POSITION_KEYWORDS:
        idx = text.find(keyword)
        if idx != -1 and (best is None or idx < best[0]):
            best = (idx, position)
    return best[1] if best else None


_LIONS_LABELS = {"british lions", "british and irish lions"}

# A handful of players are famous for a *different* nation than whichever
# one their infobox's representative-team fields happen to list first (not
# a Lions-style ambiguity - a genuine switch, e.g. briefly capped for their
# birth nation before the union they're actually a Hall of Fame legend for).
# Checked individually; not a general rule, just the cases that came up.
_NATION_OVERRIDES = {
    "Diego Domínguez (rugby union)": "Italy",  # capped briefly for Argentina, HoF career is with Italy
}


def _parse_nation(wikitext: str) -> Optional[str]:
    """Infoboxes list representative teams chronologically (repteam1,
    repteam2, ...), but *not* in a consistent order between "home nation
    first, Lions second" and "Lions/underage side first, home nation
    second" - different editors, no reliable convention either way. What
    IS reliable: a British & Irish Lions call-up is never someone's only
    representative honour (it's a composite invitational side drawn from
    the home nations), so it's always deprioritized in favour of whichever
    real union nation is also mentioned, in whatever slot that appears."""
    hits: List[str] = []
    for param in ("repteam1", "repteam2", "repteam3", "repteam4", "country", "nationalteam"):
        m = re.search(rf"\|\s*{param}\s*=\s*([^\n]+)", wikitext)
        if not m:
            continue
        raw = m.group(1)
        cleaned = _strip_wikitext(raw)
        for nation in _KNOWN_NATIONS:
            if nation.lower() in raw.lower() or nation.lower() in cleaned.lower():
                hits.append(nation)
                break

    for nation in hits:
        if nation.lower() not in _LIONS_LABELS:
            return nation
    return hits[0] if hits else None


def _parse_era(wikitext: str) -> Optional[str]:
    for param in ("repyears1", "repyears2", "years1"):
        m = re.search(rf"\|\s*{param}\s*=\s*([^\n]+)", wikitext)
        if not m:
            continue
        years = re.findall(r"(19|20)(\d{2})", m.group(1))
        if years:
            full_years = [int(a + b) for a, b in years]
            mid = full_years[len(full_years) // 2]
            return f"'{str(mid)[-2:]}"
    return None


def build_hof_legend(title: str) -> Optional[Player]:
    """Returns a `Player` for one Hall of Fame category member, or None if
    the page isn't a playing-career biography (filters out non-players) or
    its infobox doesn't give us a usable position/nation."""
    if title in _NON_PLAYER_TITLES or ":" in title:
        return None
    wikitext = fetch_wikitext(title)
    if not wikitext or "nfobox rugby" not in wikitext.lower():
        return None

    position = _parse_position(wikitext)
    nation = _NATION_OVERRIDES.get(title) or _parse_nation(wikitext)
    if position is None or nation is None:
        return None
    era = _parse_era(wikitext) or "'00"

    display_name = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
    return Player(
        name=display_name,
        nation=nation,
        natural_position=position,
        attributes=_archetype_attributes(position),
        era=era,
        notes=(
            f"World Rugby Hall of Fame inductee (position/nation/era parsed "
            f"from their Wikipedia infobox); attributes are a generic "
            f"position-archetype estimate, not a scouted rating."
        ),
        data_source="hof_archetype",
    )


def build_all_hof_legends() -> List[Player]:
    """Every Hall of Fame category member that resolves to a usable
    `Player`. Network-heavy on first run (~190 page fetches); each page is
    disk-cached by `fetch_wikitext`, so repeat calls are instant."""
    legends: List[Player] = []
    seen_names = set()
    for title in fetch_hof_category_members():
        player = build_hof_legend(title)
        if player is None:
            continue
        key = player.name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        legends.append(player)
    return legends
