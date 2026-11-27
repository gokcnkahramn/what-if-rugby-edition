"""Real, individual player ratings from the 2007 PC game EA Sports Rugby
08, sourced from a real, already-published fan extraction -
`marnoux/rugby08-player-explorer` (GitHub) - which itself reverse-engineers
the game's own `Data/data.gob` archive (EA BIG format, RefPack
compression) via its own `tools/bigdump.js`/`tools/build-data-gob.js`. We
do NOT re-run that extraction ourselves; we fetch the already-built,
already-published `players.json` (confirmed: ~1,904 players, 23 real raw
ratings each, built from the game's own database - see that repo's own
README "Rebuilding the data from the game" section) and cache it on disk,
same convention as every other Wikipedia-sourced pull in this project.

HONESTY NOTES (checked live against the real repo, not assumed):
- The repo has **no LICENSE file** - it's described as "an unofficial fan
  project, not affiliated with or endorsed by EA." Every player built from
  this source is tagged `data_source="rugby08_dataset"` (never silently
  folded into a `"historical_wikipedia"`/`"historical_archetype"` tag) so
  this provenance stays visible and inspectable, same transparency
  convention `EA_RATED_PLAYERS` already uses for its own (smaller,
  secondhand-article-sourced) Rugby 08 ratings.
- "Overall (OVR)" on that site is explicitly THEIR OWN computed estimate,
  not a game value - we never read or use their OVR; we read the 23 raw
  ratings directly and compute our own `rating_at`/`sub_ratings` as usual.
- Names in `players.json` are abbreviated (`"D.Hickie"`, not "Denis
  Hickie") - `_rugby08_key` below generates the same abbreviated form from
  a full name to match against it. A real, documented limitation: two
  different real players sharing one surname and first initial (rare, but
  real) will collide on this key - the first real match found wins, not
  silently disambiguated by magic. Nationality, when the caller has it, is
  used as a real tie-breaker among same-key candidates.
- Only 16 of the 23 real raw ratings have a clean, honest 1:1 equivalent in
  this project's own `Attributes` model (see `RATING_TO_ATTRIBUTE` below) -
  the other 7 (attack, ruck, hook, aggression, consistency, bravery,
  stamina - the last because this project's own `fitness` field already
  has a cleaner direct match at the game's own separate "fitness" rating)
  are genuinely ambiguous/non-equivalent and are deliberately left
  UNMAPPED rather than forced onto a field they don't really mean. A
  Rugby08-sourced player therefore starts from that position's own
  archetype baseline and only the 16 clean fields are overlaid with real
  game data - a genuine, honestly-scoped partial real signal, same
  "blend, don't force" spirit as `_proxy_attributes`'s own caps/tournament-
  stats nudges.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from ...models.attributes import Attributes
from ...models.position import Position
from .rugby_data_client import CACHE_DIR

PLAYERS_JSON_URL = "https://raw.githubusercontent.com/marnoux/rugby08-player-explorer/main/players.json"
DATASET_CACHE_DIR = CACHE_DIR / "rugby08_dataset"
PLAYERS_CACHE_FILE = DATASET_CACHE_DIR / "players.json"

# The 23 raw rating names, in the exact index order `players.json`'s own
# `"r"` array uses - read straight from `index.html`'s own `RATINGS` table
# on the live repo (`{k:'...', l:'...', ...}` entries, in file order).
RUGBY08_RATING_NAMES = [
    "attack", "defence", "speed", "accel", "agility", "handling", "pass", "kick",
    "gkick", "tackle", "strength", "ruck", "scrum", "hook", "lineout", "discipline",
    "aggression", "stamina", "consistency", "temperament", "creativity", "bravery", "fitness",
]

# Our `Attributes` field name -> Rugby08 rating NAME (not raw index, so this
# stays correct even if a future refresh of `RUGBY08_RATING_NAMES` reorders
# anything) - only the honest, clean 1:1 matches (see module docstring for
# why the other 7 raw ratings and 7 of our own fields are left unmapped).
RATING_TO_ATTRIBUTE: Dict[str, str] = {
    "pace": "speed",
    "acceleration": "accel",
    "agility": "agility",
    "handling": "handling",
    "passing": "pass",
    "kicking_game": "kick",
    "goal_kicking": "gkick",
    "strength": "strength",
    "scrummaging": "scrum",
    "lineout_jumping": "lineout",
    "discipline": "discipline",
    "fitness": "fitness",
    "tackle_technique": "defence",
    "tackling": "tackle",
    "composure": "temperament",
    "game_intelligence": "creativity",
}

_RATING_INDEX = {name: i for i, name in enumerate(RUGBY08_RATING_NAMES)}

_name_initial_surname_re = re.compile(r"^\s*(\S)\S*\s+.*?(\S+)\s*$")


def _rugby08_key(full_name: str) -> Optional[str]:
    """`"Denis Hickie"` -> `"d.hickie"` - the same abbreviated
    first-initial-plus-surname form `players.json`'s own `"name"` field
    uses (confirmed live: `"D.Hickie"`, `"S.Mertons"`). Returns `None` for
    a name with no real space-separated surname to key off."""
    parts = full_name.strip().split()
    if len(parts) < 2:
        return None
    first, last = parts[0], parts[-1]
    if not first or not last:
        return None
    return f"{first[0]}.{last}".lower()


_PLAYERS_BY_KEY: Optional[Dict[str, List[dict]]] = None


def _fetch_players_json() -> Optional[str]:
    if PLAYERS_CACHE_FILE.exists():
        return PLAYERS_CACHE_FILE.read_text(encoding="utf-8")
    try:
        req = urllib.request.Request(PLAYERS_JSON_URL, headers={"User-Agent": "what-if-rugby-edition-research"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[rugby08_dataset] could not fetch {PLAYERS_JSON_URL}: {e}")
        return None
    DATASET_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PLAYERS_CACHE_FILE.write_text(text, encoding="utf-8")
    return text


def _load_players_by_key() -> Dict[str, List[dict]]:
    global _PLAYERS_BY_KEY
    if _PLAYERS_BY_KEY is not None:
        return _PLAYERS_BY_KEY
    text = _fetch_players_json()
    by_key: Dict[str, List[dict]] = {}
    if text:
        try:
            records = json.loads(text)
        except json.JSONDecodeError:
            records = []
        for rec in records:
            name = rec.get("name")
            if not name:
                continue
            by_key.setdefault(name.strip().lower(), []).append(rec)
    _PLAYERS_BY_KEY = by_key
    return by_key


def lookup_rugby08_record(full_name: str, nation: Optional[str] = None) -> Optional[dict]:
    """Returns the raw `players.json` record for `full_name` (abbreviated-
    key match, see `_rugby08_key`), or `None` if no real match exists in
    the dataset. When more than one real player shares that exact
    abbreviated key, `nation` (if given) picks the one whose `"nat"` field
    matches; otherwise the first real match found is used - a documented,
    honest limitation (see module docstring), never a guess dressed up as
    certainty."""
    key = _rugby08_key(full_name)
    if key is None:
        return None
    candidates = _load_players_by_key().get(key)
    if not candidates:
        return None
    if nation:
        nation_lower = nation.strip().lower()
        for rec in candidates:
            if str(rec.get("nat", "")).strip().lower() == nation_lower:
                return rec
    return candidates[0]


def rugby08_attributes(position: Position, full_name: str, nation: Optional[str] = None) -> Optional[Attributes]:
    """Builds a real, partially-game-sourced `Attributes` for `full_name`:
    starts from `position`'s own archetype baseline (so every field this
    dataset doesn't cleanly cover still has a sensible value, never a raw
    zero/default), then overlays the 16 honestly-mapped fields
    (`RATING_TO_ATTRIBUTE`) with this player's REAL Rugby 08 ratings.
    Returns `None` if this exact player isn't in the dataset at all - the
    caller falls through to its own existing archetype/proxy chain
    unchanged, same contract every other `_cross_reference_attributes`
    tier already follows."""
    record = lookup_rugby08_record(full_name, nation)
    if record is None:
        return None
    ratings = record.get("r")
    if not isinstance(ratings, list) or len(ratings) != len(RUGBY08_RATING_NAMES):
        return None

    from .wikipedia_squad import _archetype_attributes
    attrs = _archetype_attributes(position)
    data = attrs.as_dict()
    for our_field, rating_name in RATING_TO_ATTRIBUTE.items():
        idx = _RATING_INDEX[rating_name]
        value = ratings[idx]
        if isinstance(value, (int, float)):
            data[our_field] = int(value)
    return Attributes.from_dict(data)
