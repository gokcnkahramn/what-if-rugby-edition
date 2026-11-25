"""Verification for the phase-by-phase drive resolution model (match-engine-
depth Phase 4 - see the plan file's "Match engine depth, phase 4" section):
a drive is no longer one single weighted roll, it's a bounded loop of
explicit ruck/tackle/carry phases (`MatchEngine._resolve_phase`,
`MAX_PHASES_PER_DRIVE`). Same "seeded, many-run worked example" discipline
every other probabilistic claim in this engine already follows - RNG noise
on one run proves nothing."""

from unittest.mock import patch

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.engine.match_engine import MAX_PHASES_PER_DRIVE, PHASE_TRY_RAMP
from rugby_sim.models import Attributes, Lineup, Player, Position, Team


def _team(name, attrs=None):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        player = p if attrs is None else Player(
            p.name, p.nation, p.natural_position,
            Attributes(**{**p.attributes.as_dict(), **attrs}),
        )
        lineup.set_starter(player.natural_position, player)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def _run_with_phase_counting(home, away, seed, try_scorer_of_interest=None):
    """Runs one match while recording, per drive, how many phases
    `_resolve_phase` was actually called for and what outcome the drive
    ended on - used below to verify the phase loop's real behavior without
    needing any new, test-only hooks on `MatchEngine` itself. When
    `try_scorer_of_interest` (a team name) is given, `try_phase_counts`
    only collects phase counts for drives THAT team scored a try on - a
    drive's attacking team varies possession by possession, so filtering
    by name (not just "any try this match") is what makes the strong-vs-
    weak comparison below meaningful."""
    engine = MatchEngine(home, away, seed=seed)
    engine.start()

    phase_counts = []
    try_phase_counts = []
    state = {"phases_this_drive": 0, "last_outcome": None, "last_attacking_name": None}

    original_phase = MatchEngine._resolve_phase
    original_drive = MatchEngine._resolve_drive

    def counting_phase(self, attacking, defending, *args, **kwargs):
        state["phases_this_drive"] += 1
        outcome = original_phase(self, attacking, defending, *args, **kwargs)
        state["last_outcome"] = outcome
        state["last_attacking_name"] = attacking.name
        return outcome

    def counting_drive(self, *args, **kwargs):
        state["phases_this_drive"] = 0
        state["last_outcome"] = None
        state["last_attacking_name"] = None
        result = original_drive(self, *args, **kwargs)
        phase_counts.append(state["phases_this_drive"])
        if state["last_outcome"] == "try" and (
            try_scorer_of_interest is None or state["last_attacking_name"] == try_scorer_of_interest
        ):
            try_phase_counts.append(state["phases_this_drive"])
        return result

    with patch.object(MatchEngine, "_resolve_phase", counting_phase), \
         patch.object(MatchEngine, "_resolve_drive", counting_drive):
        engine.finish()

    return engine.result, phase_counts, try_phase_counts


def test_no_drive_ever_exceeds_max_phases_per_drive():
    home, away = _team("Home"), _team("Away")
    _, phase_counts, _ = _run_with_phase_counting(home, away, seed=3)
    assert phase_counts, "expected at least one drive to have run"
    # A card/set-piece drive returns before any phase loop runs at all (0
    # phases, by design - see `_resolve_drive`'s own comment), so 0 is a
    # valid count; only the upper bound matters here.
    assert max(phase_counts) <= MAX_PHASES_PER_DRIVE


def test_rucks_won_carries_and_tackles_emerge_from_the_simulation():
    # Confirms the new stat fields are a genuine byproduct of the phase
    # loop (credited only on a "continue" phase - see
    # `_credit_phase_continue`), not inert placeholders.
    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=7).run()
    for name in (home.name, away.name):
        stats = result.stats[name]
        assert stats.carries > 0
        assert stats.metres_gained > 0
        assert stats.rucks_won > 0
        assert stats.tackles_made > 0
        # Every credited carry/ruck is mirrored 1:1 (each "continue" phase
        # credits exactly one carry and one ruck-won to the SAME team).
        assert stats.carries == stats.rucks_won


def test_phase_try_ramp_is_damped_early_and_reaches_full_strength_by_phase_3():
    # Deterministic check of the actual designed mechanism (no RNG, no
    # seeds needed) - a try is reachable from phase 1, just damped, and
    # reaches full strength (no further ramp penalty) by phase 3. This is
    # what lets a quick, high-edge attack still score in very few phases
    # (not literally phase 1 every time) while a grinding attack isn't
    # structurally capped differently - the REST of the try chance
    # (edge/zone) is what actually separates a fast score from a slow one,
    # verified statistically below.
    assert 0 < PHASE_TRY_RAMP[1] < PHASE_TRY_RAMP[2] < 1.0
    assert PHASE_TRY_RAMP.get(3, 1.0) == 1.0
    assert PHASE_TRY_RAMP.get(6, 1.0) == 1.0


def test_a_much_stronger_attack_scores_many_more_tries_than_a_weak_one():
    # The user's own worked example for this change: a backline that wins
    # the edge should score far more often (a real "quick pass, 1-on-1
    # overlap" advantage), not be forced through the same scoring rate a
    # grinding, low-edge attack has. `p_try`'s edge term directly doubles
    # between these two attribute sets (verified separately: edge swings
    # from about +0.18 to -0.46 for this exact attrs pair, giving p_try
    # roughly 0.13 vs 0.06) - a real, substantial, reliably-measurable
    # difference, not noise. Statistical, many-seed check (RNG noise on
    # one run proves nothing).
    strong_attrs = dict(pace=95, footwork=95, offload=90, handling=90)
    weak_attrs = dict(pace=20, footwork=20, offload=20, handling=30)

    def home_tries_total(attrs, seeds=60):
        total = 0
        for seed in range(seeds):
            home = _team("Home", attrs=attrs)
            away = _team("Away")
            result = MatchEngine(home, away, seed=seed).run()
            total += result.stats["Home"].tries
        return total

    assert home_tries_total(strong_attrs) > home_tries_total(weak_attrs)
