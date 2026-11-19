"""Regression guards for the real-player rating distribution analysis (audit
section 4.3 - see `scripts/analyze_rating_distributions.py`).

These assert sane invariants derived from the REAL distribution that script
measures across every Tier 1 union's 2026 rugbydata-derived pool, not exact
means/medians (those shift whenever real stats refresh, and pinning them
would make this suite brittle for no safety benefit). Instead this checks
for the specific bug signatures a broken rating formula would actually
produce: a position's mean rating outside the documented 1-100 range, a
position where every player gets an identical/near-identical rating (flat
std-dev - a real symptom of a formula silently ignoring its inputs), or an
individual rating so far from its position's own mean that it can't be
explained by the real spread every OTHER position also shows.

The actual run (captured 2026-11-19, 291 unique real players across the 12
Tier 1 unions' 2026 pools) found every position's |z-score| for its most
extreme player topping out at about 2.34 (Left Wing's Haruto Kida) and every
position's std-dev at or above 4.8 (Loosehead Prop). The thresholds below
are set well clear of those real observed values (4.0 stdevs, stdev > 1.5)
specifically so they keep passing on normal data refreshes while still
catching a genuinely broken formula (e.g. one position collapsing to a
single repeated value, or a bug that multiplies one player's rating by 10).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Dict, List, Tuple

import pytest

from rugby_sim.data.sources.pool_builder import TIER1_TEAM_IDS, build_union_pool
from rugby_sim.models.position import Position

SEASON = "2026"

# Clear of the largest real |z| observed (~2.34) with ample headroom, while
# still tight enough to catch a formula bug that sends one player's rating
# far outside the real spread every position shows.
MAX_Z_SCORE = 4.0

# Clear below the smallest real per-position std-dev observed (~4.8), while
# still catching a "flat"/near-identical rating bug (std-dev collapsing
# toward 0) for any position.
MIN_STD_DEV = 1.5


@pytest.fixture(scope="module")
def ratings_by_position() -> Dict[Position, List[Tuple[float, str, str]]]:
    by_position: Dict[Position, List[Tuple[float, str, str]]] = defaultdict(list)
    seen = set()
    for code in TIER1_TEAM_IDS:
        pool = build_union_pool(code, season=SEASON)
        for p in pool:
            key = (p.nation, p.name.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            rating = p.rating_at(p.natural_position)
            by_position[p.natural_position].append((rating, p.name, p.nation))
    return by_position


def test_sample_is_nonempty_and_covers_most_positions(ratings_by_position):
    assert sum(len(v) for v in ratings_by_position.values()) > 100
    # Every one of the 15 real positions should have real capped players
    # somewhere across 12 Tier 1 unions' 2026 pools.
    assert len(ratings_by_position) >= 13


def test_all_individual_ratings_within_valid_range(ratings_by_position):
    for position, rows in ratings_by_position.items():
        for rating, name, nation in rows:
            assert 1.0 <= rating <= 100.0, (
                f"{name} ({nation}, {position.value}) rated {rating}, outside "
                "the documented 1-100 range"
            )


def test_position_mean_within_valid_range(ratings_by_position):
    for position, rows in ratings_by_position.items():
        ratings = [r for r, _, _ in rows]
        mean = statistics.mean(ratings)
        assert 1.0 <= mean <= 100.0, f"{position.value} mean {mean:.1f} outside [1, 100]"


def test_no_position_has_a_suspiciously_flat_rating_distribution(ratings_by_position):
    """A std-dev near 0 for a real position (with a decent sample) would mean
    every player there gets an (almost) identical rating - the signature of
    a formula bug that stopped actually using player-specific input."""
    for position, rows in ratings_by_position.items():
        if len(rows) < 5:
            continue  # too few players for std-dev to be a meaningful signal
        ratings = [r for r, _, _ in rows]
        std = statistics.stdev(ratings)
        assert std > MIN_STD_DEV, (
            f"{position.value} std-dev {std:.2f} is suspiciously flat "
            f"(n={len(ratings)})"
        )


def test_no_individual_rating_is_an_inexplicable_outlier(ratings_by_position):
    """No single real player's rating should sit wildly outside their own
    position's real mean/std-dev - that would indicate a formula bug for
    that specific player (e.g. a stat blowing up unscaled), not a real
    rugby talent gap, which the whole rest of this project's real sample
    shows tops out at roughly a 2.3 standard deviation spread."""
    for position, rows in ratings_by_position.items():
        if len(rows) < 5:
            continue
        ratings = [r for r, _, _ in rows]
        mean = statistics.mean(ratings)
        std = statistics.stdev(ratings)
        if std == 0:
            continue
        for rating, name, nation in rows:
            z = abs(rating - mean) / std
            assert z <= MAX_Z_SCORE, (
                f"{name} ({nation}, {position.value}) rating {rating} is "
                f"{z:.2f} std-devs from that position's mean {mean:.1f} "
                f"(std {std:.2f}) - outside the {MAX_Z_SCORE} bound"
            )
