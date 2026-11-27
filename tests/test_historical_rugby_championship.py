"""Verification for the new historical Rugby Championship/Tri Nations
full-season replay (1996-2025) - real per-match lineup tables AND a real
chronological fixture order, both parsed straight off each season's own
Wikipedia article (see `season_match_pages.py`)."""

from rugby_sim.data.sources.auto_draft import auto_draft_team
from rugby_sim.data.sources.historical_rugby_championship import (
    AVAILABLE_RUGBY_CHAMPIONSHIP_YEARS,
    get_rugby_championship_year_data,
)
from rugby_sim.tournament import Tournament


def test_available_years_span_1996_to_2025():
    assert AVAILABLE_RUGBY_CHAMPIONSHIP_YEARS[0] == 1996
    assert AVAILABLE_RUGBY_CHAMPIONSHIP_YEARS[-1] == 2025
    assert 2026 not in AVAILABLE_RUGBY_CHAMPIONSHIP_YEARS  # absorbed into Nations Championship


def test_2015_resolves_all_4_teams_with_a_real_fixture_order():
    squads, fixtures = get_rugby_championship_year_data(2015)
    assert set(squads.keys()) == {"New Zealand", "Australia", "South Africa", "Argentina"}
    for name, pool in squads.items():
        assert len(pool) >= 15, f"{name} squad came back too small"
        player_names = [p.name for p in pool]
        assert len(player_names) == len(set(player_names)), f"{name} has a duplicate player"
        assert all(p.era == "'15" for p in pool)
    assert fixtures
    teams = set(squads.keys())
    for home, away, home_score, away_score in fixtures:
        assert home in teams and away in teams and home != away
        assert isinstance(home_score, int) and isinstance(away_score, int)


def test_2020_handles_a_real_3_team_edition_honestly():
    """South Africa genuinely withdrew from the real 2020 Rugby
    Championship (COVID-19) - a real historical fact, not a parsing gap."""
    squads, fixtures = get_rugby_championship_year_data(2020)
    assert set(squads.keys()) == {"New Zealand", "Australia", "Argentina"}
    assert fixtures


def test_run_historical_rugby_championship_end_to_end():
    squads, _fixtures = get_rugby_championship_year_data(2015)
    teams = {name: auto_draft_team(name, squad) for name, squad in squads.items()}
    for team in teams.values():
        assert team.lineup.validate() == []

    report = Tournament(teams).run_historical_rugby_championship(2015, seed=3)
    assert "real fixture order" in report.name
    assert report.standings is not None
    assert len(report.standings.table()) == 4
    assert len(report.results) == 6  # 2015 was a shortened, single-round-robin RWC year


def test_run_historical_rugby_championship_requires_every_participant_drafted():
    squads, _fixtures = get_rugby_championship_year_data(2015)
    teams = {name: auto_draft_team(name, squad) for name, squad in list(squads.items())[:-1]}
    try:
        Tournament(teams).run_historical_rugby_championship(2015, seed=1)
        assert False, "expected a ValueError for a missing team"
    except ValueError as e:
        assert "Missing a Team" in str(e)
