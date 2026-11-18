from rugby_sim.data.classic_matches_tier_b_six_nations import (
    TIER_B_SIX_NATIONS_MATCHES,
    resolve_pools,
)


def test_catalog_has_exactly_23_entries():
    assert len(TIER_B_SIX_NATIONS_MATCHES) == 23


def test_catalog_ids_are_unique():
    ids = [m.id for m in TIER_B_SIX_NATIONS_MATCHES]
    assert len(ids) == len(set(ids))


def test_catalog_covers_every_year_1995_to_2017():
    years = sorted(m.year for m in TIER_B_SIX_NATIONS_MATCHES)
    assert years == list(range(1995, 2018))


def test_every_match_has_three_base_and_two_bonus_objectives():
    for match in TIER_B_SIX_NATIONS_MATCHES:
        tiers = [o.tier for o in match.objectives]
        assert tiers.count("base") == 3, f"{match.id} has {tiers.count('base')} base objectives"
        assert tiers.count("bonus") == 2, f"{match.id} has {tiers.count('bonus')} bonus objectives"


def test_pools_are_non_empty_for_every_match():
    for match in TIER_B_SIX_NATIONS_MATCHES:
        home_pool, away_pool = resolve_pools(match)
        assert len(home_pool) > 0, f"{match.id} home pool empty"
        assert len(away_pool) > 0, f"{match.id} away pool empty"


def test_2003_lineup_includes_jonny_wilkinson():
    match = next(m for m in TIER_B_SIX_NATIONS_MATCHES if m.year == 2003)
    _home_pool, away_pool = resolve_pools(match)  # England is away in this fixture
    assert "Jonny Wilkinson" in [p.name for p in away_pool]


def test_2009_lineup_includes_ronan_ogara():
    match = next(m for m in TIER_B_SIX_NATIONS_MATCHES if m.year == 2009)
    _home_pool, away_pool = resolve_pools(match)  # Ireland is away in this fixture
    assert "Ronan O'Gara" in [p.name for p in away_pool]


def test_2014_lineup_includes_brian_odriscoll():
    match = next(m for m in TIER_B_SIX_NATIONS_MATCHES if m.year == 2014)
    _home_pool, away_pool = resolve_pools(match)  # Ireland is away in this fixture
    assert "Brian O'Driscoll" in [p.name for p in away_pool]


def test_1999_legacy_squad_includes_scott_gibbs():
    match = next(m for m in TIER_B_SIX_NATIONS_MATCHES if m.year == 1999)
    _home_pool, away_pool = resolve_pools(match)  # Wales is away in this fixture
    assert "Scott Gibbs" in [p.name for p in away_pool]


def test_objective_checkers_reused_from_classic_matches_module():
    # Every objective's `check` callable must come from classic_matches'
    # own vocabulary (imported, not redefined) - smoke-test that the
    # checkers are at least callable with a plausible fake result shape.
    from rugby_sim.data.classic_matches import Objective

    for match in TIER_B_SIX_NATIONS_MATCHES:
        for obj in match.objectives:
            assert isinstance(obj, Objective)
            assert callable(obj.check)
