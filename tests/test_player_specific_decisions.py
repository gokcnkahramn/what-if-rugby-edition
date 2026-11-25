"""Verification for player-specific decision behavior (match-engine-depth
Phase 6 - the review's "Dupont vs. an average scrum-half shouldn't make the
same decisions" ask): a scrum-half's OWN `pace`/`game_intelligence`
(not a team-wide average) can create a "snipe" try near the line - a real,
individually-attributed outcome, not a team-level one."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Attributes, Lineup, Player, Position, Team


def _team(name, sh_attrs=None):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        if sh_attrs and p.natural_position == Position.SCRUM_HALF:
            p = Player(p.name, p.nation, p.natural_position, Attributes(**{**p.attributes.as_dict(), **sh_attrs}))
        lineup.set_starter(p.natural_position, p)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def _snipe_try_count(sh_attrs, seeds=40):
    total = 0
    for seed in range(seeds):
        home = _team("Home", sh_attrs)
        away = _team("Away")
        result = MatchEngine(home, away, seed=seed).run()
        total += sum(1 for e in result.events if "snipes over" in e.text and e.team == "Home")
    return total


def test_an_elite_scrum_half_snipes_far_more_tries_than_an_average_one():
    # Statistical, many-seed check (RNG noise on one run proves nothing) -
    # everything else about the two teams is identical, only the
    # scrum-half's own pace/game_intelligence differs, so any gap is
    # genuinely attributable to that one player, not a team-wide swing.
    elite = _snipe_try_count(dict(pace=99, game_intelligence=99))
    average = _snipe_try_count(dict(pace=50, game_intelligence=50))
    assert elite > average


def test_snipe_try_names_the_scrum_half_as_scorer_and_credits_them():
    home = _team("Home", dict(pace=99, game_intelligence=99))
    away = _team("Away")
    scrum_half = home.lineup.starters[Position.SCRUM_HALF].player
    found = False
    for seed in range(40):
        result = MatchEngine(_team("Home", dict(pace=99, game_intelligence=99)), _team("Away"), seed=seed).run()
        for e in result.events:
            if "snipes over" in e.text and e.team == "Home":
                assert scrum_half.name in e.text
                ps = next(
                    (p for p in result.player_stats if p.team == "Home" and p.player.name == scrum_half.name),
                    None,
                )
                assert ps is not None and ps.tries > 0
                found = True
        if found:
            break
    assert found, "expected at least one snipe try across 40 seeds"
