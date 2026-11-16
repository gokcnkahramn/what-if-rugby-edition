from rugby_sim.data.sources.nations_championship_2026 import (
    CODE_TO_NATION,
    NORTH_POOL,
    SOUTH_POOL,
    fetch_nations_championship_2026_fixtures,
    parse_fixtures,
)
from rugby_sim.data.sources.wikipedia_squad import fetch_wikitext
from rugby_sim.tournament.real_fixtures import TOURNAMENTS, load_real_fixtures
from rugby_sim.tournament.tournament import Tournament


def test_parse_fixtures_real_wikitext():
    # Same convention as test_uncapped_pool.py: parse against the real
    # (live-or-disk-cached) wikitext rather than a hand-typed fixture,
    # since this module's whole job is staying honest about what the
    # live page actually says.
    wikitext = fetch_wikitext("2026 Nations Championship")
    assert wikitext, "expected to fetch the 2026 Nations Championship wikitext (live or disk-cached)"

    fixtures = parse_fixtures(wikitext)
    assert len(fixtures) == 36  # Rounds 1-5 (30) + Round 6 (6), no finals

    rounds = sorted({f.round_no for f in fixtures})
    assert rounds == [1, 2, 3, 4, 5, 6]

    played = [f for f in fixtures if f.played]
    unplayed = [f for f in fixtures if not f.played]
    assert len(played) == 30
    assert len(unplayed) == 6
    assert all(f.round_no == 6 for f in unplayed)
    assert all(f.date == "20261121" for f in unplayed)

    # Spot-check a real Round 1 result and a real Round 5 result.
    r1 = next(f for f in fixtures if f.round_no == 1 and f.home == "New Zealand")
    assert r1.away == "France" and r1.date == "20260704" and r1.played

    r5 = next(f for f in fixtures if f.round_no == 5 and f.home == "England")
    assert r5.away == "Japan" and r5.date == "20261114" and r5.played

    # No fabricated finals-weekend fixtures.
    assert all(f.date <= "20261121" for f in fixtures)

    # Every parsed team name maps onto the registered tournament's team set.
    names = {f.home for f in fixtures} | {f.away for f in fixtures}
    assert names == set(CODE_TO_NATION.values())
    assert names == TOURNAMENTS["nations_championship"].teams


def test_fetch_nations_championship_2026_fixtures_matches_parse_fixtures():
    wikitext = fetch_wikitext("2026 Nations Championship")
    assert wikitext
    assert fetch_nations_championship_2026_fixtures() == parse_fixtures(wikitext)


def test_load_real_fixtures_falls_back_to_wikipedia_with_no_fabricated_finals():
    fixtures = load_real_fixtures("nations_championship", "2026")
    assert len(fixtures) == 36
    dates = [f.date for f in fixtures]
    assert dates == sorted(dates)
    assert all(f.competition_id == "nations_championship_2026_wikipedia" for f in fixtures)
    # Finals weekend is 27-29 Nov 2026 - must not appear.
    assert all(not d.startswith("202611") or int(d[6:8]) <= 21 for d in dates)


def test_run_real_nations_championship_2026_end_to_end():
    from rugby_sim.data.sources.pool_builder import ALL_TEAM_IDS, build_season_pool

    code_by_nation = {nation: code for code, (_, _, nation) in ALL_TEAM_IDS.items()}
    squads = {}
    for nation in TOURNAMENTS["nations_championship"].teams:
        code = code_by_nation.get(nation)
        squads[nation] = build_season_pool(code, 2026) if code else []

    tournament = Tournament(squads=squads)
    report = tournament.run_real("nations_championship", season="2026", seed=7)

    assert len(report.results) == 36
    assert report.standings is not None
    played_teams = {r.home.name for r in report.results} | {r.away.name for r in report.results}
    assert played_teams == TOURNAMENTS["nations_championship"].teams


def _nations_championship_squads():
    from rugby_sim.data.sources.pool_builder import ALL_TEAM_IDS, build_season_pool

    code_by_nation = {nation: code for code, (_, _, nation) in ALL_TEAM_IDS.items()}
    squads = {}
    for nation in TOURNAMENTS["nations_championship"].teams:
        code = code_by_nation.get(nation)
        squads[nation] = build_season_pool(code, 2026) if code else []
    return squads


def test_run_nations_championship_produces_round_robin_plus_finals_weekend():
    tournament = Tournament(squads=_nations_championship_squads())
    report = tournament.run_nations_championship(2026, seed=11)

    # 36 round-robin results + 6 finals-weekend results.
    assert len(report.results) == 42
    assert report.pools is not None
    assert set(report.pools.keys()) == {"North", "South"}
    assert len(report.bracket) == 1
    finals_round = report.bracket[0]
    assert len(finals_round.fixtures) == 6
    assert len(finals_round.results) == 6
    assert finals_round.fixtures[0].stage == "Grand Final"
    assert all(fx.stage != "Grand Final" for fx in finals_round.fixtures[1:])
    assert report.champion in (NORTH_POOL | SOUTH_POOL)


def test_run_nations_championship_pool_tables_have_six_teams_each_with_bonus_points():
    tournament = Tournament(squads=_nations_championship_squads())
    report = tournament.run_nations_championship(2026, seed=23)

    north_table = report.pools["North"].table()
    south_table = report.pools["South"].table()
    assert {row.team for row in north_table} == set(NORTH_POOL)
    assert {row.team for row in south_table} == set(SOUTH_POOL)
    assert len(north_table) == 6
    assert len(south_table) == 6
    # Every pool member played exactly 6 round-robin matches (one against
    # each member of the OTHER pool), and table points are plain win/draw
    # bonus-point arithmetic (reusing standings.py's own math).
    for row in north_table + south_table:
        assert row.played == 6
        assert row.table_points == (
            row.won * 4 + row.drawn * 2 + row.try_bonus_points + row.losing_bonus_points
        )


def test_run_nations_championship_finals_pairings_match_simulated_rank_order():
    tournament = Tournament(squads=_nations_championship_squads())
    report = tournament.run_nations_championship(2026, seed=23)

    north_table = report.pools["North"].table()
    south_table = report.pools["South"].table()
    finals_fixtures = report.bracket[0].fixtures

    # Finals weekend pairs each pool's Nth-ranked side with the other
    # pool's Nth-ranked side - derived from THIS run's own simulated
    # standings order, not a fixed/hardcoded pairing.
    assert len(finals_fixtures) == len(north_table) == len(south_table) == 6
    for rank, fx in enumerate(finals_fixtures):
        assert fx.home == north_table[rank].team
        assert fx.away == south_table[rank].team


def test_run_nations_championship_live_progress_pools_are_never_merged():
    """Regression test for the bug where a MID-TOURNAMENT progress snapshot
    (`instance.current_pools`, what `_tournament_progress_json` in
    `webapp.py` reads for the live/interactive web UI) showed the SAME
    merged ~10-team list in both the North and South pool tables, instead
    of each pool's table containing only its own 6 real members, because
    `run_nations_championship` only pruned `pool_standings` back to each
    pool's own teams once, AFTER the whole round-robin loop finished -
    during the loop itself (i.e. whenever something reads
    `tournament.current_pools` mid-run, exactly like the live web UI does),
    every cross-pool result had already been added to BOTH pools'
    `Standings` objects unpruned.

    This hooks `Tournament._play` (every real fixture goes through it) and,
    after each of the first several fixtures, snapshots
    `tournament.current_pools` the same way an interactive progress poll
    would - asserting at every single step, not just at the end, that each
    pool's table has exactly its own 6 members and sane (non-inflated)
    played counts.
    """
    tournament = Tournament(squads=_nations_championship_squads())
    snapshots = []
    orig_play = tournament._play

    def spying_play(home_name, away_name, seed=None):
        result = orig_play(home_name, away_name, seed)
        pools = tournament.current_pools
        if pools and set(pools.keys()) == {"North", "South"}:
            snapshots.append({
                name: {row.team for row in standings.table()}
                for name, standings in pools.items()
            })
        return result

    tournament._play = spying_play
    tournament.run_nations_championship(2026, seed=7)

    # At least the 36 round-robin fixtures should have produced a snapshot
    # (the finals-weekend matches also go through `_play`, but by then
    # `current_pools` still holds the same, already-correct, pool tables).
    assert len(snapshots) >= 36
    for snap in snapshots:
        assert snap["North"] == set(NORTH_POOL)
        assert snap["South"] == set(SOUTH_POOL)
        # Never the same merged set in both tables.
        assert snap["North"] != snap["South"]
