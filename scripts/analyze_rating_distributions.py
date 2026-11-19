"""Position-by-position rating distribution analysis (audit section 4.3).

Why this exists: an external audit asked for mean/median/std-dev/outlier
analysis of player attribute ratings by position, to catch rating inflation
or compression, or arbitrary imbalances between positions, in the real
player attribute pipeline (`attribute_mapping.py`'s heuristic conversion
from real rugbydata box-score stats, as assembled by `pool_builder.py`).

Sampling choice: every Tier 1 union's 2026-season pool
(`build_union_pool(code, season="2026")` for all 12 `TIER1_TEAM_IDS` codes).
This is the largest REAL, rugbydata-derived sample readily available without
adding Tier 2/Wikipedia-only unions (which lean on weaker, non-rugbydata
fallback data and would muddy a pipeline-accuracy question with a data-
source-accuracy one) and without re-pulling every season (Tier 1 2026 pools
are already disk-cached by earlier test/calibration runs, so this stays fast
and not network-heavy). Each player's rating is computed via
`Player.rating_at(player.natural_position)` - their fit rating at the
position they actually, really play - which is the fairest "how good are
real players rated by this pipeline" number (not an out-of-position penalty
number).

Run: `python scripts/analyze_rating_distributions.py`
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Dict, List

from rugby_sim.data.sources.pool_builder import TIER1_TEAM_IDS, build_union_pool
from rugby_sim.models.player import Player
from rugby_sim.models.position import Position

SEASON = "2026"


def collect_players() -> List[Player]:
    players: List[Player] = []
    seen = set()
    for code in TIER1_TEAM_IDS:
        pool = build_union_pool(code, season=SEASON)
        for p in pool:
            key = (p.nation, p.name.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            players.append(p)
    return players


def analyze(players: List[Player]) -> Dict[Position, List[tuple]]:
    by_position: Dict[Position, List[tuple]] = defaultdict(list)
    for p in players:
        rating = p.rating_at(p.natural_position)
        by_position[p.natural_position].append((rating, p.name, p.nation))
    return by_position


def main() -> None:
    players = collect_players()
    print(f"Collected {len(players)} unique real players across {len(TIER1_TEAM_IDS)} "
          f"Tier 1 unions' {SEASON} pools.\n")

    by_position = analyze(players)

    header = f"{'Position':<20}{'N':>5}{'Mean':>8}{'Median':>8}{'StdDev':>8}{'Min':>7}{'Max':>7}"
    print(header)
    print("-" * len(header))

    # Keep a stable, jersey-number-ish ordering for readability.
    for position in Position:
        rows = by_position.get(position)
        if not rows:
            continue
        ratings = [r[0] for r in rows]
        mean = statistics.mean(ratings)
        median = statistics.median(ratings)
        std = statistics.stdev(ratings) if len(ratings) > 1 else 0.0
        print(
            f"{position.value:<20}{len(ratings):>5}{mean:>8.1f}{median:>8.1f}"
            f"{std:>8.1f}{min(ratings):>7.1f}{max(ratings):>7.1f}"
        )

    print()
    for position in Position:
        rows = by_position.get(position)
        if not rows:
            continue
        rows_sorted = sorted(rows, key=lambda r: r[0])
        bottom3 = rows_sorted[:3]
        top3 = rows_sorted[-3:][::-1]
        print(f"{position.value}:")
        print("  Top 3:    " + ", ".join(f"{n} ({nat}) {r:.1f}" for r, n, nat in top3))
        print("  Bottom 3: " + ", ".join(f"{n} ({nat}) {r:.1f}" for r, n, nat in bottom3))

    print()
    overall = [r for rows in by_position.values() for r, _, _ in rows]
    print(f"Overall: n={len(overall)} mean={statistics.mean(overall):.1f} "
          f"median={statistics.median(overall):.1f} stdev={statistics.stdev(overall):.1f} "
          f"min={min(overall):.1f} max={max(overall):.1f}")


if __name__ == "__main__":
    main()
