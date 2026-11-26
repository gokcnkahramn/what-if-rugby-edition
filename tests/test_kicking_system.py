"""Verification for kicking system detail (match-engine-depth Phase 11):
the cross-field kick (a fly-half's own kicking_game/game_intelligence
combined with the far wing's own aerial/pace - two named individuals, not
a team-wide average, producing a try) and the territorial box kick (the
scrum-half/fly-half's own kicking_game choosing to trade possession for
territory instead of carrying, with a real charge-down risk)."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Attributes, Lineup, Player, Position, Team


def _team(name, pos=None, attrs=None):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        player = p
        if attrs and p.natural_position == pos:
            player = Player(p.name, p.nation, p.natural_position, Attributes(**{**p.attributes.as_dict(), **attrs}))
        lineup.set_starter(player.natural_position, player)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def _count(phrase, pos, attrs, seeds=60):
    total = 0
    for seed in range(seeds):
        home = _team("Home", pos, attrs)
        away = _team("Away")
        result = MatchEngine(home, away, seed=seed).run()
        total += sum(1 for e in result.events if phrase in e.text and e.team == "Home")
    return total


def test_an_elite_fly_half_sets_up_far_more_cross_field_tries_than_an_average_one():
    elite = _count("cross-field kick", Position.FLY_HALF, dict(kicking_game=99, game_intelligence=99))
    average = _count("cross-field kick", Position.FLY_HALF, dict(kicking_game=50, game_intelligence=50))
    assert elite > average


def test_cross_field_try_names_both_the_fly_half_and_the_far_wing():
    found = False
    for seed in range(60):
        home = _team("Home", Position.FLY_HALF, dict(kicking_game=99, game_intelligence=99))
        away = _team("Away")
        fly_half = home.lineup.starters[Position.FLY_HALF].player
        wing_names = {
            home.lineup.starters[Position.LEFT_WING].player.name,
            home.lineup.starters[Position.RIGHT_WING].player.name,
        }
        result = MatchEngine(home, away, seed=seed).run()
        for e in result.events:
            if "cross-field kick" in e.text and e.team == "Home":
                assert fly_half.name in e.text
                scorer_name = next(name for name in wing_names if name in e.text)
                ps = next((p for p in result.player_stats if p.team == "Home" and p.player.name == scorer_name), None)
                assert ps is not None and ps.tries > 0
                found = True
        if found:
            break
    assert found, "expected at least one cross-field try across 60 seeds"


def test_a_better_kicking_half_back_pair_box_kicks_far_more_often():
    elite = _count("smart territorial kick", Position.FLY_HALF, dict(kicking_game=99))
    average = _count("smart territorial kick", Position.FLY_HALF, dict(kicking_game=50))
    assert elite > average


def test_box_kick_can_be_charged_down_as_a_real_turnover_risk():
    # Statistical: over enough seeds with a poor-kicking halfback pairing
    # facing a strong-aerial fullback, at least some box kicks should be
    # charged down - confirms the risk side of the trade-off is real, not
    # just flavor text with no consequence.
    charge_downs = 0
    for seed in range(60):
        home = _team("Home", Position.FLY_HALF, dict(kicking_game=70))
        away = _team("Away", Position.FULLBACK, dict(aerial=99))
        result = MatchEngine(home, away, seed=seed).run()
        charge_downs += sum(1 for e in result.events if "charged down" in e.text and e.team == "Home")
    assert charge_downs > 0
