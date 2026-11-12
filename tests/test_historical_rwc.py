from rugby_sim.data.sources.auto_draft import auto_draft_team
from rugby_sim.data.sources.historical_rwc import get_rwc_year_data, parse_rwc_squads
from rugby_sim.tournament import Tournament

SAMPLE_SQUADS_WIKITEXT = """
==Pool A==

===Testland===

Head coach: {{flagicon|TST}} Someone

{{nat rs start}}
{{nat rs player|pos=HK|name={{sortname|Alex|Hooker}}|age=1|caps=10|club=X}}
{{nat rs player|pos=PR|name={{sortname|Sam|Prop}}|age=1|caps=5|club=X}}
{{nat rs player|pos=PR|name={{sortname|Sam|Prop}}|age=1|caps=5|club=X}}

===Otherland===

{{nat rs player|pos=FH|name={{sortname|Jo|Flyhalf}}|age=1|caps=20|club=Y}}

==Pool B==

===Thirdland===

{{nat rs player|pos=WG|name={{sortname|Pat|Winger}}|age=1|caps=8|club=Z}}

==Notes==
Some unrelated text that must not be captured as a player.
"""


def test_parse_rwc_squads_groups_by_pool_and_team_and_dedupes():
    pools = parse_rwc_squads(SAMPLE_SQUADS_WIKITEXT)
    assert set(pools.keys()) == {"Pool A", "Pool B"}
    assert set(pools["Pool A"].keys()) == {"Testland", "Otherland"}
    assert set(pools["Pool B"].keys()) == {"Thirdland"}

    testland = pools["Pool A"]["Testland"]
    names = [f"{e['first']} {e['last']}" for e in testland]
    assert names == ["Alex Hooker", "Sam Prop"]  # the repeated prop line is deduped

    otherland = pools["Pool A"]["Otherland"]
    assert [f"{e['first']} {e['last']}" for e in otherland] == ["Jo Flyhalf"]


def test_2003_world_cup_squads_resolve_to_20_real_teams():
    pools, squads = get_rwc_year_data(2003)
    all_teams = {name for teams in pools.values() for name in teams}
    assert len(all_teams) == 20
    assert all_teams == set(squads.keys())
    for name, pool in squads.items():
        assert pool, f"{name} squad came back empty"
        player_names = [p.name for p in pool]
        assert len(player_names) == len(set(player_names)), f"{name} has a duplicate player"
        assert all(p.era == "'03" for p in pool)
        assert all(p.data_source in ("historical_wikipedia", "historical_archetype") for p in pool)


def test_run_historical_world_cup_2003_end_to_end():
    pools, squads = get_rwc_year_data(2003)
    teams = {name: auto_draft_team(name, squad) for name, squad in squads.items()}
    for team in teams.values():
        assert team.lineup.validate() == []

    report = Tournament(teams).run_historical_world_cup(2003, seed=7)
    assert report.champion in teams
    assert len(report.pools) == 4
    for standings in report.pools.values():
        assert len(standings.table()) == 5
    # 4 pools x (5 choose 2)=10 matches + QF(4) + SF(2) + Final(1)
    assert len(report.results) == 4 * 10 + 4 + 2 + 1


def test_run_historical_world_cup_requires_every_participant_drafted():
    pools, squads = get_rwc_year_data(2003)
    teams = {name: auto_draft_team(name, squad) for name, squad in list(squads.items())[:-1]}
    try:
        Tournament(teams).run_historical_world_cup(2003, seed=1)
        assert False, "expected a ValueError for a missing team"
    except ValueError as e:
        assert "Missing a Team" in str(e)


def test_run_1999_world_cup_uses_the_real_5_pool_playoff_format():
    pools, squads = get_rwc_year_data(1999)
    assert len(pools) == 5
    teams = {name: auto_draft_team(name, squad) for name, squad in squads.items()}

    report = Tournament(teams).run_historical_world_cup(1999, seed=5)
    stages = [rnd.stage for rnd in report.bracket]
    assert stages == ["quarter-final play-off", "quarter-final", "semi-final", "final"]

    playoff = report.bracket[0]
    assert len(playoff.fixtures) == 3
    qf = report.bracket[1]
    assert len(qf.fixtures) == 4
    # no match in the play-off round replays a pool-stage pairing (same
    # two teams meeting twice in the pool stage, then again here)
    pool_pairs = set()
    for pool_name, pool_teams in pools.items():
        for i, a in enumerate(pool_teams):
            for b in pool_teams[i + 1:]:
                pool_pairs.add(frozenset((a, b)))
    for fx in playoff.fixtures:
        assert frozenset((fx.home, fx.away)) not in pool_pairs
    assert report.champion in teams
