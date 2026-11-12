"""Builds a capped national player pool for one union from rugbydata.

Pipeline: team match-log (-> which players featured in `season`) -> each
player's full match history (-> filter back down to just that union's
`season` rows) -> aggregate box-score stats over those caps -> map to
`Attributes`.

Every player ends up with `era` set to the two-digit year (e.g. `"'26"`,
`"'23"`) and `data_source="rugbydata"`, same convention as the hand-entered
historical players in `sample_players.py`. Defaults to 2026 so existing
callers (`build_union_pool("ITA")`) are unaffected, but any season the
dataset covers (2022-2026, per the competition registry) can be requested.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Optional

import pandas as pd

from ...models.attributes import Attributes
from ...models.player import Player
from .attribute_mapping import (
    DEFAULT_UNION_STRENGTH,
    UNION_STRENGTH,
    build_peer_proxies,
    map_stats_to_attributes,
    scale_to_union_strength,
)
from .position_mapping import map_raw_position
from .rugby_data_client import (
    INTERNATIONAL_COMPETITIONS,
    fetch_player_history,
    fetch_team_matches,
)

DEFAULT_SEASON = "2026"

# Tier 1 union -> (dataset team_id, dataset team-name, display nation name).
# Team names/ids resolved by scanning rugbydata's 2026 fixture list.
TIER1_TEAM_IDS = {
    "ENG": ("f60f757d", "England", "England"),
    "FRA": ("67d88578", "France", "France"),
    "IRE": ("165b36e5", "Ireland", "Ireland"),
    "SCO": ("4409215c", "Scotland", "Scotland"),
    "WAL": ("094dae60", "Wales", "Wales"),
    "ITA": ("d0cffe5e", "Italy", "Italy"),
    "NZL": ("d75e45cc", "New Zealand", "New Zealand"),
    "AUS": ("b904fef9", "Australia", "Australia"),
    "RSA": ("9b93d911", "South Africa", "South Africa"),
    "ARG": ("11392c0c", "Argentina", "Argentina"),
    "JPN": ("f97333f3", "Japan", "Japan"),
    "FIJ": ("3a1983b3", "Fiji", "Fiji"),
}

# Tier 2 unions - relevant for the 2027 Rugby World Cup pools. Rugby Europe
# sides (GEO/ROU/ESP/POR) have 2026 rows already; the Pacific/Americas sides
# don't yet (their most recent recorded internationals are 2024-2025), so
# they rely on the latest-available-season fallback in `build_union_pool`.
TIER2_TEAM_IDS = {
    "GEO": ("9b13901b", "Georgia", "Georgia"),
    "ROU": ("931e1c23", "Romania", "Romania"),
    "ESP": ("219a6262", "Spain", "Spain"),
    "POR": ("5149996e", "Portugal", "Portugal"),
    "SAM": ("23778ceb", "Samoa", "Samoa"),
    "TGA": ("be110f80", "Tonga", "Tonga"),
    "USA": ("5865faf2", "Usa", "USA"),  # dataset's own team-name spelling is "Usa"
    "CAN": ("1039f7c4", "Canada", "Canada"),
    "URU": ("95ba991c", "Uruguay", "Uruguay"),
    "CHI": ("53ea6ee8", "Chile", "Chile"),
    "NAM": ("03b35a84", "Namibia", "Namibia"),
}

ALL_TEAM_IDS = {**TIER1_TEAM_IDS, **TIER2_TEAM_IDS}

# Unions with no rugbydata team_id at all (not found in the dataset under
# any name) but needed for the 2027 Rugby World Cup draw - display name
# only, since there's no team-level box score to pull from; these are
# Wikipedia-only (see `build_union_pool_2026`'s fallback below).
WIKI_ONLY_NATIONS = {
    "HKG": "Hong Kong",
    "ZIM": "Zimbabwe",
}


#: Union short code -> display nation name, for every pool `POOLS` can
#: build (Tier 1 + Tier 2 + the Wikipedia-only additions), plus the
#: Barbarians. Single source of truth so the interactive CLI, the web UI,
#: and anything else that needs "what code is this nation" don't each keep
#: their own copy.
NATION_DISPLAY = {code: nation for code, (_, _, nation) in ALL_TEAM_IDS.items()}
NATION_DISPLAY.update(WIKI_ONLY_NATIONS)
NATION_DISPLAY["BAR"] = "Barbarians"
NATION_TO_CODE = {nation: code for code, nation in NATION_DISPLAY.items()}


def _era_suffix(season: str) -> str:
    return f"'{season[-2:]}"


def _collect_season_player_ids(team_id: str, season: str) -> List[str]:
    matches = fetch_team_matches(team_id)
    if matches is None or matches.empty:
        return []
    rows = matches[matches["game_date"].astype(str).str.startswith(season)]
    ids: set = set()
    for players in rows.get("players", []):
        if players is None:
            continue
        ids.update(list(players))
    return sorted(ids)


def _aggregate_caps(history: pd.DataFrame, nation: str, season: str) -> Optional[tuple]:
    caps = history[
        (history["team"] == nation)
        & history["game_date"].astype(str).str.startswith(season)
        & history["competition_id"].isin(INTERNATIONAL_COMPETITIONS)
    ]
    if caps.empty:
        return None

    numeric_cols = [
        c for c in caps.columns
        if pd.api.types.is_numeric_dtype(caps[c]) and c not in ("weight_kg", "height_cm")
    ]
    summed = caps[numeric_cols].sum(numeric_only=True)
    if "kick_percent_success" in caps.columns:
        summed["kick_percent_success"] = caps["kick_percent_success"].mean()

    raw_positions = [p for p in caps["position"].tolist() if map_raw_position(p)]
    if not raw_positions:
        return None
    primary_raw = Counter(raw_positions).most_common(1)[0][0]
    position = map_raw_position(primary_raw)

    return summed, len(caps), position


def _latest_available_season(team_id: str) -> Optional[str]:
    """Most recent year this team has a match with an actual player-id list
    for, dataset-wide. Many smaller unions' matches have an empty `players`
    column (no roster tracked at that granularity - confirmed e.g. for every
    Rugby Europe Championship fixture), so a plain "latest match date"
    would often point at a season with no usable per-player data at all."""
    matches = fetch_team_matches(team_id)
    if matches is None or matches.empty:
        return None
    has_players = matches["players"].apply(lambda x: x is not None and len(x) > 0)
    dates = matches.loc[has_players, "game_date"].astype(str)
    years = sorted({d[:4] for d in dates if len(d) >= 4})
    return years[-1] if years else None


def _collect_raw_entries(short_code: str, season: str, _allow_fallback: bool = True) -> dict:
    """First pass of `build_union_pool`: every capped player's raw aggregated
    stats for one union/season, keyed by name - `{name: (caps, stats,
    position)}`. Split out so the same raw collection can feed both one
    union's own pool AND the cross-union reference pool used to calibrate
    percentile scaling (see `_global_reference_peer_proxies`)."""
    team_id, dataset_name, _nation = ALL_TEAM_IDS[short_code]

    player_ids = _collect_season_player_ids(team_id, season)
    if not player_ids and _allow_fallback:
        latest = _latest_available_season(team_id)
        if latest and latest != season:
            return _collect_raw_entries(short_code, latest, _allow_fallback=False)

    # Dataset data-quality note: the same real person occasionally gets two
    # different player_ids (confirmed e.g. for Wales's Ellis Mee: one id with
    # 6 caps, another with 1). Build by name and keep whichever id has more
    # caps, so a lineup never ends up with the same player "twice" under two
    # different records.
    best_by_name: dict = {}

    for pid in player_ids:
        history = fetch_player_history(pid)
        if history is None or history.empty:
            continue
        aggregated = _aggregate_caps(history, dataset_name, season)
        if aggregated is None:
            continue
        stats, caps, position = aggregated
        if position is None:
            continue

        name_rows = history[history["team"] == dataset_name]
        name = name_rows["name"].iloc[0] if not name_rows.empty else pid

        existing = best_by_name.get(name)
        if existing is not None and existing[0] >= caps:
            continue
        best_by_name[name] = (caps, stats, position)

    return best_by_name


# Cross-union reference pools, keyed by season: {Position: peer_proxies}.
# Built once per season (network-heavy the first time; every union it pulls
# from is disk-cached afterwards) and reused for every union's percentile
# scaling, instead of each union percentile-ranking only against its own
# (sometimes tiny) pool.
_GLOBAL_REFERENCE_CACHE: dict = {}


def _global_reference_peer_proxies(season: str) -> dict:
    """Why this exists: percentile-ranking a player against only their own
    union's pool has no *absolute* calibration - the weakest player in an
    elite 18-player All Blacks pool still gets rank-forced down near the
    bottom of the 1-100 scale, even though in real-world terms they're
    still a very good international, while every union's own average
    player lands near the same ~60 regardless of whether that union is
    genuinely elite or not. Ranking against ALL unions' real rugbydata
    players at that position instead keeps the real gap between, say, an
    All Black lock and a weaker nation's lock - a mediocre player for a
    small union should score lower than a depth player at a rugby
    superpower, not the same."""
    if season in _GLOBAL_REFERENCE_CACHE:
        return _GLOBAL_REFERENCE_CACHE[season]

    by_position: dict = {}
    for code in ALL_TEAM_IDS:
        entries = _collect_raw_entries(code, season)
        for caps, stats, position in entries.values():
            by_position.setdefault(position, []).append((stats, caps))

    result = {position: build_peer_proxies(entries) for position, entries in by_position.items()}
    _GLOBAL_REFERENCE_CACHE[season] = result
    return result


def build_union_pool(short_code: str, season: str = DEFAULT_SEASON, _allow_fallback: bool = True) -> List[Player]:
    """Return every player capped for `short_code`'s union in `season`.

    If the dataset has no rows at all for that union in `season` (common for
    smaller unions whose latest fixtures haven't been scraped yet), this
    automatically retries with the most recent season the union *does* have
    data for, and the resulting players' `era` reflects that actual season
    - never silently mislabeled as `season`.
    """
    if short_code not in ALL_TEAM_IDS:
        raise ValueError(f"Unknown union short code: {short_code}")
    _team_id, _dataset_name, nation = ALL_TEAM_IDS[short_code]

    best_by_name = _collect_raw_entries(short_code, season, _allow_fallback=_allow_fallback)
    era = _era_suffix(season)

    # Percentile-normalize each attribute against the cross-union reference
    # pool for that position (e.g. "better tackler than 80% of real-world
    # international locks"), not a fixed breakpoint chosen in the abstract,
    # and not just this union's own (possibly tiny, possibly elite) pool -
    # see `_global_reference_peer_proxies` for why that matters.
    peer_proxies_by_position = _global_reference_peer_proxies(season)
    strength = UNION_STRENGTH.get(short_code, DEFAULT_UNION_STRENGTH)

    pool: List[Player] = []
    for name, (caps, stats, position) in best_by_name.items():
        attrs = map_stats_to_attributes(stats, caps, peer_proxies=peer_proxies_by_position.get(position))
        attrs = scale_to_union_strength(attrs, strength)
        pool.append(
            Player(
                name=name,
                nation=nation,
                natural_position=position,
                attributes=attrs,
                era=era,
                notes=f"{caps} cap(s) for {nation} in {season} (rugbydata-derived ratings - approximate).",
                data_source="rugbydata",
            )
        )

    return pool


def build_union_pool_2026(short_code: str) -> List[Player]:
    """The best available 2026 pool for `short_code`: real rugbydata 2026
    caps (whichever players have them) topped up with the rest of that
    union's actual 2026 Wikipedia-listed squad (see `wikipedia_squad.py`)
    for players rugbydata has no 2026 box score for. A name already covered
    by real rugbydata stats is never overwritten by its (weaker) Wikipedia
    counterpart.

    This is specifically for 2026 - for any other season just call
    `build_union_pool(code, season=...)` directly.
    """
    from .wikipedia_squad import WIKI_UNION_PAGES, build_wikipedia_pool

    if short_code in WIKI_ONLY_NATIONS:
        return build_wikipedia_pool(short_code, WIKI_ONLY_NATIONS[short_code])

    real_pool = build_union_pool(short_code, season="2026", _allow_fallback=False)
    if short_code not in WIKI_UNION_PAGES:
        return real_pool

    nation = ALL_TEAM_IDS[short_code][2]
    wiki_pool = build_wikipedia_pool(short_code, nation)

    covered_names = {p.name.strip().lower() for p in real_pool}
    merged = list(real_pool)
    for player in wiki_pool:
        if player.name.strip().lower() in covered_names:
            continue
        merged.append(player)
    return merged
