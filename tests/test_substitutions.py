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


def test_advance_to_and_finish_produce_the_same_shape_as_run():
    home = _team_with_bench("Home")
    away = _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=42)
    engine.advance_to(20)
    # drives are 1-4 minutes each, so a checkpoint can overshoot slightly -
    # "at least 20" is the actual contract, not an exact minute
    assert 20 <= engine.minute <= 20 + 4
    assert not engine.is_finished()
    result = engine.finish()
    assert result.player_of_the_match is not None or result.player_stats == []
    assert result.score_home >= 0 and result.score_away >= 0

    # a second call to finish() must not double-finalize (e.g. double-count
    # territory % or re-run Player of the Match selection differently)
    result_again = engine.finish()
    assert result_again is result
    assert result_again.score_home == result.score_home


def test_run_interactive_allows_a_manual_substitution_at_a_checkpoint():
    home = _team_with_bench("Home")
    away = _team_with_bench("Away")
    home.lineup.add_bench(ENGLAND_SAMPLE[0])
    engine = MatchEngine(home, away, seed=7)

    checkpoints_seen = []

    def on_checkpoint(eng, minute):
        checkpoints_seen.append(minute)
        if len(checkpoints_seen) == 2:  # the "40" checkpoint
            starting_hooker = eng.active_lineup(home)[Position.HOOKER].player
            made_sub = eng.apply_substitution(home, Position.HOOKER, bench_player=ENGLAND_SAMPLE[0])
            assert made_sub is True
            assert eng.active_lineup(home)[Position.HOOKER].player is ENGLAND_SAMPLE[0]
            assert eng.active_lineup(home)[Position.HOOKER].player is not starting_hooker

    result = engine.run_interactive([20, 40, 60], on_checkpoint)
    # checkpoints can overshoot slightly (1-4 minute drive granularity) but
    # must be reached in order and each at or past its target
    assert len(checkpoints_seen) == 3
    for target, seen in zip([20, 40, 60], checkpoints_seen):
        assert target <= seen <= target + 4
    assert result.stats["Home"].substitutions >= 1
    sub_events = [e for e in result.events if "Substitution" in e.text]
    assert sub_events


def test_apply_substitution_rejects_a_player_not_on_the_bench():
    home = _team_with_bench("Home")
    away = _team_with_bench("Away")
    home.lineup.add_bench(ENGLAND_SAMPLE[0])
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    not_on_bench = ENGLAND_SAMPLE[1]
    assert engine.apply_substitution(home, Position.HOOKER, bench_player=not_on_bench) is False
