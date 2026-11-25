"""Verification for set-piece sub-scenarios (match-engine-depth Phase 10):
a clean scrum/lineout win close to the line can now become a real,
recognizable rugby pattern - a number 8's pick-and-go, or a hooker peeling
off a driving maul - instead of always falling through to the generic
phase loop. Each is driven by that ONE specific player's own `strength`/
`game_intelligence`, not a team-wide average, same pattern as this arc's
other player-specific decision behaviors."""

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


def test_an_elite_number_8_scores_far_more_pick_and_go_tries_than_an_average_one():
    elite = _count("picks up from the base", Position.NUMBER_8, dict(strength=99, game_intelligence=99))
    average = _count("picks up from the base", Position.NUMBER_8, dict(strength=50, game_intelligence=50))
    assert elite > average


def test_an_elite_hooker_scores_far_more_driving_maul_tries_than_an_average_one():
    elite = _count("peels off the back", Position.HOOKER, dict(strength=99, game_intelligence=99))
    average = _count("peels off the back", Position.HOOKER, dict(strength=50, game_intelligence=50))
    assert elite > average


def test_pick_and_go_try_names_the_number_8_and_credits_them():
    found = False
    for seed in range(60):
        home = _team("Home", Position.NUMBER_8, dict(strength=99, game_intelligence=99))
        away = _team("Away")
        no8 = home.lineup.starters[Position.NUMBER_8].player
        result = MatchEngine(home, away, seed=seed).run()
        for e in result.events:
            if "picks up from the base" in e.text and e.team == "Home":
                assert no8.name in e.text
                ps = next((p for p in result.player_stats if p.team == "Home" and p.player.name == no8.name), None)
                assert ps is not None and ps.tries > 0
                found = True
        if found:
            break
    assert found, "expected at least one pick-and-go try across 60 seeds"


def test_driving_maul_try_names_the_hooker_and_credits_them():
    found = False
    for seed in range(60):
        home = _team("Home", Position.HOOKER, dict(strength=99, game_intelligence=99))
        away = _team("Away")
        hooker = home.lineup.starters[Position.HOOKER].player
        result = MatchEngine(home, away, seed=seed).run()
        for e in result.events:
            if "peels off the back" in e.text and e.team == "Home":
                assert hooker.name in e.text
                ps = next((p for p in result.player_stats if p.team == "Home" and p.player.name == hooker.name), None)
                assert ps is not None and ps.tries > 0
                found = True
        if found:
            break
    assert found, "expected at least one driving-maul try across 60 seeds"
