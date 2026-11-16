from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.models import Team, Lineup
from rugby_sim.tournament import ALL_TEAMS_2027, POOLS_2027, Tournament, round_robin, pool_stage
from rugby_sim.tournament.availability import TournamentAvailability
from rugby_sim.tournament.rankings import TeamRankingTracker
from rugby_sim.tournament.real_fixtures import TOURNAMENTS, list_tournaments, load_real_fixtures


def test_nations_championship_is_a_registered_tournament_with_12_teams():
    assert "nations_championship" in list_tournaments()
    template = TOURNAMENTS["nations_championship"]
    assert template.name == "Nations Championship"
    assert template.teams == {
        "England", "France", "Ireland", "Scotland", "Wales", "Italy",
        "New Zealand", "Australia", "South Africa", "Argentina",
        "Japan", "Fiji",
    }
    assert template.months == {"07", "11"}


def test_rugby_championship_2026_is_excluded_real_world_calendar_exception():
    # The real 2026 Rugby Championship did not run as a standalone SANZAAR
    # competition - confirmed live (2026-11-16): it was squeezed off the
    # calendar by the All Blacks' Aug-Oct 2026 tour of South Africa, with
    # its 4 unions instead only playing cross-hemisphere Nations
    # Championship matches. Without this guard, the team-set+month
    # heuristic mislabels 3 real bilateral/tour fixtures (Argentina v South
    # Africa 8 Aug, South Africa v New Zealand 22 Aug, Argentina v
    # Australia 29 Aug 2026) as "The Rugby Championship 2026".
    assert load_real_fixtures("rugby_championship", "2026") == []


def test_rugby_championship_other_years_unaffected_by_2026_exclusion():
    # The 2026 guard is a narrow, documented one-off - every other season
    # this dataset covers must keep working exactly as before.
    fixtures = load_real_fixtures("rugby_championship", "2024")
    assert len(fixtures) > 0
    teams = {f.home for f in fixtures} | {f.away for f in fixtures}
    assert teams <= TOURNAMENTS["rugby_championship"].teams


def test_nations_championship_load_real_fixtures_falls_back_to_wikipedia_for_2026():
    # The rugbydata-backed index has no coverage at all for this brand-new
    # 2026 competition (see real_fixtures.py's comment), so
    # load_real_fixtures falls back to the hand-verified Wikipedia fixture
    # list (nations_championship_2026.py) instead of returning []. Expect
    # the 30 played Rounds 1-5 matches plus the 6 scheduled-but-not-yet-
    # played Round 6 matches - no fabricated finals pairings.
    fixtures = load_real_fixtures("nations_championship", "2026")
    assert isinstance(fixtures, list)
    assert len(fixtures) == 36
    dates = [f.date for f in fixtures]
    assert dates == sorted(dates)
    teams = {f.home for f in fixtures} | {f.away for f in fixtures}
    assert teams == TOURNAMENTS["nations_championship"].teams
    # No finals-weekend fixtures (27-29 Nov 2026) - those pairings are
    # ranking-dependent and not yet determined.
    assert all(not d.startswith("202611") or d <= "20261121" for d in dates)


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


def test_shared_rankings_and_availability_persist_across_sequential_tournaments():
    # The core Season-mode mechanism (12c): a shared TeamRankingTracker and
    # TournamentAvailability, passed into two sequential Tournament runs,
    # keep accumulating state across the tournament boundary instead of
    # resetting fresh each time.
    teams = {n: make_team(n) for n in ["A", "B", "C", "D"]}
    shared_rankings = TeamRankingTracker()

    first = Tournament(teams, rankings=shared_rankings)
    first.run_round_robin(seed=1)
    rating_after_first = shared_rankings.rating("A")

    second = Tournament(teams, rankings=shared_rankings)
    assert second.rankings is shared_rankings
    second.run_round_robin(seed=2)
    rating_after_second = shared_rankings.rating("A")

    # Ratings kept moving across the boundary (second run's matches moved
    # "A"'s rating again, starting from where the first run left it), not
    # reset back to the WR_RANKING_SEED/default baseline.
    assert rating_after_second != rating_after_first
    assert shared_rankings.ratings is second.rankings.ratings


def test_tournament_without_shared_rankings_gets_its_own_fresh_tracker():
    teams = {n: make_team(n) for n in ["A", "B", "C", "D"]}
    t1 = Tournament(teams)
    t2 = Tournament(teams)
    assert t1.rankings is not t2.rankings
