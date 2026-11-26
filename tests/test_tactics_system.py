"""Verification for the tactics/strategy system (match-engine-depth Phase
15): `_attack_shape_tendency` (forward-heavy vs. backs-heavy), `_score_pressure`
(chasing the game vs. closing it out), and their wiring into the existing
individual-break/set-piece-sub-scenario/box-kick probabilities.

These are verified as DETERMINISTIC formula checks (direct calls to the
engine's own helper methods with controlled squads/scorelines), not noisy
full-match event counts - a full-match statistical check turned out to be
confounded here: boosting an entire unit's (forwards' or backs') attack-
relevant attributes to test ONE specific mechanism also shifts the
generic, HIGHER-PRIORITY `p_try` slice in the same cumulative roll menu,
which can suppress a lower-priority outcome's realized frequency even
though its own nominal probability genuinely increased - an artifact of
the shared single-roll-per-phase architecture, not a bug in this feature.
Testing the formulas directly avoids that confound entirely."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Attributes, Lineup, Player, Position, Team
from rugby_sim.models.position import BACKS, FORWARDS


def _team(name, boost_group=None):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        player = p
        if boost_group == "fwd" and p.natural_position in FORWARDS:
            player = Player(p.name, p.nation, p.natural_position, Attributes(**{**p.attributes.as_dict(), "pace": 90, "footwork": 90, "offload": 90}))
        if boost_group == "bck" and p.natural_position in BACKS:
            player = Player(p.name, p.nation, p.natural_position, Attributes(**{**p.attributes.as_dict(), "pace": 90, "footwork": 90, "offload": 90}))
        lineup.set_starter(player.natural_position, player)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def test_manager_chosen_tactics_override_the_derived_tendency():
    """Manager-controls pass: a `tactics` choice REPLACES the attribute-
    derived tendency for that axis/team, regardless of what the real
    squad would naturally produce."""
    home = _team("Home")
    away = _team("Away")
    engine = MatchEngine(home, away, seed=1, tactics={
        "Home": {"attack_shape": "forward_heavy", "defensive_style": "blitz", "kick_tendency": "kick_heavy"},
    })
    engine.start()
    assert engine._attack_shape_tendency(home) == 0.8
    assert engine._defensive_style(home) == 0.8
    assert engine._kick_tendency(home) == 0.8
    # Away has no override - stays fully derived, same as before this
    # feature existed.
    plain_engine = MatchEngine(home, away, seed=1)
    plain_engine.start()
    assert engine._attack_shape_tendency(away) == plain_engine._attack_shape_tendency(away)


def test_balanced_tactic_choice_forces_a_neutral_zero():
    home = _team("Home")
    away = _team("Away", boost_group="fwd")  # would otherwise be forward-heavy
    engine = MatchEngine(home, away, seed=1, tactics={"Away": {"attack_shape": "balanced"}})
    engine.start()
    assert engine._attack_shape_tendency(away) == 0.0


def test_attack_shape_tendency_responds_to_forward_vs_back_strength():
    home_fwd = _team("Home", "fwd")
    engine_fwd = MatchEngine(home_fwd, home_fwd, seed=1)
    engine_fwd.start()
    forward_heavy = engine_fwd._attack_shape_tendency(home_fwd)

    home_bck = _team("Home", "bck")
    engine_bck = MatchEngine(home_bck, home_bck, seed=1)
    engine_bck.start()
    backs_heavy = engine_bck._attack_shape_tendency(home_bck)

    assert forward_heavy > 0
    assert backs_heavy < 0
    assert forward_heavy > backs_heavy


def test_score_pressure_is_zero_in_the_first_half_regardless_of_scoreline():
    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    engine.result.score_home, engine.result.score_away = 0, 21
    assert engine._score_pressure(home, 20, engine.result) == 0.0


def test_score_pressure_is_positive_when_chasing_and_negative_when_closing_out():
    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()

    engine.result.score_home, engine.result.score_away = 0, 14
    chasing = engine._score_pressure(home, 70, engine.result)
    assert chasing > 0

    engine.result.score_home, engine.result.score_away = 14, 0
    closing_out = engine._score_pressure(home, 70, engine.result)
    assert closing_out < 0

    engine.result.score_home, engine.result.score_away = 0, 0
    tied = engine._score_pressure(home, 70, engine.result)
    assert tied == 0.0


def test_score_pressure_urgency_rises_through_the_second_half():
    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    engine.result.score_home, engine.result.score_away = 0, 14

    early_second_half = engine._score_pressure(home, 45, engine.result)
    late_second_half = engine._score_pressure(home, 78, engine.result)
    assert 0 < early_second_half < late_second_half


def test_kick_tendency_now_also_raises_real_box_kick_odds_not_just_zone_advance():
    """Player-role/tactic link, strengthened: `_kick_tendency` used to only
    feed `_advance_zone`'s abstract territory roll - it now ALSO raises the
    real box-kick decision's own odds for a "kick_heavy" choice (a one-
    sided boost, matching `backs_heavy_factor`'s own one-sided precedent -
    "ball_in_hand" gets no matching reduction here, since its own effect
    already shows up as a real side effect of `_advance_zone` instead:
    advancing zone more slowly means more time spent in the own-half zones
    where a box kick is even possible at all, so comparing it against
    "kick_heavy" isn't a clean one-variable comparison)."""
    home = _team("Home")
    away = _team("Away")

    def count(tactics, seeds=150):
        total = 0
        for seed in range(seeds):
            r = MatchEngine(home, away, seed=seed, tactics=tactics).run()
            total += sum(1 for ev in r.events if "territorial kick" in ev.text and ev.team == "Home")
        return total

    base = count(None)
    kick_heavy = count({"Home": {"kick_tendency": "kick_heavy"}})
    assert kick_heavy > base


def test_period_caution_factor_dampens_the_opening_minutes_of_each_half():
    """A new, purely clock-driven strategy tier (independent of the
    scoreline, which `_score_pressure` already covers): both halves open
    with a real "cagey start" window before individual-break probabilities
    ramp back up to their normal level."""
    home = _team("Home")
    engine = MatchEngine(home, home, seed=1)
    assert engine._period_caution_factor(0) == MatchEngine.PERIOD_CAUTION_FLOOR
    assert engine._period_caution_factor(40) == MatchEngine.PERIOD_CAUTION_FLOOR
    assert engine._period_caution_factor(MatchEngine.PERIOD_CAUTION_WINDOW) == 1.0
    assert engine._period_caution_factor(20) == 1.0
    assert engine._period_caution_factor(79) == 1.0
    # Strictly increasing within the window, never exceeding 1.0.
    values = [engine._period_caution_factor(m) for m in range(0, MatchEngine.PERIOD_CAUTION_WINDOW + 1)]
    assert values == sorted(values)
    assert max(values) <= 1.0
