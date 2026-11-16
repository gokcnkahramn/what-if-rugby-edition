"""World-Rugby-style points ranking, reimplemented from World Rugby's own
publicly documented algorithm (there is no stable, documented third-party
API to depend on instead - `rawling/wr-calc` was checked and is just an
unofficial frontend over World Rugby's own site, not a reusable data
source). This is our own reimplementation of the real formula, not a
scrape - see `expected_result`/`update_after_match` below for exactly what
it does and doesn't model (no margin-of-victory term, since the real
algorithm doesn't have one either).

Used by both `Tournament`/`CustomTournament` (12b, one tournament's worth
of ranking movement) and `SeasonSession` (12c, a whole chained real
calendar year - the same tracker instance is threaded through every
tournament in the season so ratings carry over tournament boundaries,
exactly like `TournamentAvailability` already does for sidelining).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

# -- Seed snapshot -----------------------------------------------------
# Hand-entered, approximate World Rugby Men's ranking points, as of
# late 2025/early 2026 - a one-time, clearly-dated starting snapshot, NOT a
# live feed (there is nothing in this project that re-fetches real ranking
# points; this is where the "what if" ratings start, then diverge from
# reality as tracked matches are simulated). Sourced from memory of
# World Rugby's public rankings table around that time and rounded to a
# plausible point value per side - treat these as "roughly right", not an
# authoritative record.
WR_RANKING_SEED: Dict[str, float] = {
    "South Africa": 92.5,
    "New Zealand": 91.0,
    "Ireland": 89.0,
    "France": 88.0,
    "England": 83.5,
    "Argentina": 82.0,
    "Scotland": 81.0,
    "Fiji": 79.5,
    "Australia": 79.0,
    "Italy": 76.0,
    "Wales": 74.0,
    "Japan": 73.0,
    "Georgia": 72.5,
    "Samoa": 72.0,
    "Tonga": 70.5,
    "USA": 69.0,
    "Spain": 67.0,
    "Portugal": 68.0,
    "Romania": 65.0,
    "Uruguay": 64.5,
    "Canada": 63.5,
    "Chile": 62.0,
    "Namibia": 61.0,
    "Hong Kong": 58.0,
    "Zimbabwe": 56.0,
}

# Any union not present in `WR_RANKING_SEED` above (a Barbarians XV, a
# user's own custom-built team, or a real union this project's seed simply
# doesn't cover) starts from this documented baseline instead of an
# invented number - deliberately the lowest seeded value, so an unseeded
# side starts out looking like a weak/unranked nation rather than an
# average one.
DEFAULT_RATING = min(WR_RANKING_SEED.values())

HOME_ADVANTAGE = 3.0
NORMAL_FACTOR = 1.0
WORLD_CUP_FACTOR = 2.0


def expected_result(rating_a: float, rating_b: float, home_advantage: float = HOME_ADVANTAGE) -> float:
    """Expected result for side A (home) against side B (away), in [0, 1].
    Reimplements World Rugby's capped-linear mapping: the rating gap (A's
    rating + home advantage, minus B's rating) maps linearly onto expected
    result, capped at the extremes - a gap of 0 is a perfect toss-up (0.5),
    a big enough gap saturates at a near-certain win/loss rather than
    climbing without bound. No margin-of-victory term anywhere in this
    module - the real World Rugby algorithm doesn't use one, only the
    win/draw/loss result itself."""
    gap = (rating_a + home_advantage) - rating_b
    # World Rugby's published mapping: each ~10 rating points of gap is
    # worth about 0.1 of expected result around the 0.5 midpoint, capped
    # to [0.0, 1.0].
    expected = 0.5 + gap / 100.0
    return max(0.0, min(1.0, expected))


def update_after_match(
    rating_a: float, rating_b: float, result_a: float, is_world_cup: bool = False,
) -> Tuple[float, float]:
    """`result_a`: 1.0 win / 0.5 draw / 0.0 loss for side A (home). Returns
    the new `(rating_a, rating_b)` after applying the swing - points moved
    from the loser to the winner (or partially, for an upset/expected
    result), zero-sum between the two sides. `is_world_cup` doubles the
    swing (`WORLD_CUP_FACTOR`), matching World Rugby's real rule that a
    Rugby World Cup match counts double."""
    expected_a = expected_result(rating_a, rating_b)
    factor = WORLD_CUP_FACTOR if is_world_cup else NORMAL_FACTOR
    swing = (result_a - expected_a) * factor * 10.0  # scaled to plausible real point swings
    return rating_a + swing, rating_b - swing


@dataclass
class TeamRankingTracker:
    """Holds `{team_name: rating}`, seeded lazily from `WR_RANKING_SEED`
    (or `DEFAULT_RATING` for anything unseeded) the first time a team name
    is ever looked up - mirrors `TournamentAvailability`'s shape/ownership
    convention: a plain, mutable piece of state a `Tournament`/
    `CustomTournament`/`SeasonSession` owns (or receives, already shared,
    from a caller chaining several tournaments together) and threads
    through match-by-match."""

    ratings: Dict[str, float] = field(default_factory=dict)

    def rating(self, team_name: str) -> float:
        if team_name not in self.ratings:
            self.ratings[team_name] = WR_RANKING_SEED.get(team_name, DEFAULT_RATING)
        return self.ratings[team_name]

    def record_result(
        self, home: str, away: str, home_score: int, away_score: int, is_world_cup: bool = False,
    ) -> Tuple[float, float]:
        """Call once per finished match. Returns `(home_delta, away_delta)`
        - the rating swing each side experienced, for the "Team form"
        report's per-match-visible swing (same convention as the injury/
        card report's per-event rows)."""
        if home_score > away_score:
            result_home = 1.0
        elif home_score < away_score:
            result_home = 0.0
        else:
            result_home = 0.5

        before_home = self.rating(home)
        before_away = self.rating(away)
        after_home, after_away = update_after_match(before_home, before_away, result_home, is_world_cup=is_world_cup)
        self.ratings[home] = after_home
        self.ratings[away] = after_away
        return after_home - before_home, after_away - before_away
