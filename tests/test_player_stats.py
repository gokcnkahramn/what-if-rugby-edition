from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Lineup, Team


def _team(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = ENGLAND_SAMPLE[0]
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def test_try_events_name_a_real_on_field_scorer():
    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=3).run()
    on_field_names = {p.name for p in ENGLAND_SAMPLE}
    try_events = [e for e in result.events if e.text.startswith("TRY!")]
    assert try_events
    for e in try_events:
        assert any(name in e.text for name in on_field_names)


def test_player_stats_points_match_team_totals():
    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=3).run()
    for team_name, stats in result.stats.items():
        expected_points = stats.tries * 5 + stats.conversions * 2 + stats.penalty_goals * 3
        actual_points = sum(ps.points for ps in result.player_stats if ps.team == team_name)
        assert actual_points == expected_points


def test_player_of_the_match_is_a_real_scoring_contributor():
    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=3).run()
    if result.player_of_the_match is not None:
        matching = [ps for ps in result.player_stats if ps.player is result.player_of_the_match]
        assert matching and matching[0].pom_score > 0
        assert matching[0].pom_score == max(ps.pom_score for ps in result.player_stats)
