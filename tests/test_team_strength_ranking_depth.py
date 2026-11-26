"""Verification for the team strength/ranking system follow-up: squad
quality separated from real-performance ranking, and the per-match rating
swing (real "performance vs expectation" - previously computed by
`TeamRankingTracker.record_result` and silently discarded by
`Tournament._play`, now captured and exposed).

Also investigated, not changed: "balance the effect of big wins/losses" -
confirmed already true by design. `update_after_match` has no margin-of-
victory term at all (matching the real World Rugby algorithm, documented
in `rankings.py`'s own module docstring) - a 60-0 win updates a team's
rating identically to a 24-21 win over the same opponent, so a landslide
can never swing a rating disproportionately. Adding an invented
margin-of-victory bonus would be a real DEVIATION from the real formula
this module already faithfully reimplements, not a fix - reported
honestly rather than changed."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.models import Attributes, Lineup, Player, Position, Team
from rugby_sim.tournament import Tournament
from rugby_sim.tournament.rankings import TeamRankingTracker, update_after_match


def _team(name, attrs=None):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        player = p if attrs is None else Player(
            p.name, p.nation, p.natural_position,
            Attributes(**{**p.attributes.as_dict(), **attrs}),
        )
        lineup.set_starter(player.natural_position, player)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def test_squad_quality_score_is_a_real_0_to_100_number_from_real_fit_ratings():
    home = _team("Home")
    score = home.lineup.squad_quality_score()
    assert 0.0 < score <= 100.0
    # Matches the mean of every starter's own real fit rating - not a
    # separately invented formula.
    expected = sum(s.fit_rating for s in home.lineup.starters.values()) / len(home.lineup.starters)
    assert abs(score - expected) < 1e-9


def test_squad_quality_score_is_zero_for_an_empty_lineup():
    assert Lineup().squad_quality_score() == 0.0


def test_squad_quality_responds_to_real_attribute_differences():
    strong = _team("Home", dict(pace=95, footwork=95, offload=95, tackling=95, strength=95))
    weak = _team("Home", dict(pace=20, footwork=20, offload=20, tackling=20, strength=20))
    assert strong.lineup.squad_quality_score() > weak.lineup.squad_quality_score()


def test_per_match_rating_swing_is_captured_not_discarded():
    home, away = _team("Home"), _team("Away")
    tournament = Tournament(teams={"Home": home, "Away": away})
    result = tournament._play("Home", "Away", seed=1)
    assert hasattr(result, "rating_swing_home")
    assert hasattr(result, "rating_swing_away")
    # Zero-sum between the two sides, same as `update_after_match` itself.
    assert abs(result.rating_swing_home + result.rating_swing_away) < 1e-6


def test_rating_swing_matches_the_tracker_formula_directly():
    rankings = TeamRankingTracker()
    before_home = rankings.rating("Home")
    before_away = rankings.rating("Away")
    home_delta, away_delta = rankings.record_result("Home", "Away", 30, 10)
    expected_home, expected_away = update_after_match(before_home, before_away, 1.0)
    assert abs((before_home + home_delta) - expected_home) < 1e-9
    assert abs((before_away + away_delta) - expected_away) < 1e-9


def test_margin_of_victory_does_not_change_the_rating_swing_by_design():
    # A 60-0 landslide and a 24-21 nail-biter against the SAME opponent
    # move the rating by the exact same amount - confirms the "balance
    # big win/loss effects" ask is already satisfied, not missing.
    landslide = TeamRankingTracker()
    landslide.record_result("Home", "Away", 60, 0)

    narrow = TeamRankingTracker()
    narrow.record_result("Home", "Away", 24, 21)

    assert landslide.rating("Home") == narrow.rating("Home")
    assert landslide.rating("Away") == narrow.rating("Away")
