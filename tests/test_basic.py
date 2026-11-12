from rugby_sim.data import ENGLAND_SAMPLE, LEGENDS
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Team, Lineup, Position


def build_team(name, players, overrides=None):
    lineup = Lineup()
    for p in players:
        lineup.set_starter(p.natural_position, p)
    for pos, player in (overrides or {}).items():
        lineup.set_starter(pos, player)
    lineup.captain = players[0]
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def test_lineup_validates():
    team = build_team("England", ENGLAND_SAMPLE)
    assert team.lineup.validate() == []


def test_out_of_position_rating_is_penalized():
    lomu = next(p for p in LEGENDS if p.name == "Jonah Lomu")
    natural = lomu.rating_at(Position.RIGHT_WING)
    out_of_position = lomu.rating_at(Position.FULLBACK)
    assert out_of_position < natural


def test_match_runs_and_produces_a_result():
    home = build_team("Home", ENGLAND_SAMPLE)
    away = build_team("Away", ENGLAND_SAMPLE)
    engine = MatchEngine(home, away, seed=1)
    result = engine.run()
    assert result.score_home >= 0 and result.score_away >= 0
    assert len(result.events) > 0
