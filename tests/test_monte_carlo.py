"""Verification for the Monte Carlo "what-if" comparison: the same two
lineups run many times with different seeds, aggregated into real
percentage distributions (never a single collapsed mean/median) for the
match outcome, each side's scoreline, Player of the Match, and every real
per-team stat."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.models import Lineup, Position, Team
from rugby_sim.tournament.monte_carlo import (
    MAX_MONTE_CARLO_RUNS, aggregate_monte_carlo, run_monte_carlo_matches,
)


def _team(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def test_run_monte_carlo_matches_runs_the_requested_number_with_distinct_seeds():
    home, away = _team("Home"), _team("Away")
    results = run_monte_carlo_matches(home, away, 20)
    assert len(results) == 20
    scorelines = {(r.score_home, r.score_away) for r in results}
    assert len(scorelines) > 1  # genuinely different runs, not 20 copies


def test_n_is_clamped_to_the_max():
    home, away = _team("Home"), _team("Away")
    results = run_monte_carlo_matches(home, away, MAX_MONTE_CARLO_RUNS + 500)
    assert len(results) == MAX_MONTE_CARLO_RUNS


def test_outcome_distribution_sums_to_100_and_is_a_real_tally():
    home, away = _team("Home"), _team("Away")
    results = run_monte_carlo_matches(home, away, 50)
    agg = aggregate_monte_carlo(results, "Home", "Away")
    assert agg["runs"] == 50
    pct = agg["outcome_pct"]
    assert set(pct.keys()) == {"home_win", "draw", "away_win"}
    assert abs(sum(pct.values()) - 100.0) < 0.6  # rounding tolerance only
    recomputed_home_wins = sum(1 for r in results if r.score_home > r.score_away)
    assert pct["home_win"] == round(100 * recomputed_home_wins / 50, 1)


def test_player_of_the_match_distribution_is_real_and_never_padded():
    home, away = _team("Home"), _team("Away")
    results = run_monte_carlo_matches(home, away, 60)
    agg = aggregate_monte_carlo(results, "Home", "Away")
    pom_dist = agg["player_of_the_match_distribution"]
    assert pom_dist  # someone was POM at least once across 60 real matches
    total_pct = sum(e["pct"] for e in pom_dist)
    assert total_pct <= 100.5
    # Sorted descending by real share.
    assert all(pom_dist[i]["pct"] >= pom_dist[i + 1]["pct"] for i in range(len(pom_dist) - 1))
    # Every entry's percentage matches a real recount against the raw results.
    for entry in pom_dist:
        real_count = sum(
            1 for r in results
            if r.player_of_the_match is not None and r.player_of_the_match.name == entry["name"]
        )
        assert entry["pct"] == round(100 * real_count / 60, 1)


def test_every_real_team_stat_field_gets_a_distribution():
    home, away = _team("Home"), _team("Away")
    results = run_monte_carlo_matches(home, away, 40)
    agg = aggregate_monte_carlo(results, "Home", "Away")
    home_dist = agg["team_stats_distribution"]["Home"]
    # A representative sample of real TeamMatchStats fields, not an
    # exhaustive hardcoded list (the aggregator iterates every dataclass
    # field automatically - this just spot-checks a few of them).
    for stat in ("tries", "possessions", "territory_pct", "carries", "scrums_won"):
        assert stat in home_dist
        dist = home_dist[stat]
        assert dist  # never empty - every run produced a real value
        total_pct = sum(e["pct"] for e in dist)
        assert total_pct <= 100.5
        for entry in dist:
            assert "label" in entry and "pct" in entry and "count" in entry


def test_discrete_vs_histogram_distribution_shape():
    home, away = _team("Home"), _team("Away")
    results = run_monte_carlo_matches(home, away, 60)
    agg = aggregate_monte_carlo(results, "Home", "Away")
    tries_dist = agg["team_stats_distribution"]["Home"]["tries"]
    # tries is a small-range counting stat - expect discrete integer labels,
    # not a binned "x-y" range label.
    for entry in tries_dist:
        assert "-" not in entry["label"]
    metres_dist = agg["team_stats_distribution"]["Home"]["metres_gained"]
    # metres_gained has a wide real range across 60 matches - expect it to
    # fall back to binned ranges once past MAX_DISCRETE_VALUES distinct
    # real values (not asserted as a hard count, since real variance could
    # occasionally land under the threshold, but at minimum every bucket
    # must be well-formed).
    for entry in metres_dist:
        assert "label" in entry
