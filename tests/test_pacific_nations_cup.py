"""Tier 2 coverage: Pacific Nations Cup real-fixture replay.

See `real_fixtures.py`'s `TOURNAMENTS["pacific_nations_cup"]` comment for
why only 2025 has real data in this dataset (2022-2024/2026 have zero rows
for this competition_id) - these tests cover exactly the seasons that
actually exist, honestly, instead of asserting against seasons with none.
"""
from rugby_sim.tournament.real_fixtures import load_real_fixtures
from rugby_sim.tournament.season import SeasonPlan
from rugby_sim.tournament.rankings import TeamRankingTracker
from rugby_sim.tournament.tournament import Tournament
from rugby_sim.data.sources.pool_builder import build_union_pool


def test_pacific_nations_cup_2025_resolves_real_fixtures():
    fixtures = load_real_fixtures("pacific_nations_cup", "2025")
    assert len(fixtures) == 10
    teams = {f.home for f in fixtures} | {f.away for f in fixtures}
    # "Usa" is rugbydata's own spelling; it's canonicalized to the display
    # name "USA" that the rest of the project (rankings seed, squad
    # lookups) actually uses - see `real_fixtures.py`'s `_canonical_name`.
    assert teams == {"Fiji", "Japan", "Samoa", "Tonga", "Canada", "USA"}


def test_pacific_nations_cup_has_historical_coverage_too():
    # Unlike its dedicated competition_id (`d1999468`, only tagged for
    # 2025), team-set+month matching also recovers real 2023/2024 Pacific
    # Nations Cup fixtures tagged under other ids (e.g. generic
    # "International Test Match" ids) - same team-set+month heuristic Six
    # Nations already relies on (see this module's docstring). 2022/2026
    # genuinely have zero matching rows in this dataset, so those two
    # stay empty - honest "no data", not a fabricated fixture list.
    assert load_real_fixtures("pacific_nations_cup", "2022") == []
    assert load_real_fixtures("pacific_nations_cup", "2026") == []
    assert len(load_real_fixtures("pacific_nations_cup", "2023")) > 0
    assert len(load_real_fixtures("pacific_nations_cup", "2024")) > 0


def test_season_plan_includes_pacific_nations_cup_block_for_2025():
    blocks = SeasonPlan("CAN", 2025)
    pnc = next((b for b in blocks if b.key == "pacific_nations_cup"), None)
    assert pnc is not None
    assert pnc.kind == "real"
    for team in ("Fiji", "Japan", "Samoa", "Tonga", "Canada", "USA"):
        assert team in pnc.team_names


def test_simulating_pacific_nations_cup_updates_tier2_union_rankings():
    rankings = TeamRankingTracker()
    tonga_before = rankings.rating("Tonga")
    samoa_before = rankings.rating("Samoa")

    squads = {
        team: build_union_pool(code, season="2025")
        for code, team in [
            ("FIJ", "Fiji"), ("JPN", "Japan"), ("SAM", "Samoa"),
            ("TGA", "Tonga"), ("CAN", "Canada"), ("USA", "USA"),
        ]
    }
    t = Tournament(squads=squads, rankings=rankings)
    t.run_real("pacific_nations_cup", season="2025", seed=1)

    assert rankings.rating("Tonga") != tonga_before or rankings.rating("Samoa") != samoa_before
