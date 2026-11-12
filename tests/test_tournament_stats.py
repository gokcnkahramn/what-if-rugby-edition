from rugby_sim.data import POOLS
from rugby_sim.data.sources.auto_draft import auto_draft_team
from rugby_sim.models.position import Position
from rugby_sim.tournament import Tournament


def _teams(codes):
    teams = {}
    for code in codes:
        pool = POOLS[code](season="2026")
        teams[code] = auto_draft_team(code, pool, short_code=code)
    return teams


def test_round_robin_tournament_has_awards_with_no_late_stage_restriction():
    teams = _teams(["ENG", "FRA", "IRE", "SCO"])
    report = Tournament(teams).run_round_robin(seed=4)

    assert report.team_stats
    for code in teams:
        assert report.team_stats[code].played == 3  # round-robin of 4: 3 games each

    assert report.player_stats_aggregate
    assert len(report.team_of_tournament) <= 15
    assert all(isinstance(pos, Position) for pos in report.team_of_tournament)

    assert report.player_of_tournament is not None
    # no bracket at all in a plain round-robin - the semi-final restriction
    # must not apply, and the top overall performer should still be found
    assert report.player_of_tournament.matches_started > 0


def test_pool_and_knockout_tournament_restricts_player_of_tournament_to_late_stage():
    teams = _teams(["ENG", "FRA", "IRE", "SCO", "WAL", "ITA", "NZL", "RSA"])
    report = Tournament(teams).run_pool_and_knockout(pool_count=2, seed=6)

    assert any(rnd.stage in ("semi-final", "final") for rnd in report.bracket)
    pot = report.player_of_tournament
    assert pot is not None
    assert pot.played_late_stage is True


def test_team_of_tournament_never_repeats_the_same_player_twice():
    teams = _teams(["ENG", "FRA", "IRE", "SCO"])
    report = Tournament(teams).run_round_robin(seed=1)
    chosen_players = [(s.team, id(s.player)) for s in report.team_of_tournament.values()]
    assert len(chosen_players) == len(set(chosen_players))
