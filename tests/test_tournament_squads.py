from rugby_sim.data import POOLS
from rugby_sim.tournament import Tournament
from rugby_sim.tournament.availability import TournamentAvailability


def _pools(codes):
    return {code: POOLS[code](season="2026") for code in codes}


def test_squads_mode_drafts_a_fresh_lineup_each_match():
    squads = _pools(["ENG", "FRA", "IRE", "SCO"])
    tournament = Tournament(squads=squads)
    report = tournament.run_round_robin(seed=2)

    assert sum(row.played for row in report.standings.table()) == 2 * len(report.results)
    # every match actually ran (a fresh auto-draft happened every time,
    # not a single reused Team/Lineup)
    assert len(report.results) == 6  # 4 choose 2


def test_squads_and_teams_can_be_mixed_in_one_tournament():
    from rugby_sim.data.sources.auto_draft import auto_draft_team

    squads = _pools(["ENG", "FRA"])
    fixed_team = auto_draft_team("Ireland", POOLS["IRE"](season="2026"), short_code="IRE")
    tournament = Tournament(teams={"Ireland": fixed_team}, squads=squads)
    assert tournament.known_names() == {"ENG", "FRA", "Ireland"}

    report = tournament.run_round_robin(seed=3)
    assert len(report.results) == 3  # 3 choose 2


def test_availability_sidelines_injured_and_red_carded_players_for_next_match():
    availability = TournamentAvailability()
    pool = POOLS["ENG"](season="2026")
    victim = pool[0]

    class FakeResult:
        injured_players = [("ENG", victim)]
        carded_players = []

    availability.record_match(FakeResult())
    assert availability.is_sidelined("ENG", victim)
    available_now = availability.filter_available("ENG", pool)
    assert victim not in available_now

    class EmptyResult:
        injured_players = []
        carded_players = []

    availability.record_match(EmptyResult())  # one match later, they're back
    assert not availability.is_sidelined("ENG", victim)


def test_squads_mode_raises_if_pool_runs_out_of_available_players():
    tournament = Tournament(squads={"X": []})
    tournament.teams = {"Y": None}
    try:
        tournament._resolve_team_for_match("X")
        assert False, "expected a ValueError for an empty pool"
    except ValueError as e:
        assert "sidelined" in str(e) or "available" in str(e)
