from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.models import Team, Lineup
from rugby_sim.tournament import ALL_TEAMS_2027, POOLS_2027, Tournament, round_robin, pool_stage


def make_team(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = ENGLAND_SAMPLE[0]
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def test_round_robin_fixture_count():
    fixtures = round_robin(["A", "B", "C", "D"])
    assert len(fixtures) == 6  # 4 choose 2


def test_round_robin_each_pair_once():
    fixtures = round_robin(["A", "B", "C", "D", "E", "F"])
    pairs = {frozenset((f.home, f.away)) for f in fixtures}
    assert len(pairs) == len(fixtures) == 15  # 6 choose 2


def test_pool_stage_splits_evenly():
    pools, fixtures = pool_stage(["A", "B", "C", "D"], pool_count=2)
    assert sorted(len(p) for p in pools) == [2, 2]


def test_tournament_round_robin_produces_full_table():
    teams = {n: make_team(n) for n in ["A", "B", "C", "D"]}
    report = Tournament(teams).run_round_robin(seed=1)
    table = report.standings.table()
    assert len(table) == 4
    assert sum(row.played for row in table) == 2 * len(report.results)


def test_tournament_pool_knockout_has_a_champion():
    teams = {n: make_team(n) for n in ["A", "B", "C", "D"]}
    report = Tournament(teams).run_pool_and_knockout(pool_count=2, seed=5)
    assert report.champion in teams


def test_world_cup_2027_pools_have_24_teams_no_overlap():
    assert len(POOLS_2027) == 6
    assert all(len(teams) == 4 for teams in POOLS_2027.values())
    assert len(ALL_TEAMS_2027) == 24
    assert len(set(ALL_TEAMS_2027)) == 24  # no team drawn into two pools


def test_world_cup_2027_runs_specific_and_random_and_crowns_a_champion():
    teams = {name: make_team(name) for name in ALL_TEAMS_2027}
    for fixture_mode in ("specific", "random"):
        report = Tournament(teams).run_world_cup_2027(fixture_mode=fixture_mode, seed=7)
        assert report.champion in ALL_TEAMS_2027
        assert len(report.pools) == 6


def test_world_cup_2027_r16_never_repeats_a_pool_matchup():
    # Regression check for the official third-place permutation table:
    # whichever 4 pools' third-placed teams qualify, no Round-of-16 fixture
    # should pit two teams that were drawn into the same pool.
    team_pool = {name: letter for letter, names in POOLS_2027.items() for name in names}
    teams = {name: make_team(name) for name in ALL_TEAMS_2027}
    for seed in range(5):
        report = Tournament(teams).run_world_cup_2027(fixture_mode="specific", seed=seed)
        r16 = report.bracket[0]
        assert r16.stage == "round-of-16"
        assert len(r16.fixtures) == 8
        for fx in r16.fixtures:
            assert team_pool[fx.home] != team_pool[fx.away]
        # pool play (6 x 6 games) + R16 (8) + QF (4) + SF (2) + final (1)
        assert len(report.results) == 36 + 8 + 4 + 2 + 1
