"""Converts aggregated rugbydata box-score stats into our 1-100 `Attributes`.

This is a documented *approximation*, not a scouted rating: the dataset has
no raw pace/strength numbers, so attributes like `pace` or `strength` are
inferred from proxies (line breaks, defenders beaten, carries per minute).
Where a formula is a stretch, it's called out below. If this mapping is
ever found to produce clearly wrong results for a union, prefer the
Wikipedia/manual fallback path for that union instead of tuning around it.

Scaling: when enough same-position peers are supplied (`peer_proxies`,
>= `MIN_PEER_SAMPLE` players), a value is converted to 1-100 by its
**percentile rank among those peers** - "better than N% of locks in this
pool" - rather than a fixed, arbitrarily-chosen breakpoint. With too few
peers (a thin pool, or no peer data passed at all - the original,
still-supported calling convention), it falls back to the original fixed
breakpoints, since percentiles from a handful of players are noisy.

Input: a pandas Series/dict of *summed or averaged* per-cap stats for one
player's international appearances (see `pool_builder.build_union_pool`).
"""

from __future__ import annotations

from dataclasses import fields
from typing import Dict, List, Mapping, Optional

from ...models.attributes import Attributes

MIN_PEER_SAMPLE = 5

# Rough, real-world-informed competitiveness multiplier per union, applied
# as a final pass to EVERY player regardless of data source (real
# rugbydata stats, Wikipedia-cross-referenced stats, or archetype
# fallback) - see `scale_to_union_strength`. Without this, percentile
# ranking (which is only *relative*, with no absolute calibration) or a
# flat archetype baseline could both end up rating a minnow's player
# similarly to a rugby superpower's, erasing a real and often very large
# gap in quality. 1.0 = unchanged; lower pulls every attribute toward 50
# (replacement level) in proportion to how far below Tier 1 that union
# generally sits. Not a ranking claim, just enough separation that a
# "what if" match doesn't make upsets routine instead of occasional.
UNION_STRENGTH: Dict[str, float] = {
    "ENG": 1.0, "FRA": 1.0, "IRE": 1.0, "SCO": 1.0, "WAL": 1.0, "ITA": 0.9,
    "NZL": 1.0, "AUS": 1.0, "RSA": 1.0, "ARG": 0.95, "JPN": 0.8, "FIJ": 0.8,
    "GEO": 0.7, "ROU": 0.4, "ESP": 0.3, "POR": 0.4, "SAM": 0.75, "TGA": 0.65,
    "USA": 0.4, "CAN": 0.35, "URU": 0.3, "CHI": 0.2, "NAM": 0.25,
    "HKG": 0.12, "ZIM": 0.15, "BAR": 1.0,
}
DEFAULT_UNION_STRENGTH = 0.4

# Never compressed toward 50 - versatility is a player trait (how well
# THEY personally adapt out of position), not a reflection of their
# union's overall competitiveness.
_UNION_STRENGTH_EXEMPT_ATTRS = {"versatility"}


def scale_to_union_strength(attrs: Attributes, strength: float) -> Attributes:
    if strength >= 1.0:
        return attrs
    data = {}
    for f in fields(attrs):
        value = getattr(attrs, f.name)
        if f.name in _UNION_STRENGTH_EXEMPT_ATTRS:
            data[f.name] = value
        else:
            data[f.name] = 50 + (value - 50) * strength
    return Attributes(**data).clamp()


def _get(stats: Mapping, key: str, default: float = 0.0) -> float:
    v = stats.get(key)
    if v is None or v != v:  # NaN check without importing numpy/pandas here
        return default
    return float(v)


def _scale(value: float, lo: float, hi: float, out_lo: float = 30, out_hi: float = 95) -> float:
    if hi == lo:
        return (out_lo + out_hi) / 2
    pct = (value - lo) / (hi - lo)
    pct = max(0.0, min(1.0, pct))
    return out_lo + pct * (out_hi - out_lo)


def _percentile_scale(value: float, peers: List[float], out_lo: float = 30, out_hi: float = 95) -> float:
    """What fraction of `peers` this value is >= - mapped onto [out_lo, out_hi]."""
    n = len(peers)
    rank = sum(1 for v in peers if v <= value)
    pct = rank / n
    return out_lo + pct * (out_hi - out_lo)


def _compute_proxies(stats: Mapping, caps: int) -> Dict[str, float]:
    """Pure per-player proxy values (no scaling yet) - the same values are
    computed for every peer when building `peer_proxies`, so percentile
    ranking compares like with like."""
    caps = max(1, caps)

    tackles_made = _get(stats, "tackles_made")
    tackles_missed = _get(stats, "tackles_missed")
    tackle_attempts = tackles_made + tackles_missed
    tackle_success = tackles_made / tackle_attempts if tackle_attempts else 0.85
    dominant_tackles = _get(stats, "dominant_tackles") / caps

    carries = _get(stats, "carries") / caps
    metres = _get(stats, "metres_carried") / caps
    line_breaks = _get(stats, "line_breaks") / caps
    clean_breaks = _get(stats, "clean_breaks") / caps
    defenders_beaten = _get(stats, "defenders_beaten") / caps
    offloads = _get(stats, "offloads") / caps

    passes = _get(stats, "passes") / caps
    turnovers_lost = _get(stats, "turnovers_lost") / caps

    kicks_from_hand = _get(stats, "kicks_from_hand") / caps

    lineouts_won = _get(stats, "lineouts_won") / caps
    total_lineouts = _get(stats, "total_lineouts") / caps

    rucks_won = _get(stats, "rucks_won") / caps

    penalties_conceded = _get(stats, "penalties_conceded") / caps
    cards = (_get(stats, "yellow_cards") + _get(stats, "red_cards") * 2) / caps

    return {
        "tackle_success": tackle_success,
        "dominant_tackles": dominant_tackles,
        "pace": line_breaks + clean_breaks,
        "footwork": defenders_beaten,
        "strength": metres / max(carries, 1.0),
        "offload": offloads,
        "handling": passes - turnovers_lost * 3,
        "kicking_game": kicks_from_hand,
        "lineout_jumping": lineouts_won,
        "lineout_throwing": total_lineouts,
        "scrummaging": rucks_won,
        "discipline_raw": 2.0 - penalties_conceded - cards * 20,
        "lineouts_won_flag": 1.0 if lineouts_won else 0.0,
    }


def map_stats_to_attributes(
    stats: Mapping, caps: int, peer_proxies: Optional[Dict[str, List[float]]] = None
) -> Attributes:
    proxies = _compute_proxies(stats, caps)

    def scaled(name: str, lo: float, hi: float, out_lo: float = 30, out_hi: float = 95) -> float:
        value = proxies[name]
        peers = peer_proxies.get(name) if peer_proxies else None
        if peers and len(peers) >= MIN_PEER_SAMPLE:
            return _percentile_scale(value, peers, out_lo, out_hi)
        return _scale(value, lo, hi, out_lo, out_hi)

    tackling = scaled("tackle_success", 0.70, 0.95)
    tackle_technique = scaled("dominant_tackles", 0.0, 3.0)
    pace = scaled("pace", 0.0, 1.5)
    footwork = scaled("footwork", 0.0, 2.5)
    strength = scaled("strength", 2.0, 7.0)
    offload = scaled("offload", 0.0, 2.0)
    handling = scaled("handling", 2.0, 25.0)
    kicking_game = scaled("kicking_game", 0.0, 6.0)
    lineout_jumping = scaled("lineout_jumping", 0.0, 3.0)
    lineout_throwing = scaled("lineout_throwing", 0.0, 10.0)
    scrummaging = scaled("scrummaging", 0.0, 8.0)
    discipline = scaled("discipline_raw", 0.0, 2.0)
    discipline = max(5.0, discipline)

    kick_success = _get(stats, "kick_percent_success", default=float("nan"))
    penalty_goals = _get(stats, "penalty_goals")
    conversion_goals = _get(stats, "conversion_goals")
    is_kicker = (penalty_goals + conversion_goals) > 0
    if is_kicker and kick_success == kick_success:  # not NaN
        goal_kicking = _scale(kick_success, 0.55, 0.95, out_lo=55, out_hi=96)
    elif is_kicker:
        goal_kicking = 70.0
    else:
        goal_kicking = 35.0

    return Attributes(
        pace=round(pace),
        acceleration=round(pace),
        strength=round(strength),
        fitness=60,
        agility=round((pace + footwork) / 2),
        tackling=round(tackling),
        tackle_technique=round(tackle_technique),
        aerial=round(lineout_jumping if proxies["lineouts_won_flag"] else 50),
        scrummaging=round(scrummaging),
        lineout_jumping=round(lineout_jumping),
        lineout_throwing=round(lineout_throwing),
        handling=round(handling),
        passing=round(handling),
        offload=round(offload),
        footwork=round(footwork),
        kicking_game=round(kicking_game),
        goal_kicking=round(goal_kicking),
        place_kicking_range=round(goal_kicking),
        game_intelligence=round((tackling + handling) / 2),
        positioning=round((tackling + handling) / 2),
        leadership=50,
        discipline=round(discipline),
        composure=round((discipline + goal_kicking) / 2),
        versatility=40,
    ).clamp()


def build_peer_proxies(stats_caps_pairs: List[tuple]) -> Dict[str, List[float]]:
    """Given [(stats, caps), ...] for every player at one position in a
    pool, returns {proxy_name: [value_per_player, ...]} for percentile
    scaling. Called once per position by `pool_builder`, not per player."""
    peer_proxies: Dict[str, List[float]] = {}
    for stats, caps in stats_caps_pairs:
        for name, value in _compute_proxies(stats, caps).items():
            peer_proxies.setdefault(name, []).append(value)
    return peer_proxies
