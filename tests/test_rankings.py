from rugby_sim.tournament.rankings import (
    DEFAULT_RATING,
    TeamRankingTracker,
    expected_result,
    update_after_match,
)


def test_expected_result_monotonic():
    low = expected_result(70.0, 90.0)
    mid = expected_result(80.0, 80.0)
    high = expected_result(90.0, 70.0)
    assert low < mid < high
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0


def test_expected_result_neutral_gap_is_half():
    assert expected_result(80.0, 80.0, home_advantage=0.0) == 0.5


def test_upset_swings_more_than_expected_win():
    # Big underdog (B) beating big favourite (A): result_a = 0 (A lost).
    upset_a, upset_b = update_after_match(95.0, 60.0, result_a=0.0)
    upset_swing = abs(upset_a - 95.0)

    # Near-even match, favourite wins as expected.
    expected_win_a, _ = update_after_match(81.0, 79.0, result_a=1.0)
    expected_swing = abs(expected_win_a - 81.0)

    assert upset_swing > expected_swing


def test_world_cup_factor_doubles_swing():
    normal_a, normal_b = update_after_match(85.0, 80.0, result_a=1.0, is_world_cup=False)
    rwc_a, rwc_b = update_after_match(85.0, 80.0, result_a=1.0, is_world_cup=True)
    normal_swing = normal_a - 85.0
    rwc_swing = rwc_a - 85.0
    assert rwc_swing == normal_swing * 2


def test_draw_moves_both_ratings_toward_each_other():
    a, b = update_after_match(90.0, 70.0, result_a=0.5)
    assert a < 90.0
    assert b > 70.0


def test_tracker_seeds_known_team_and_defaults_unknown_team():
    tracker = TeamRankingTracker()
    assert tracker.rating("New Zealand") > DEFAULT_RATING
    assert tracker.rating("A Made Up Invitational XV") == DEFAULT_RATING


def test_tracker_record_result_updates_and_returns_deltas():
    tracker = TeamRankingTracker()
    before_home = tracker.rating("Italy")
    before_away = tracker.rating("South Africa")
    home_delta, away_delta = tracker.record_result("Italy", "South Africa", 10, 40)
    assert tracker.rating("Italy") == before_home + home_delta
    assert tracker.rating("South Africa") == before_away + away_delta
    assert home_delta < 0
    assert away_delta > 0


def test_tracker_shared_across_sequential_matches_accumulates():
    tracker = TeamRankingTracker()
    tracker.record_result("Wales", "Fiji", 30, 10)
    r1 = tracker.rating("Wales")
    tracker.record_result("Wales", "Fiji", 30, 10)
    r2 = tracker.rating("Wales")
    assert r2 > r1  # repeated wins keep climbing, same tracker, same team
