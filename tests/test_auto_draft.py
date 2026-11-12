from rugby_sim.data import POOLS
from rugby_sim.data.sources.auto_draft import auto_draft_lineup, auto_draft_team
from rugby_sim.models import Position


def test_auto_draft_lineup_fills_all_15_and_validates():
    pool = POOLS["ENG"]()
    lineup = auto_draft_lineup(pool)
    assert len(lineup.starters) == 15
    assert lineup.captain is not None
    assert lineup.validate() == []


def test_auto_draft_lineup_picks_strong_fits_not_just_first_available():
    pool = POOLS["ENG"]()
    lineup = auto_draft_lineup(pool)
    # every slot's occupant should be at least as good a fit at that slot
    # as every other player still left unassigned when it was filled -
    # approximate check: the chosen player's fit beats the pool's median.
    fits = sorted(p.rating_at(Position.FLY_HALF) for p in pool)
    median = fits[len(fits) // 2]
    assert lineup.starters[Position.FLY_HALF].player.rating_at(Position.FLY_HALF) >= median


def test_auto_draft_team_has_a_usable_bench():
    pool = POOLS["FRA"]()
    team = auto_draft_team("France (auto)", pool, short_code="FRA")
    assert team.name == "France (auto)"
    assert len(team.lineup.bench) <= 8
    assert team.lineup.validate() == []
