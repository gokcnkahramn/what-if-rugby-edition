from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.engine.match_engine import MAX_SUBSTITUTIONS
from rugby_sim.models import Lineup, Position, Team


def _team_with_bench(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = ENGLAND_SAMPLE[0]
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def test_match_runs_fine_with_no_bench_at_all():
    # No bench players set - injuries should just down-man the team instead
    # of crashing when a replacement isn't available.
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    result = MatchEngine(home, away, seed=1).run()
    assert result.score_home >= 0 and result.score_away >= 0


def test_injury_substitution_swaps_in_a_bench_player_and_is_logged():
    home = _team_with_bench("Home")
    away = _team_with_bench("Away")
    # Reuse a couple of starters as makeshift bench depth for the test.
    home.lineup.add_bench(ENGLAND_SAMPLE[0])

    engine = MatchEngine(home, away, seed=1)
    # Force at least one injury roll to fire deterministically.
    import rugby_sim.engine.match_engine as me
    original = me.P_INJURY_PER_DRIVE
    me.P_INJURY_PER_DRIVE = 1.0
    try:
        result = engine.run()
    finally:
        me.P_INJURY_PER_DRIVE = original

    assert result.stats["Home"].injuries >= 1
    injury_events = [e for e in result.events if "Injury" in e.text]
    assert injury_events


def test_apply_substitution_hook_respects_bench_and_cap():
    home = _team_with_bench("Home")
    away = _team_with_bench("Away")
    home.lineup.add_bench(ENGLAND_SAMPLE[0])
    engine = MatchEngine(home, away, seed=5)
    engine.run()  # populates _active/_bench

    # No bench left for Away (never added any).
    assert engine.apply_substitution(away, Position.HOOKER) is False


def test_no_more_than_max_substitutions_per_team():
    home = _team_with_bench("Home")
    away = _team_with_bench("Away")
    for p in ENGLAND_SAMPLE[:8]:
        home.lineup.add_bench(p)
    engine = MatchEngine(home, away, seed=1)
    import rugby_sim.engine.match_engine as me
    original = me.P_INJURY_PER_DRIVE
    me.P_INJURY_PER_DRIVE = 1.0
    try:
        result = engine.run()
    finally:
        me.P_INJURY_PER_DRIVE = original
    assert result.stats["Home"].substitutions <= MAX_SUBSTITUTIONS
