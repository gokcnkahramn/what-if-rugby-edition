"""Fills out a union's 2026 pool from its Wikipedia "Current squad" section,
for unions rugbydata doesn't have full 2026 player-level data for.

How this works, end to end:
1. Every national-team Wikipedia page (checked live for Georgia, Spain,
   Namibia, Samoa, Tonga, Uruguay, Chile, Romania - all consistent) has a
   `==Current squad==` section built from a very regular template:
   `{{nat rs player|pos=HK|name={{sortname|Luka|Goginava}}|age=...|caps=8|
   club=...}}` - one line per player, with a jersey-style position code
   (HK/PR/LK/FL/BR/N8/SH/FH/CE/WG/FB) and an explicit "Caps updated:" date,
   so this really is the current (2026) squad, not a stale snapshot.
2. Wikipedia gives a name and a position, but no box-score stats - so for
   each scraped name, we look it up in rugbydata's *global* player registry
   (`player_registry.parquet`, ~9,200 players, independent of nation/season)
   and, if found, aggregate THAT person's real career stats (any team, any
   competition - club rugby included) into `Attributes` via the same
   `attribute_mapping` used everywhere else. This is a genuinely different,
   broader lookup than `pool_builder`'s nation+season-scoped one.
3. If a scraped name isn't in the registry at all (no rugbydata footprint,
   common for the less-tracked unions), we fall back to a fixed
   position-archetype rating (a plausible competent-international baseline,
   not a real scouted number) and tag it `data_source="wikipedia_archetype"`
   so it's never confused with a real stats-derived rating.
"""

from __future__ import annotations

import difflib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional

import pandas as pd

from ...models.attributes import Attributes
from ...models.player import Player
from ...models.position import Position
from .attribute_mapping import (
    DEFAULT_UNION_STRENGTH,
    UNION_STRENGTH,
    map_stats_to_attributes,
    scale_to_union_strength,
)
from .rugby_data_client import CACHE_DIR, fetch_player_history, fetch_player_registry

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "what-if-rugby-edition/0.1 (educational hobby project; no API key)"
WIKI_CACHE_DIR = CACHE_DIR / "wikipedia"

# Wikipedia pos= codes -> our Position enum. Several real-world distinctions
# (loosehead/tighthead, lock 4/5, left/right wing, inside/outside centre)
# aren't in the template, so these map to one representative slot each -
# same limitation as the rugbydata-derived pools, draft into either freely.
POS_CODE_MAP = {
    "HK": Position.HOOKER,
    "PR": Position.LOOSEHEAD_PROP,
    "LK": Position.LOCK_1,
    "FL": Position.BLINDSIDE_FLANKER,
    "BR": Position.BLINDSIDE_FLANKER,
    "N8": Position.NUMBER_8,
    "SH": Position.SCRUM_HALF,
    "FH": Position.FLY_HALF,
    "CE": Position.INSIDE_CENTRE,
    "C": Position.INSIDE_CENTRE,
    "WG": Position.LEFT_WING,
    "W": Position.LEFT_WING,
    "FB": Position.FULLBACK,
}

# A plausible "solid Tier 2 international" baseline per position, used only
# when a scraped player has no findable rugbydata history at all. Deliberately
# mid-table (50s-60s), not tuned per player - a template, not a rating.
_ARCHETYPES = {
    Position.LOOSEHEAD_PROP: dict(scrummaging=60, strength=62, tackling=56, fitness=55),
    Position.HOOKER: dict(scrummaging=56, lineout_throwing=58, tackling=58, handling=54),
    Position.TIGHTHEAD_PROP: dict(scrummaging=62, strength=64, tackling=55, fitness=54),
    Position.LOCK_1: dict(lineout_jumping=58, strength=60, tackling=58, scrummaging=55),
    Position.LOCK_2: dict(lineout_jumping=58, strength=60, tackling=58, scrummaging=55),
    Position.BLINDSIDE_FLANKER: dict(tackling=62, strength=58, fitness=60),
    Position.OPENSIDE_FLANKER: dict(tackling=62, fitness=62, game_intelligence=56),
    Position.NUMBER_8: dict(strength=60, tackling=58, fitness=58, handling=52),
    Position.SCRUM_HALF: dict(passing=58, game_intelligence=55, kicking_game=50, pace=55),
    Position.FLY_HALF: dict(kicking_game=55, game_intelligence=56, passing=56, goal_kicking=50),
    Position.LEFT_WING: dict(pace=62, footwork=55, agility=58),
    Position.RIGHT_WING: dict(pace=62, footwork=55, agility=58),
    Position.INSIDE_CENTRE: dict(tackling=55, passing=52, pace=54),
    Position.OUTSIDE_CENTRE: dict(pace=56, footwork=54, passing=52),
    Position.FULLBACK: dict(aerial=54, kicking_game=50, pace=55, composure=52),
}


def _wiki_cache_path(title: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
    path = WIKI_CACHE_DIR / f"{slug}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def fetch_wikitext(title: str, use_cache: bool = True) -> Optional[str]:
    """Fetches a Wikipedia page's raw wikitext (main revision), disk-cached."""
    cache_file = _wiki_cache_path(title)
    if use_cache and cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    params = {
        "action": "query", "titles": title, "format": "json",
        "prop": "revisions", "rvprop": "content", "rvslots": "main",
        "redirects": 1,
    }
    url = f"{WIKI_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                time.sleep(8 * (attempt + 1))
                continue
            print(f"[wikipedia_squad] could not fetch '{title}': {e}")
            return None
        except Exception as e:
            print(f"[wikipedia_squad] could not fetch '{title}': {e}")
            return None
    else:
        return None

    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    revisions = page.get("revisions")
    if not revisions:
        return None
    content = revisions[0]["slots"]["main"]["*"]
    cache_file.write_text(content, encoding="utf-8")
    time.sleep(2.5)  # politeness delay between live Wikipedia requests
    return content


def parse_current_squad(wikitext: str) -> List[dict]:
    """Extracts {pos, first, last, caps} entries from a `{{nat rs player}}`
    -templated "Current squad" section. Returns [] if that section/template
    isn't present on this page (format varies page to page - never guess)."""
    start = wikitext.find("Current squad")
    if start == -1:
        return []
    heading_match = re.search(r"\n==[^=]", wikitext[start + 10:])
    end = start + 10 + heading_match.start() if heading_match else len(wikitext)
    section = wikitext[start:end]

    entries = []
    seen_names = set()
    for line in section.splitlines():
        if "nat rs player" not in line:
            continue
        pos_m = re.search(r"pos=(\w+)", line)
        name_m = re.search(r"name=\{\{sortname\|([^|}]+)\|([^|}]+)", line)
        caps_m = re.search(r"\|caps=(\d+)", line)
        if not (pos_m and name_m):
            continue
        first, last = name_m.group(1).strip(), name_m.group(2).strip()
        # Some pages genuinely list a utility player twice (once per position
        # group they cover, e.g. lock *and* flanker) - keep only their first
        # (primary) listing so a drafted lineup never sees the same name twice.
        key = f"{first} {last}".lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        entries.append({
            "pos": pos_m.group(1),
            "first": first,
            "last": last,
            "caps": int(caps_m.group(1)) if caps_m else 0,
        })
    return entries


def _cross_reference_attributes(full_name: str, peer_proxies: Optional[dict] = None) -> tuple[Attributes, str]:
    """Looks `full_name` up in rugbydata's global player registry and, if
    found, aggregates that person's real career stats. Falls back to None
    if there's no usable match - caller supplies the position archetype.
    `peer_proxies` (see `pool_builder._global_reference_peer_proxies`) is
    passed straight through to `map_stats_to_attributes` so this person's
    rating is calibrated against the same cross-union reference pool as
    every rugbydata-sourced player, not scored in isolation."""
    registry = fetch_player_registry()
    if registry is None or registry.empty:
        return None, "wikipedia_archetype"

    clean_names = registry["player_name"].astype(str).str.lstrip("*").str.strip()
    target = full_name.strip().lower()

    exact = registry.loc[clean_names.str.lower() == target, "player_id"].tolist()
    candidates = exact
    if not candidates:
        close = difflib.get_close_matches(target, clean_names.str.lower().tolist(), n=3, cutoff=0.93)
        if close:
            candidates = registry.loc[clean_names.str.lower().isin(close), "player_id"].tolist()

    for pid in candidates:
        history = fetch_player_history(pid)
        if history is None or history.empty:
            continue
        numeric_cols = [
            c for c in history.columns
            if pd.api.types.is_numeric_dtype(history[c]) and c not in ("weight_kg", "height_cm")
        ]
        summed = history[numeric_cols].sum(numeric_only=True)
        caps = len(history)
        if caps == 0:
            continue
        return map_stats_to_attributes(summed, caps, peer_proxies=peer_proxies), "wikipedia"

    return None, "wikipedia_archetype"


def _archetype_attributes(position: Position) -> Attributes:
    return Attributes(**_ARCHETYPES.get(position, {})).clamp()


# code -> Wikipedia page title. Most unions follow "<Nation> national rugby
# union team"; a few need an explicit override (checked live - some redirect
# or use a different page structure and are better skipped than guessed at).
WIKI_UNION_PAGES = {
    "GEO": "Georgia national rugby union team",
    "ROU": "Romania national rugby union team",
    "ESP": "Spain national rugby union team",
    "POR": "Portugal national rugby union team",
    "SAM": "Samoa national rugby union team",
    "TGA": "Tonga national rugby union team",
    "URU": "Uruguay national rugby union team",
    "CHI": "Chile national rugby union team",
    "NAM": "Namibia national rugby union team",
    "FIJ": "Fiji national rugby union team",
    "USA": "United States national rugby union team",
    "CAN": "Canada national rugby union team",
    "HKG": "Hong Kong national rugby union team",
    "ZIM": "Zimbabwe national rugby union team",
}


def build_wikipedia_pool(short_code: str, nation: str, season: str = "2026") -> List[Player]:
    """Scrapes `short_code`'s Wikipedia "Current squad" section and returns
    a `Player` per entry - real stats where cross-referencing finds them
    (calibrated against the same cross-union reference pool as every
    rugbydata-sourced player), a union-strength-scaled position-archetype
    rating otherwise. Empty list if the page doesn't exist or doesn't have
    the expected squad template."""
    title = WIKI_UNION_PAGES.get(short_code)
    if not title:
        return []
    wikitext = fetch_wikitext(title)
    if not wikitext:
        return []
    entries = parse_current_squad(wikitext)

    # Deferred import: `pool_builder` only imports this module inside a
    # function body (not at module load time), so importing it back here
    # at call time is safe and doesn't create a real circular import.
    from .pool_builder import _global_reference_peer_proxies
    peer_proxies_by_position = _global_reference_peer_proxies(season)
    strength = UNION_STRENGTH.get(short_code, DEFAULT_UNION_STRENGTH)

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
        note = (
            "2026 Wikipedia squad listing; attributes from that person's real "
            "rugbydata career stats (cross-referenced by name)."
            if source == "wikipedia" else
            "2026 Wikipedia squad listing; no rugbydata history found for this "
            "name, so attributes are a generic position-archetype estimate, "
            "not a scouted rating."
        )
        pool.append(Player(
            name=full_name,
            nation=nation,
            natural_position=position,
            attributes=attrs,
            era="'26",
            notes=note,
            data_source=source,
        ))
    return pool
