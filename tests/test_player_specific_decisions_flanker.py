"""Verification for the SECOND player-specific decision behavior (match-
engine-depth Phase 8, extending Phase 6's scrum-half snipe-try pattern to a
second position): an openside flanker's OWN `tackle_technique`/
`game_intelligence` (not the team-wide `breakdown_def` average) creates a
real, individually-attributed extra jackal/turnover threat."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Attributes, Lineup, Player, Position, Team


def _team(name, of_attrs=None):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        player = p
        if of_attrs and p.natural_position == Position.OPENSIDE_FLANKER:
            player = Player(p.name, p.nation, p.natural_position, Attributes(**{**p.attributes.as_dict(), **of_attrs}))
        lineup.set_starter(player.natural_position, player)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def _jackal_turnover_count(of_attrs, seeds=40):
    total = 0
    for seed in range(seeds):
        home = _team("Home", of_attrs)
        away = _team("Away")
        result = MatchEngine(home, away, seed=seed).run()
        total += sum(1 for e in result.events if "jackals over the ball" in e.text and e.team == "Home")
    return total


def test_an_elite_fetcher_wins_far_more_breakdown_turnovers_than_an_average_one():
    # Statistical, many-seed check - everything else about the two teams
    # is identical, only the openside flanker's own tackle_technique/
    # game_intelligence differs, so any gap is genuinely attributable to
    # that one player, not a team-wide swing.
    elite = _jackal_turnover_count(dict(tackle_technique=99, game_intelligence=99))
    average = _jackal_turnover_count(dict(tackle_technique=50, game_intelligence=50))
    assert elite > average


def test_jackal_turnover_names_the_flanker_and_applies_phase_involvement_stamina():
    found = False
    for seed in range(40):
        home = _team("Home", dict(tackle_technique=99, game_intelligence=99))
        away = _team("Away")
        flanker = home.lineup.starters[Position.OPENSIDE_FLANKER].player
        engine = MatchEngine(home, away, seed=seed)
        engine.run()
        result = engine.result
        for e in result.events:
            if "jackals over the ball" in e.text and e.team == "Home":
                assert flanker.name in e.text
                assert engine.condition_for(flanker) < 100.0
                found = True
        if found:
            break
    assert found, "expected at least one jackal turnover across 40 seeds"
