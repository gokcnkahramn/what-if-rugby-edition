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
from dataclasses import replace
from pathlib import Path
from typing import List, Optional

import pandas as pd

from ...models.attributes import Attributes
from ...models.player import Player
from ...models.position import Position
from ..legends import CURATED_LEGENDS
from .attribute_mapping import (
    DEFAULT_UNION_STRENGTH,
    UNION_STRENGTH,
    map_stats_to_attributes,
    scale_to_union_strength,
)
from .rugby_data_client import CACHE_DIR, fetch_player_history, fetch_player_registry
from .union_registry import UNION_REGISTRY

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

# A real data-source gap, not a per-player data gap: every Wikipedia/
# historical squad source this project has (this file's own
# `POS_CODE_MAP` above, `invitational_squads.py`'s Lions/Pacific Islanders
# parsers) can only tell "prop"/"lock"/"wing"/"centre"/"flanker" apart as
# ONE generic jersey category, never which specific real-world slot
# (loosehead vs tighthead, left vs right wing, etc.) a given real player
# actually played - so every pool built this way ends up with real players
# ONLY at one of each pair's two `Position` enum values and genuinely NONE
# at the other (confirmed live: a real 2003 England RWC squad and Hong
# Kong's real current squad both came back with zero players at Tighthead
# Prop/Lock (5)/Openside Flanker/Outside Centre/Right Wing - not because
# nobody in the real squad played those roles, but because this mapping
# can't tell). The honest fix is NOT a new per-player "alternate position"
# field (nothing in any of these real sources ever says which specific
# slot a player preferred) - it's to stop silently excluding these real
# players from a slot they're exactly as plausible a candidate for as the
# slot they got mapped to. `with_twin_position_duplicates` adds a second
# `Player` entry (same real name/attributes/nation/everything, just
# `natural_position` set to the twin slot) for anyone mapped to one of
# these 5 "primary" positions - `Lineup.validate()` already rejects
# fielding the same real name in two slots at once (see its own "named in
# multiple positions" check), so this can never result in literally
# drafting one real person twice - it only ever makes them a real,
# draftable candidate for either slot, same "what if" freedom every other
# player in this project already has.
TWIN_POSITION = {
    Position.LOOSEHEAD_PROP: Position.TIGHTHEAD_PROP,
    Position.LOCK_1: Position.LOCK_2,
    Position.LEFT_WING: Position.RIGHT_WING,
    Position.INSIDE_CENTRE: Position.OUTSIDE_CENTRE,
    Position.BLINDSIDE_FLANKER: Position.OPENSIDE_FLANKER,
}


def with_twin_position_duplicates(pool: List[Player]) -> List[Player]:
    extra = [
        replace(p, natural_position=TWIN_POSITION[p.natural_position])
        for p in pool if p.natural_position in TWIN_POSITION
    ]
    return pool + extra

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
    heading_len = 13
    if start == -1:
        # Germany's page (confirmed live 2026-11-16) titles this section
        # plain "==Squad==" rather than "==Current squad==" - same
        # template underneath, just a shorter heading.
        start = wikitext.find("Squad==")
        heading_len = 7
    if start == -1:
        return []
    heading_match = re.search(r"\n==[^=]", wikitext[start + heading_len:])
    end = start + heading_len + heading_match.start() if heading_match else len(wikitext)
    section = wikitext[start:end]

    entries = []
    seen_names = set()
    for line in section.splitlines():
        if "nat rs player" not in line:
            continue
        pos_m = re.search(r"pos=\s*(\w+)", line)
        caps_m = re.search(r"\|caps=\s*(\d+)", line)
        name_m = re.search(r"name=\{\{sortname\|([^|}]+)\|([^|}]+)", line)
        if pos_m and name_m:
            first, last = name_m.group(1).strip(), name_m.group(2).strip()
        elif pos_m:
            # Some national-team pages (confirmed live for Switzerland/
            # Poland - a dated Rugby Europe Trophy squad listing on each)
            # spell the name as a plain `name=[[Full Name]]` (or
            # `name=[[Full Name]] ([[Captain (sports)|c]])`) wikilink
            # instead of the `{{sortname|First|Last}}` template - same
            # bracket-stripping convention `uncapped_pool._parse_senior_squad`
            # already uses for an equivalent plain-wikilink name. Split on
            # the LAST space for first/last (best-effort; a multi-word
            # surname is mis-split, same documented limitation as every
            # other name-parsing path in this project).
            plain_m = re.search(r"name=\s*\[\[([^\]|]+)", line)
            if not plain_m:
                continue
            full_name = plain_m.group(1).strip()
            if not full_name:
                continue
            parts = full_name.rsplit(" ", 1)
            if len(parts) == 2:
                first, last = parts
            else:
                first, last = "", parts[0]
        else:
            continue
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


_CURATED_LEGENDS_BY_NAME = {p.name.strip().lower(): p for p in CURATED_LEGENDS}
_ea_rated_players_by_name_cache: Optional[dict] = None


def _ea_rated_attributes(full_name: str) -> Optional[Attributes]:
    """Exact-name lookup into `legends.EA_RATED_PLAYERS` - a small, separate
    list derived from real, published Rugby 08 (EA Sports) in-game player
    ratings. Checked after `_curated_legend_attributes` (a hand-tuned
    Hall-of-Fame rating always wins a name collision) but before the
    rugbydata registry/proxy/archetype chain, since a real published EA
    rating is a stronger signal than an incidental stats cross-reference.
    Imports `legends.EA_RATED_PLAYERS` lazily (not at module load time) -
    `legends.py` itself builds that list's `Attributes` from this module's
    `_ARCHETYPES`, so a top-level import here would be circular."""
    global _ea_rated_players_by_name_cache
    if _ea_rated_players_by_name_cache is None:
        from ..legends import EA_RATED_PLAYERS
        _ea_rated_players_by_name_cache = {
            p.name.strip().lower(): p for p in EA_RATED_PLAYERS
        }
    player = _ea_rated_players_by_name_cache.get(full_name.strip().lower())
    return player.attributes if player is not None else None


def _curated_legend_attributes(full_name: str) -> Optional[Attributes]:
    """Exact-name lookup (same convention as the registry lookup below:
    exact match first) into `legends.CURATED_LEGENDS` - the small, hand-
    tuned ~30-entry list, NOT `get_all_legends()`'s larger scraped-archetype
    set (those are no better than our own archetype fallback). A real
    Hall-of-Famer who also turns up in a historical/current squad should
    get their hand-tuned, historically-justified rating instead of a flat
    archetype or an unrelated-career stats cross-reference."""
    legend = _CURATED_LEGENDS_BY_NAME.get(full_name.strip().lower())
    return legend.attributes if legend is not None else None


def _cross_reference_attributes(
    full_name: str, peer_proxies: Optional[dict] = None,
    position: Optional[Position] = None, nation: Optional[str] = None,
) -> tuple[Attributes, str]:
    """Looks `full_name` up, in priority order: (1) `legends.CURATED_LEGENDS`'
    hand-tuned entries (exact name match) - a real Hall-of-Famer's
    historically-justified rating always beats a generic archetype or an
    incidental stats cross-reference; (2) `legends.EA_RATED_PLAYERS` (a
    small, secondhand-article-sourced Rugby 08 OVR conversion); (3) the
    much richer real `rugby08_dataset` (1,904 real players, 23 real raw
    ratings each, see that module's own docstring) - checked AFTER the
    hand-curated tiers above (a real Hall-of-Famer's own curated rating
    still wins a collision) but BEFORE the generic rugbydata registry,
    since a real, individually-attributed 2007 game rating is a stronger
    signal for a historical (pre-2018) player than an incidental modern
    stats cross-reference; only reachable when the caller passes
    `position` (needed to build the archetype baseline this tier overlays
    real ratings onto - omitted callers simply skip this tier, same as
    before this tier existed); (4) rugbydata's global player registry,
    aggregating that person's real career stats if found; (5) None,
    meaning no usable match - caller supplies the position archetype.
    `peer_proxies` (see `pool_builder._global_reference_peer_proxies`) is
    passed straight through to `map_stats_to_attributes` so a registry-
    sourced rating is calibrated against the same cross-union reference
    pool as every rugbydata-sourced player, not scored in isolation -
    curated-legends/EA/Rugby08-dataset attributes are already final and
    skip that step."""
    legend_attrs = _curated_legend_attributes(full_name)
    if legend_attrs is not None:
        return legend_attrs, "legends_curated"

    ea_attrs = _ea_rated_attributes(full_name)
    if ea_attrs is not None:
        return ea_attrs, "ea_rugby08_rating"

    if position is not None:
        from .rugby08_dataset import rugby08_attributes
        r08_attrs = rugby08_attributes(position, full_name, nation=nation)
        if r08_attrs is not None:
            return r08_attrs, "rugby08_dataset"

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


def describe_attribute_source(source: str, *, historical: bool = False) -> Optional[str]:
    """The shared `notes` fragment for the two source tiers whose wording
    is identical (or near-identical) across every `build_*_pool` call site
    - `legends_curated`/`ea_rugby08_rating` - since `_cross_reference_attributes`
    is the one place that owns the `source` string vocabulary. Returns
    `None` for any other source: the `wikipedia`/`historical_proxy`/
    archetype branches each make a genuinely different claim depending on
    whether this is a current-squad, historical-tournament, or invitational
    pull, so those stay as each call site's own wording rather than being
    forced through one shared string. `historical=True` drops the trailing
    "not a scouted rating of our own" clause the current-squad (2026)
    wording uses, matching the shorter phrasing historical pulls used
    before this helper existed."""
    if source == "legends_curated":
        return (
            "World Rugby Hall of Fame - hand-tuned curated rating from "
            "legends.CURATED_LEGENDS, not a Wikipedia/archetype estimate."
        )
    if source == "ea_rugby08_rating":
        base = (
            "Real, published Rugby 08 (EA Sports) in-game player rating - "
            "legends.EA_RATED_PLAYERS, converted via a documented heuristic"
        )
        return base + "." if historical else base + ", not a scouted rating of our own."
    return None


# Bounded nudge caps (deliberately small - see plan section 17: the explicit
# goal is "prevent anyone from becoming overpowered," not to approximate a
# real scouted rating from thin proxy signal).
_MAX_CAPS_NUDGE = 6
_MAX_STATS_NUDGE = 6


def _proxy_attributes(position: Position, caps: Optional[int] = None,
                       tournament_stats: Optional[dict] = None) -> tuple[Attributes, str]:
    """Starts from the flat `_archetype_attributes(position)` baseline and
    applies up to two small, bounded nudges when there's real (if coarse)
    signal to justify them - used for pre-2018 historical players who have
    no rugbydata box-score history at all, so would otherwise be byte-
    identical to every other player at their position:

    1. A caps-based "trusted with real selection" experience nudge - real
       international caps at the time, bounded to `_MAX_CAPS_NUDGE`.
    2. A real tournament-output nudge, only on an actual
       `parse_rwc_tournament_stats` match for this exact player in this
       exact tournament - points nudge goal-kicking/kicking game, tries
       nudge pace/footwork/handling, each bounded to `_MAX_STATS_NUDGE`.

    Returns `(attributes, data_source)`: `data_source` is
    `"historical_proxy"` if either nudge actually fired (real caps>0 or a
    real tournament-stats match), else the unchanged `"historical_archetype"`
    - a player with genuinely zero real signal gets EXACTLY the old flat
    archetype value, no regression."""
    base = _archetype_attributes(position)
    caps_nudge = min(_MAX_CAPS_NUDGE, (caps or 0) // 15)
    stats_nudge_tries = 0
    stats_nudge_points = 0
    if tournament_stats:
        tries = tournament_stats.get("tries") or 0
        points = tournament_stats.get("points") or 0
        stats_nudge_tries = min(_MAX_STATS_NUDGE, tries * 2)
        stats_nudge_points = min(_MAX_STATS_NUDGE, points // 20)

    if not caps_nudge and not stats_nudge_tries and not stats_nudge_points:
        return base, "historical_archetype"

    data = base.as_dict()
    for attr in ("fitness", "game_intelligence", "discipline"):
        data[attr] = data[attr] + caps_nudge
    for attr in ("goal_kicking", "kicking_game"):
        data[attr] = data[attr] + stats_nudge_points
    for attr in ("pace", "footwork", "handling"):
        data[attr] = data[attr] + stats_nudge_tries
    return Attributes.from_dict(data), "historical_proxy"


# code -> Wikipedia page title. Most unions follow "<Nation> national rugby
# union team"; a few need an explicit override (checked live - some redirect
# or use a different page structure and are better skipped than guessed at).
# Derived from `union_registry.UNION_REGISTRY` (the single source of truth
# for a union's Wikipedia squad-page title, among other things) - same
# contents as the hand-written dict this replaced.
WIKI_UNION_PAGES = {
    e.code: e.wiki_page_title for e in UNION_REGISTRY
    if e.wiki_page_title and e.needs_wiki_squad_fallback
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
        full_name = f"{entry['first']} {entry['last']}".strip()
        attrs, source = _cross_reference_attributes(
            full_name, peer_proxies=peer_proxies_by_position.get(position)
        )
        if attrs is None:
            attrs, source = _proxy_attributes(position, entry.get("caps"))
        if source not in ("legends_curated", "ea_rugby08_rating"):
            attrs = scale_to_union_strength(attrs, strength)
        note = describe_attribute_source(source) or (
            "2026 Wikipedia squad listing; attributes from that person's real "
            "rugbydata career stats (cross-referenced by name)."
            if source == "wikipedia" else
            "2026 Wikipedia squad listing; real caps parsed from Wikipedia gave "
            "a small, bounded experience nudge off the generic position "
            "archetype - not a scouted rating."
            if source == "historical_proxy" else
            "2026 Wikipedia squad listing; no rugbydata history found for this "
            "name, so attributes are a generic position-archetype estimate, "
            "not a scouted rating."
        )
        pool.append(Player(
            name=full_name,
            nation=nation,
            natural_position=position,
            attributes=attrs,
            caps=entry.get("caps"),
            era="'26",
            notes=note,
            data_source=source,
        ))
    return with_twin_position_duplicates(pool)
