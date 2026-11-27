from rugby_sim.data.sources.auto_draft import auto_draft_team
from rugby_sim.data.sources.historical_six_nations import (
    get_six_nations_year_data,
    parse_six_nations_squads,
)
from rugby_sim.tournament import Tournament

SAMPLE_WIKITEXT = """
==England==

{{nat rs start}}
{{nat rs player|pos=HK|name=[[Alex Hooker]]|age=1|caps=10|club=X}}
{{nat rs player|pos=PR|name=[[Sam Prop|S. Prop]]|age=1|caps=5|club=X}}
{{nat rs player|pos=PR|name=[[Sam Prop|S. Prop]]|age=1|caps=5|club=X}}

==France==

{{nat rs player|pos=FH|name=[[Jo Flyhalf]]|age=1|caps=20|club=Y}}

==Notes==
Some unrelated text that must not be captured as a player.
"""


def test_parse_six_nations_squads_groups_by_team_and_dedupes():
    teams = parse_six_nations_squads(SAMPLE_WIKITEXT)
    assert set(teams.keys()) == {"England", "France"}
    names = [e["name"] for e in teams["England"]]
    assert names == ["Alex Hooker", "S. Prop"]  # dedup keeps the repeated prop once
    assert [e["name"] for e in teams["France"]] == ["Jo Flyhalf"]


def test_2012_six_nations_squads_resolve_to_all_6_teams():
    squads = get_six_nations_year_data(2012)
    assert set(squads.keys()) == {"England", "France", "Ireland", "Italy", "Scotland", "Wales"}
    for name, pool in squads.items():
        assert pool, f"{name} squad came back empty"
        player_names = [p.name for p in pool]
        assert len(player_names) == len(set(player_names)), f"{name} has a duplicate player"
        assert all(p.era == "'12" for p in pool)
        assert all(
            p.data_source in ("historical_wikipedia", "historical_archetype", "rugby08_dataset")
            for p in pool
        )


def test_run_historical_six_nations_2012_end_to_end():
    squads = get_six_nations_year_data(2012)
    teams = {name: auto_draft_team(name, squad) for name, squad in squads.items()}
    for team in teams.values():
        assert team.lineup.validate() == []

    report = Tournament(teams).run_historical_six_nations(2012, seed=3)
    assert report.standings is not None
    assert len(report.standings.table()) == 6
    assert len(report.results) == 15  # 6 choose 2


def test_run_historical_six_nations_requires_every_participant_drafted():
    squads = get_six_nations_year_data(2012)
    teams = {name: auto_draft_team(name, squad) for name, squad in list(squads.items())[:-1]}
    try:
        Tournament(teams).run_historical_six_nations(2012, seed=1)
        assert False, "expected a ValueError for a missing team"
    except ValueError as e:
        assert "Missing a Team" in str(e)


def test_2003_six_nations_resolves_all_6_teams_from_the_season_page():
    """2000-2008: a genuinely richer real source than the squads page
    above - the season article's own real per-match lineup tables (see
    `season_match_pages.py`), which also gives a real fixture order."""
    squads = get_six_nations_year_data(2003)
    assert set(squads.keys()) == {"England", "France", "Ireland", "Italy", "Scotland", "Wales"}
    for name, pool in squads.items():
        assert len(pool) >= 15, f"{name} squad came back too small"
        player_names = [p.name for p in pool]
        assert len(player_names) == len(set(player_names)), f"{name} has a duplicate player"
        assert all(p.era == "'03" for p in pool)


def test_get_six_nations_year_fixtures_returns_a_real_chronological_order():
    from rugby_sim.data.sources.historical_six_nations import get_six_nations_year_fixtures

    fixtures = get_six_nations_year_fixtures(2003)
    assert fixtures
    assert len(fixtures) == 15
    teams = {"England", "France", "Ireland", "Italy", "Scotland", "Wales"}
    for home, away, home_score, away_score in fixtures:
        assert home in teams and away in teams and home != away
        assert isinstance(home_score, int) and isinstance(away_score, int)
    # 2009+ has no real fixture order recoverable from its own source page.
    assert get_six_nations_year_fixtures(2012) is None


def test_run_historical_six_nations_2003_uses_real_fixture_order():
    squads = get_six_nations_year_data(2003)
    teams = {name: auto_draft_team(name, squad) for name, squad in squads.items()}
    report = Tournament(teams).run_historical_six_nations(2003, seed=3)
    assert "real fixture order" in report.name
    assert len(report.results) == 15
