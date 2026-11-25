"""Verification for the THIRD player-specific decision behavior (match-
engine-depth Phase 9, extending the scrum-half snipe try / openside
flanker jackal threat pattern to a third position): the NEAR wing's OWN
`footwork`/`pace` (not a team-wide average) can beat the last defender for
an individually-attributed try, near the line."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Attributes, Lineup, Player, Position, Team


def _team(name, lw_attrs=None):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        player = p
        if lw_attrs and p.natural_position == Position.LEFT_WING:
            player = Player(p.name, p.nation, p.natural_position, Attributes(**{**p.attributes.as_dict(), **lw_attrs}))
        lineup.set_starter(player.natural_position, player)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def _wing_break_count(lw_attrs, seeds=60):
    total = 0
    for seed in range(seeds):
        home = _team("Home", lw_attrs)
        away = _team("Away")
        result = MatchEngine(home, away, seed=seed).run()
        total += sum(1 for e in result.events if "steps the last defender" in e.text and e.team == "Home")
    return total


def test_an_elite_footwork_wing_beats_the_defense_far_more_than_an_average_one():
    elite = _wing_break_count(dict(footwork=99, pace=99))
    average = _wing_break_count(dict(footwork=50, pace=50))
    assert elite > average


def test_wing_break_names_the_specific_wing_and_credits_them():
    # The boosted attrs are only on the LEFT wing, but the mechanism fires
    # for whichever wing matches the ball's current `Side` that phase - so
    # the RIGHT wing (unboosted, default attrs) can legitimately score this
    # way too, just less often. Accept either real wing by name.
    found = False
    for seed in range(60):
        home = _team("Home", dict(footwork=99, pace=99))
        away = _team("Away")
        wing_names = {
            home.lineup.starters[Position.LEFT_WING].player.name,
            home.lineup.starters[Position.RIGHT_WING].player.name,
        }
        result = MatchEngine(home, away, seed=seed).run()
        for e in result.events:
            if "steps the last defender" in e.text and e.team == "Home":
                scorer_name = next(name for name in wing_names if name in e.text)
                ps = next(
                    (p for p in result.player_stats if p.team == "Home" and p.player.name == scorer_name), None,
                )
                assert ps is not None and ps.tries > 0
                found = True
        if found:
            break
    assert found, "expected at least one wing-break try across 60 seeds"
