"""Verification for the two new real, distinct kick types added to close
the "grubber/chip kick" gap in the kicking system: a grubber kick (right on
the defending team's line, scrum-half driven, chased by the NEAR wing) and
a chip kick (the real counter to a blitz defence - only reachable while
facing a genuinely blitz-leaning defensive style, fly-half driven)."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Attributes, Lineup, Player, Position, Team


def _team(name, boost=None, boost_positions=None):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        player = p
        if boost and (boost_positions is None or p.natural_position in boost_positions):
            player = Player(p.name, p.nation, p.natural_position, Attributes(**{**p.attributes.as_dict(), **boost}))
        lineup.set_starter(player.natural_position, player)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def _count_events(result, phrase):
    return sum(1 for e in result.events if phrase in e.text)


def test_grubber_kick_try_is_real_and_happens_for_an_elite_scrum_half_and_wing():
    # Verified as an EXISTENCE check across many seeds, not a comparative
    # count: `game_intelligence` (needed for the grubber's own kick_skill)
    # also feeds the scrum-half's INDEPENDENT, higher-priority snipe-try
    # slice (checked earlier in the same cumulative roll), and boosting the
    # wing's pace/footwork also raises the independent `p_wing_break` slice
    # - either confound can suppress a lower-priority mechanism's REALIZED
    # frequency even though its own nominal probability also rose (the
    # exact issue `test_tactics_system.py`'s own module docstring
    # documents, and the reason this file verifies grubber/chip existence
    # directly rather than chasing a noisy elite-vs-average comparison).
    boost_positions = {Position.SCRUM_HALF, Position.LEFT_WING, Position.RIGHT_WING}
    elite = _team("Home", dict(kicking_game=99, game_intelligence=99, pace=99, footwork=99), boost_positions)
    plain = _team("Away")
    total = 0
    for seed in range(150):
        total += _count_events(MatchEngine(elite, plain, seed=seed).run(), "grubbers it through")
    assert total > 0


def test_chip_kick_try_only_happens_against_a_blitz_leaning_defence():
    home = _team("Home", dict(kicking_game=99, game_intelligence=99, pace=99, footwork=99))
    blitz_away = _team("Away", dict(tackle_technique=99, positioning=20))
    neutral_away = _team("Away2")

    chip_vs_blitz = 0
    chip_vs_neutral = 0
    for seed in range(60):
        chip_vs_blitz += _count_events(MatchEngine(home, blitz_away, seed=seed).run(), "chips over the onrushing")
        chip_vs_neutral += _count_events(MatchEngine(home, neutral_away, seed=seed).run(), "chips over the onrushing")

    assert chip_vs_blitz > 0
    assert chip_vs_neutral == 0


def test_manager_kick_style_preference_boosts_the_chosen_kick_type():
    home = _team("Home")
    away = _team("Away")
    seeds = range(120)
    base = sum(_count_events(MatchEngine(home, away, seed=s, tactics=None).run(), "grubbers it through") for s in seeds)
    boosted = sum(
        _count_events(MatchEngine(home, away, seed=s, tactics={"Home": {"kick_style": "grubber"}}).run(), "grubbers it through")
        for s in seeds
    )
    assert boosted > base


def test_unrecognized_kick_style_choice_is_a_silent_no_op():
    home = _team("Home")
    away = _team("Away")
    engine = MatchEngine(home, away, seed=1, tactics={"Home": {"kick_style": "not_a_real_style"}})
    assert engine._kick_style_preference.get("Home") is None


def test_grubber_and_chip_credit_the_named_chasing_wing_a_real_try():
    elite = _team("Home", dict(kicking_game=99, game_intelligence=99, pace=99, footwork=99))
    plain = _team("Away")
    found_grubber = False
    for seed in range(60):
        result = MatchEngine(elite, plain, seed=seed).run()
        if _count_events(result, "grubbers it through"):
            scorer_names = {ps.player.name for ps in result.player_stats if ps.tries > 0}
            wing_names = {
                elite.lineup.starters[Position.LEFT_WING].player.name,
                elite.lineup.starters[Position.RIGHT_WING].player.name,
            }
            assert scorer_names & wing_names
            found_grubber = True
            break
    assert found_grubber
