from rugby_sim import webapp
from rugby_sim.data.national_teams import POOLS
from rugby_sim.data.sources.pool_builder import NATION_DISPLAY, NON_RANKED_CODES
from rugby_sim.tournament.rankings import TeamRankingTracker


def test_lions_and_pacific_islanders_are_registered_pools():
    assert "LIO" in POOLS
    assert "PAC" in POOLS
    assert NATION_DISPLAY["LIO"] == "British & Irish Lions"
    assert NATION_DISPLAY["PAC"] == "Pacific Islanders"
    assert {"BAR", "LIO", "PAC"} <= NON_RANKED_CODES


def test_lions_pool_is_real_and_non_trivial():
    pool = POOLS["LIO"]()
    assert len(pool) >= 30
    names = [p.name for p in pool]
    assert len(names) == len(set(names))
    # Real, well-known 2025 tour squad members.
    assert any(p.name == "Maro Itoje" for p in pool)
    # Every player keeps their own real national eligibility - selection
    # for the Lions doesn't change it.
    nations = {p.nation for p in pool}
    assert nations <= {"England", "Ireland", "Scotland", "Wales"}


def test_pacific_islanders_pool_is_real_and_non_trivial():
    pool = POOLS["PAC"]()
    assert len(pool) >= 20
    names = [p.name for p in pool]
    assert len(names) == len(set(names))
    nations = {p.nation for p in pool}
    assert nations <= {"Fiji", "Samoa", "Tonga"}


def test_non_ranked_sides_excluded_from_team_form():
    rankings = TeamRankingTracker()
    rankings.record_result("Barbarians", "New Zealand", 20, 30)
    rankings.record_result("British & Irish Lions", "Australia", 24, 24)
    rankings.record_result("Pacific Islanders", "Wales", 10, 40)
    team_form = webapp._team_form_json(rankings, [])
    teams = {row["team"] for row in team_form}
    assert not (teams & {"Barbarians", "British & Irish Lions", "Pacific Islanders"})
    # The real opponents still show up normally.
    assert {"New Zealand", "Australia", "Wales"} <= teams
