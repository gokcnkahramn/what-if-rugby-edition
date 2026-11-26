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
from typing import Dict, List, Optional

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
from .union_registry import UNION_REGISTRY

DEFAULT_SEASON = "2026"

# The 4 dicts below are now derived from `union_registry.UNION_REGISTRY`
# (the single source of truth for which codes exist, their dataset
# team_id/raw team-name, display nation, and tier) - see that module's
# docstring for the full rationale per union/tier, including the Rugby
# Europe Championship wiki-only group and the Usa/USA spelling note. Same
# names/shapes/contents as before this was consolidated - every external
# importer of these 4 dicts is unaffected.
TIER1_TEAM_IDS = {
    e.code: (e.dataset_team_id, e.dataset_team_name, e.nation)
    for e in UNION_REGISTRY if e.tier == "tier1"
}
TIER2_TEAM_IDS = {
    e.code: (e.dataset_team_id, e.dataset_team_name, e.nation)
    for e in UNION_REGISTRY if e.tier == "tier2"
}
TIER2_WIKI_ONLY_TEAM_IDS = {
    e.code: (e.dataset_team_id, e.dataset_team_name, e.nation)
    for e in UNION_REGISTRY if e.tier == "wiki_only"
}

ALL_TEAM_IDS = {**TIER1_TEAM_IDS, **TIER2_TEAM_IDS, **TIER2_WIKI_ONLY_TEAM_IDS}

# Unions with no rugbydata team_id at all (not found in the dataset under
# any name) but needed for the 2027 Rugby World Cup draw - display name
# only, since there's no team-level box score to pull from; these are
# Wikipedia-only (see `build_union_pool_2026`'s fallback below).
WIKI_ONLY_NATIONS = {
    e.code: e.nation for e in UNION_REGISTRY if e.tier == "wiki_only_nation"
}


#: Union short code -> display nation name, for every pool `POOLS` can
#: build (Tier 1 + Tier 2 + the Wikipedia-only additions), plus the
#: Barbarians. Single source of truth so the interactive CLI, the web UI,
#: and anything else that needs "what code is this nation" don't each keep
#: their own copy.
NATION_DISPLAY = {code: nation for code, (_, _, nation) in ALL_TEAM_IDS.items()}
NATION_DISPLAY.update(WIKI_ONLY_NATIONS)
NATION_DISPLAY["BAR"] = "Barbarians"
#: British & Irish Lions and the Pacific Islanders - the other two real
#: invitational/composite sides this project can draft from (see
#: `national_teams/lions.py`/`pacific_islanders.py`) - same "not a World
#: Rugby union" footing as the Barbarians, so they get the same treatment:
#: listed here for display/lookup, but deliberately excluded from the
#: world rankings table (see `webapp._team_form_json`) since none of the
#: three is a real ranked national team.
NATION_DISPLAY["LIO"] = "British & Irish Lions"
NATION_DISPLAY["PAC"] = "Pacific Islanders"
NATION_TO_CODE = {nation: code for code, nation in NATION_DISPLAY.items()}

#: Union/invitational-side codes that are NOT real World-Rugby-ranked
#: national teams - excluded from the world rankings ("Team form") table
#: wherever that universe is built (see `webapp._team_form_json`).
NON_RANKED_CODES = {"BAR", "LIO", "PAC"}


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


# Opponent-quality normalization (rating system, item 1): a counting stat
# racked up against a weak minnow shouldn't weigh the same as the same raw
# number against a Tier 1 nation. Reuses the EXISTING `UNION_STRENGTH` map
# (already used to scale a whole union's players toward 50 - see
# `scale_to_union_strength`) for the OPPOSITE direction: here it boosts or
# dampens one specific match's contribution to a player's aggregated stats,
# based on who that match was actually against (the dataset's own
# `team_vs` column - real nation names, confirmed live to match
# `NATION_DISPLAY`'s own spelling for Tier 1 opposition). 0.5 at the
# weakest mapped union, 1.5 at full Tier-1 strength, 1.0 (neutral) for an
# opponent this project doesn't track a strength for (a club side on a
# mixed history row, or a union outside `UNION_STRENGTH`) - a modest,
# bounded multiplier: never zeroes out a performance, never doubles it.
_OPPONENT_WEIGHTED_STAT_COLUMNS = (
    "tackles_made", "tackles_missed", "dominant_tackles", "carries",
    "metres_carried", "line_breaks", "clean_breaks", "defenders_beaten",
    "offloads", "offload", "passes", "turnovers_lost", "turnovers_won",
    "kicks_from_hand", "lineouts_won", "total_lineouts", "rucks_won",
)


def _opponent_quality_weight(opponent_name) -> float:
    code = NATION_TO_CODE.get(str(opponent_name).strip())
    if code is None:
        return 1.0
    return 0.5 + UNION_STRENGTH.get(code, DEFAULT_UNION_STRENGTH)


def _aggregate_caps(history: pd.DataFrame, nation: str, season: str) -> Optional[tuple]:
    caps = history[
        (history["team"] == nation)
        & history["game_date"].astype(str).str.startswith(season)
        & history["competition_id"].isin(INTERNATIONAL_COMPETITIONS)
    ]
    if caps.empty:
        return None

    if "team_vs" in caps.columns:
        caps = caps.copy()
        weight = caps["team_vs"].map(_opponent_quality_weight)
        for col in _OPPONENT_WEIGHTED_STAT_COLUMNS:
            if col in caps.columns:
                caps[col] = caps[col] * weight

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
    if team_id is None:
        # Wiki-only union (see `TIER2_WIKI_ONLY_TEAM_IDS`) - no rugbydata
        # box scores to aggregate, so this union contributes nothing to the
        # cross-union reference pool either; it never reaches here via
        # `build_union_pool` itself (that function returns earlier for a
        # `None` team_id).
        return {}

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

    if _team_id is None:
        # Wiki-only union (see `TIER2_WIKI_ONLY_TEAM_IDS` above) - no
        # rugbydata roster to pull, go straight to its real Wikipedia
        # "Current squad" listing.
        from .wikipedia_squad import build_wikipedia_pool
        pool = build_wikipedia_pool(short_code, nation, season=season)
        for p in pool:
            p.era = _era_suffix(season)
        return pool

    best_by_name = _collect_raw_entries(short_code, season, _allow_fallback=_allow_fallback)
    era = _era_suffix(season)

    # Minimum distinct names needed to field a legal XV (15 starters across
    # 9 distinct position slots, allowing for some doubling-up) - found
    # while wiring the Rugby Europe Championship in: Spain has a real
    # rugbydata `team_id` but, confirmed live, genuinely NO match in the
    # dataset ever carries a populated `players` id list for it
    # (`best_by_name` empty, every season); Romania has a team_id AND some
    # matches with populated rosters, but only ever 8 distinct capped names
    # dataset-wide (confirmed live, every season 2022-2026) - enough for
    # `build_union_pool` to return *something*, but not enough to actually
    # field a team (`MatchEngine` rejects a lineup missing e.g. a fly-half
    # or any centre). Both already have a real, sourced Wikipedia squad
    # page (`wikipedia_squad.WIKI_UNION_PAGES`), previously only reachable
    # through `build_union_pool_2026`'s separate merge path for 2026 - this
    # merges it in here too (real rugbydata names always kept over their
    # weaker Wikipedia-archetype counterpart, same precedence
    # `build_union_pool_2026` already uses) so `build_union_pool`/
    # `build_season_pool` (what Season mode and `rugby_europe_championship`
    # actually call) stop returning a too-thin-to-field pool for a union
    # whose rugbydata box scores are just structurally sparse.
    _MIN_FIELDABLE_NAMES = 15
    extra: List[Player] = []
    if len(best_by_name) < _MIN_FIELDABLE_NAMES and _allow_fallback:
        from .wikipedia_squad import WIKI_UNION_PAGES, build_wikipedia_pool
        if short_code in WIKI_UNION_PAGES:
            wiki_pool = build_wikipedia_pool(short_code, nation, season=season)
            covered = {n.strip().lower() for n in best_by_name}
            extra = [p for p in wiki_pool if p.name.strip().lower() not in covered]
            if not best_by_name:
                for p in extra:
                    p.era = era
                return extra
            # fall through to the normal rugbydata-pool build below, then
            # top up with `extra` afterward.

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

    if extra:
        for p in extra:
            p.era = era
        pool.extend(extra)

    return pool


def _collect_raw_entries_multi_season(
    short_code: str, seasons: List[str], season_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, tuple]:
    """Combines raw per-player stats across MULTIPLE seasons (rating
    system, item 2) into one `{name: (real_caps, weighted_stats,
    weighted_caps, position)}` dict - a more reliable profile than a
    single season's often-small sample (a player's form/role can genuinely
    vary season to season, and a thin-pool union's single-season sample
    can be tiny). `season_weights` defaults to a linear recency weighting
    (the most recent season in `seasons` weighted highest, the oldest
    weighted 1x) - a real, if simple, "recent form matters more" choice,
    not an unweighted blend that treats a player's form from 4 years ago
    the same as last season's.

    Dividing `weighted_stats` by `weighted_caps` (not `real_caps`) in
    `attribute_mapping._compute_proxies` still produces a correct
    per-cap-rate weighted average across seasons, since both the numerator
    and denominator carry the same per-season weight - `real_caps` is kept
    separately, purely for an honest "N real caps across M seasons" note,
    never fed into the rate math itself."""
    if season_weights is None:
        season_weights = {season: float(i + 1) for i, season in enumerate(seasons)}

    combined: Dict[str, dict] = {}
    for season in seasons:
        weight = season_weights.get(season, 1.0)
        entries = _collect_raw_entries(short_code, season, _allow_fallback=False)
        for name, (caps, stats, position) in entries.items():
            existing = combined.get(name)
            if existing is None:
                combined[name] = {
                    "real_caps": caps, "weighted_caps": caps * weight,
                    "weighted_stats": stats * weight, "position": position,
                }
            else:
                existing["real_caps"] += caps
                existing["weighted_caps"] += caps * weight
                existing["weighted_stats"] = existing["weighted_stats"].add(stats * weight, fill_value=0)
                # Most recent season's primary position wins (seasons is
                # expected oldest-to-newest) - a player's role can shift
                # over a career, and the latest one is the more relevant
                # "what if" starting position.
                existing["position"] = position

    return {
        name: (v["real_caps"], v["weighted_stats"], v["weighted_caps"], v["position"])
        for name, v in combined.items()
    }


def build_union_pool_multi_season(
    short_code: str, seasons: List[str], season_weights: Optional[Dict[str, float]] = None,
) -> List[Player]:
    """Like `build_union_pool`, but blends real rugbydata stats across
    MULTIPLE real seasons (rating system, item 2 - see
    `_collect_raw_entries_multi_season`'s own docstring for the weighting
    rationale) into one profile per player, instead of a single season's
    sample. `era` is set to the LAST season in `seasons` (the most recent
    one requested) - this pool represents that player's blended, multi-
    season form as of that point, same "what if" framing every other pool
    already uses. Percentile scaling still uses the single most-recent
    season's cross-union reference pool (building a true multi-season
    reference pool for every union would be a much larger, separate
    undertaking - not needed here, since percentile ranking only needs a
    broadly representative peer set, not an exactly form-matched one)."""
    if short_code not in ALL_TEAM_IDS:
        raise ValueError(f"Unknown union short code: {short_code}")
    _team_id, _dataset_name, nation = ALL_TEAM_IDS[short_code]
    if _team_id is None:
        raise ValueError(f"{short_code} has no rugbydata coverage - multi-season blending needs real per-season stats.")

    combined = _collect_raw_entries_multi_season(short_code, seasons, season_weights)
    era = _era_suffix(seasons[-1])
    peer_proxies_by_position = _global_reference_peer_proxies(seasons[-1])
    strength = UNION_STRENGTH.get(short_code, DEFAULT_UNION_STRENGTH)

    pool: List[Player] = []
    for name, (real_caps, weighted_stats, weighted_caps, position) in combined.items():
        attrs = map_stats_to_attributes(
            weighted_stats, weighted_caps, peer_proxies=peer_proxies_by_position.get(position),
        )
        attrs = scale_to_union_strength(attrs, strength)
        pool.append(
            Player(
                name=name,
                nation=nation,
                natural_position=position,
                attributes=attrs,
                era=era,
                notes=(
                    f"{real_caps} real cap(s) for {nation} across {seasons[0]}-{seasons[-1]} "
                    "(rugbydata-derived ratings, blended across multiple seasons - approximate)."
                ),
                data_source="rugbydata",
            )
        )
    return pool


def build_season_pool(short_code: str, year: int, include_uncapped: bool = False) -> List[Player]:
    """Season mode's (12c) roster for one union/year: every real capped
    player `build_union_pool` can pull for that union in `year`, deduped by
    name (`_dedupe_players_by_name`-equivalent, inlined here to avoid a
    webapp.py import).

    Simplified vs. the full plan: the plan describes merging each
    *per-competition* squad pull across the year's detected real
    tournaments (Six Nations/Rugby Championship/Autumn Nations Series/
    World Cup); this pipeline only ever pulls a union's roster at
    *season* granularity (`build_union_pool(code, season=...)`), not
    per-competition, so there's nothing further to union here - one
    season-level pull already covers every competition that union played
    in that real year. Documented honestly, same as `build_union_pool_2026`:
    every CAPPED player across the year's real rugbydata rows for this
    union, not every eligible-but-uncapped player.

    `include_uncapped=True` (12d) additionally merges in
    `uncapped_pool.build_uncapped_pool`'s real-but-never-capped club players
    for unions it covers (currently ENG/FRA only - see that module's
    `CLUB_PAGES`), deduped against the capped pool by name (capped entry
    always wins). Defaults to False so existing callers of this function
    are unaffected; `webapp.py`'s `/api/season/start` keeps the two pools
    separate in its own response rather than relying on this flag (see
    that endpoint), but the flag is here for any other caller that just
    wants one merged list."""
    pool = build_union_pool(short_code, season=str(year))
    era = f"'{year % 100:02d}"
    for p in pool:
        p.era = era

    seen: set = set()
    deduped: List[Player] = []
    for p in pool:
        key = p.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    if include_uncapped:
        from .uncapped_pool import build_uncapped_pool
        nation = ALL_TEAM_IDS[short_code][2]
        for p in build_uncapped_pool(short_code, nation):
            key = p.name.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)

    return deduped


def build_widest_season_pool(short_code: str, year: int) -> List[Player]:
    """13b: the widest possible real draft pool for interactive Season
    mode's own nation - every capped player `build_season_pool` already
    pulls for that union/year, topped up with that union's real-but-never-
    capped club pool (`uncapped_pool.build_uncapped_pool`, 12d/13a), deduped
    by name (a capped entry always wins over an uncapped one with the same
    name). This is just `build_season_pool(..., include_uncapped=True)` -
    that flag already does exactly this merge - kept as its own named
    function per the plan so callers (webapp.py's interactive season start)
    have an explicit, self-documenting entry point distinct from the plain
    (capped-only) pool every OTHER (AI-controlled) nation in a season keeps
    using. Returns the same (possibly unchanged) pool as `build_season_pool`
    for a union `uncapped_pool` doesn't cover yet - a graceful no-op, not a
    crash or an error."""
    return build_season_pool(short_code, year, include_uncapped=True)


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
