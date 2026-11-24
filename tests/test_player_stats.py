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
        # NOTE: this formula was missing `+ stats.drop_goals * 3` - a real
        # pre-existing gap in this test (not in the engine itself), only
        # ever exposed once a seed's events happened to include a drop
        # goal (seed 3 started doing so after the territory/zone model's
        # `_advance_zone` roll shifted downstream RNG consumption - see
        # `MATCH_ENGINE_MODEL.md` item 3). Fixed here, not reseeded around.
        expected_points = (
            stats.tries * 5 + stats.conversions * 2 + stats.penalty_goals * 3 + stats.drop_goals * 3
        )
        actual_points = sum(ps.points for ps in result.player_stats if ps.team == team_name)
        assert actual_points == expected_points


def test_player_of_the_match_is_a_real_scoring_contributor():
    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=3).run()
    if result.player_of_the_match is not None:
        # `_team()` builds both sides from the same `ENGLAND_SAMPLE` list,
        # so the identical `Player` object can legitimately appear in BOTH
        # lineups at once - `MatchEngine._credit` deliberately tracks that
        # as two separate per-team `PlayerMatchStats` rows (see its own
        # comment), so an identity-only lookup (`ps.player is ...`) can
        # match more than one row for the same physical object. Picking
        # `matching[0]` blindly used to grab whichever row came first
        # regardless of which one was actually the match-winning score -
        # a real test bug, only exposed once a seed (3, after the
        # territory/zone model shifted downstream RNG consumption - see
        # `MATCH_ENGINE_MODEL.md` item 3) happened to have that same
        # player score for both sides with different point totals. Fixed
        # by picking the matching row that actually carries the max score,
        # not just the first one found.
        matching = [ps for ps in result.player_stats if ps.player is result.player_of_the_match]
        assert matching
        best_pom_score = max(ps.pom_score for ps in result.player_stats)
        matching_best = [ps for ps in matching if ps.pom_score == best_pom_score]
        assert matching_best, "no matching row for the selected Player of the Match actually has the max score"
        assert matching_best[0].pom_score > 0
        assert matching_best[0].pom_score == best_pom_score
