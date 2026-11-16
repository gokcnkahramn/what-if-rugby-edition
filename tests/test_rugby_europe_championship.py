"""Rugby Europe Championship: real-fixture replay + roster coverage.

See `real_fixtures.py`'s `TOURNAMENTS["rugby_europe_championship"]` comment
and `pool_builder.py`'s `TIER2_WIKI_ONLY_TEAM_IDS` comment for the full
story. In short: this is ONE real competition (8 unions, two 4-team pools
with promotion/relegation + a crossover finals weekend), recovered from
rugbydata via the same team-set+month heuristic every other tournament here
uses. The thing that used to block it from Tournament/Season mode was
roster-building for 3 of the 8 unions (Switzerland/Germany/Poland have no
usable rugbydata player-level data) plus 3 more that were never wired up at
all (Netherlands/Belgium/Russia) - all 6 now resolve a REAL, named
Wikipedia-sourced squad (not an invented archetype roster; every one of the
8 unions' squads traces to a real, named, sourced listing - see
`wikipedia_squad.WIKI_UNION_PAGES`). Romania/Spain separately needed a
roster top-up (rugbydata's box scores for them are real but too thin to
field a full XV) via the same Wikipedia fallback, now wired generally into
`build_union_pool`.
"""
from rugby_sim.data.sources.pool_builder import build_union_pool
from rugby_sim.tournament.real_fixtures import load_real_fixtures
from rugby_sim.tournament.rankings import TeamRankingTracker
from rugby_sim.tournament.season import SeasonPlan, squad_for_team
from rugby_sim.tournament.tournament import Tournament

REC_TEAMS = {
    "Belgium", "Georgia", "Germany", "Netherlands", "Poland",
    "Portugal", "Romania", "Russia", "Spain", "Switzerland",
}


def test_resolves_full_8_team_fixture_set_for_2024():
    fixtures = load_real_fixtures("rugby_europe_championship", "2024")
    assert len(fixtures) == 12
    teams = {f.home for f in fixtures} | {f.away for f in fixtures}
    assert len(teams) == 8
    assert teams <= REC_TEAMS


def test_each_union_resolves_a_non_empty_pool():
    # Switzerland/Germany/Poland/Netherlands/Belgium/Russia: wiki-only
    # (no rugbydata team_id) - real Wikipedia squads.
    for code in ("SUI", "GER", "POL", "NED", "BEL", "RUS"):
        pool = build_union_pool(code, season="2024")
        assert len(pool) >= 15
        # Never a fabricated real name - every player here traces to a
        # cross-referenced-or-archetype Wikipedia entry, never plain
        # "rugbydata" (which would imply a rugbydata box score that these
        # three unions don't have).
        assert all(p.data_source in ("wikipedia", "wikipedia_archetype") for p in pool)

    # Georgia/Portugal already had full rugbydata rosters; Romania/Spain
    # needed the new thin-pool top-up to actually field a team.
    for code in ("GEO", "POR", "ROU", "ESP"):
        pool = build_union_pool(code, season="2024")
        assert len(pool) >= 15


def test_season_plan_includes_rugby_europe_championship_block():
    blocks = SeasonPlan("GEO", 2024)
    block = next((b for b in blocks if b.key == "rugby_europe_championship"), None)
    assert block is not None
    assert block.kind == "real"
    # 2024's actual 8-team split (per `load_real_fixtures`) excludes
    # Switzerland/Russia - they're in other seasons' splits instead (see
    # `real_fixtures.py`'s promotion/relegation note).
    expected_2024 = REC_TEAMS - {"Switzerland", "Russia"}
    assert set(block.team_names) == expected_2024
    for name in expected_2024:
        assert squad_for_team(name, 2024)


def test_simulating_rugby_europe_championship_updates_rankings():
    teams = [
        "Belgium", "Georgia", "Germany", "Netherlands", "Poland",
        "Portugal", "Romania", "Spain",
    ]
    squads = {t: squad_for_team(t, 2024) for t in teams}
    rankings = TeamRankingTracker()
    before = {t: rankings.rating(t) for t in teams}

    tournament = Tournament(squads=squads, rankings=rankings)
    report = tournament.run_real("rugby_europe_championship", season="2024", seed=1)

    assert len(report.results) == 12
    for t in teams:
        assert rankings.rating(t) != before[t]
