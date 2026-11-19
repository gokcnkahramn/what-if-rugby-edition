"""Tests for `rugby_sim.data.classic_matches_tier_b_rugby_championship` -
the 21-entry Tri Nations (1997-2011) / Rugby Championship (2012-2017)
Tier-B catalog. Lineup resolution hits (cached) Wikipedia + rugbydata, so
these tests are slower than pure-unit tests but exercise the real pipeline,
same as `test_classic_matches.py` presumably does for Tier A's RWC pools.
"""

from __future__ import annotations

import pytest

from rugby_sim.data.classic_matches_tier_b_rugby_championship import (
    TIER_B_RUGBY_CHAMPIONSHIP_MATCHES,
    get_tier_b_match,
    resolve_pools,
)


def test_catalog_has_21_entries():
    assert len(TIER_B_RUGBY_CHAMPIONSHIP_MATCHES) == 21
    years = sorted(m.year for m in TIER_B_RUGBY_CHAMPIONSHIP_MATCHES)
    assert years == list(range(1997, 2018))
    assert 1996 not in years


def test_ids_are_unique():
    ids = [m.id for m in TIER_B_RUGBY_CHAMPIONSHIP_MATCHES]
    assert len(ids) == len(set(ids))


def test_objective_shape_3_base_2_bonus():
    for match in TIER_B_RUGBY_CHAMPIONSHIP_MATCHES:
        base = [o for o in match.objectives if o.tier == "base"]
        bonus = [o for o in match.objectives if o.tier == "bonus"]
        assert len(base) == 3, f"{match.id} has {len(base)} base objectives"
        assert len(bonus) == 2, f"{match.id} has {len(bonus)} bonus objectives"


def test_get_tier_b_match():
    match = get_tier_b_match("rugby_championship_tb_2000")
    assert match is not None
    assert match.display_name.startswith("2000 Tri Nations")
    assert get_tier_b_match("does_not_exist") is None


@pytest.mark.parametrize("match_id,expected_name", [
    ("rugby_championship_tb_2000", "Jonah Lomu"),
    ("rugby_championship_tb_2007", "Dan Carter"),
])
def test_known_real_players_appear(match_id, expected_name):
    match = get_tier_b_match(match_id)
    home_pool, away_pool = resolve_pools(match)
    all_names = {p.name for p in home_pool} | {p.name for p in away_pool}
    assert expected_name in all_names


def test_pools_non_empty_for_every_match():
    for match in TIER_B_RUGBY_CHAMPIONSHIP_MATCHES:
        home_pool, away_pool = resolve_pools(match)
        assert len(home_pool) >= 15, f"{match.id} home pool too small: {len(home_pool)}"
        assert len(away_pool) >= 15, f"{match.id} away pool too small: {len(away_pool)}"
        for p in home_pool + away_pool:
            assert p.data_source in ("historical_wikipedia", "historical_archetype", "legends_curated")
            assert p.name
