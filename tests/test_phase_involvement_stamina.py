"""Verification for per-phase involvement stamina (match-engine-depth Phase
7): a player directly credited with a carry/tackle on a "continue" phase
(see `_credit_phase_continue`) now pays a small EXTRA stamina cost on top
of the existing once-per-drive team-wide decay - so a team's go-to
ball-carrier/tackler genuinely tires faster than a teammate who's rarely
involved, which the old once-per-drive-only model had no way to express."""

from unittest.mock import patch

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.engine.match_engine import PHASE_INVOLVEMENT_STAMINA_COST, STAMINA_FLOOR
from rugby_sim.models import Lineup, Position, Team


def _team(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def test_apply_phase_involvement_stamina_is_small_and_floored():
    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    player = home.lineup.starters[Position.SCRUM_HALF].player

    before = engine.condition_for(player)
    engine._apply_phase_involvement_stamina(player)
    after = engine.condition_for(player)
    assert abs((before - after) - PHASE_INVOLVEMENT_STAMINA_COST) < 1e-9

    # Repeated involvement can't push condition below the documented floor.
    for _ in range(1000):
        engine._apply_phase_involvement_stamina(player)
    assert engine.condition_for(player) == STAMINA_FLOOR


def test_forcing_every_phases_involvement_onto_one_player_lowers_their_final_condition():
    # Same seed, same squads, same simulated outcomes either way (forcing
    # WHO gets picked for stat-crediting purposes never changes the
    # underlying roll/outcome, only the bookkeeping) - the ONLY difference
    # between these two runs is whether one specific player is forced to
    # receive every "continue" phase's carry/tackle involvement credit.
    # Isolates the new mechanism directly: if their final condition is
    # measurably lower in the "forced busy" run than in the plain run,
    # that drop can only be the new per-phase involvement cost.
    engine_plain = MatchEngine(_team("Home"), _team("Away"), seed=9)
    engine_plain.run()
    plain_condition = engine_plain.condition_for(
        engine_plain.home.lineup.starters[Position.OUTSIDE_CENTRE].player
    )

    engine_forced = MatchEngine(_team("Home"), _team("Away"), seed=9)
    forced_target = engine_forced.home.lineup.starters[Position.OUTSIDE_CENTRE].player
    with patch.object(MatchEngine, "_pick_try_scorer", return_value=forced_target), \
         patch.object(MatchEngine, "_pick_defender", return_value=forced_target):
        engine_forced.run()
    forced_condition = engine_forced.condition_for(forced_target)

    assert forced_condition < plain_condition
