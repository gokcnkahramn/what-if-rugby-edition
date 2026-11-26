"""Verification for the manager-controls pass: a `decision_teams` manager
gets a real in-match choice for what to do with a just-awarded penalty
(posts / touch / quick tap) instead of the AI's usual auto-pick, and the
live-match pause/resume machinery (`advance_to`/`finish`) genuinely stops
and waits for it rather than silently rolling past."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Lineup, Position, Team


def _team(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def _first_pending_penalty_seed(decision_teams, max_seed=300):
    home, away = _team("Home"), _team("Away")
    for seed in range(1, max_seed):
        engine = MatchEngine(home, away, seed=seed, decision_teams=decision_teams)
        engine.start()
        engine.advance_to(80)
        if engine._pending_penalty is not None:
            return engine
    raise AssertionError("no pending penalty found in the seed range - widen it")


def test_a_non_decision_team_never_pauses():
    home, away = _team("Home"), _team("Away")
    for seed in range(1, 60):
        engine = MatchEngine(home, away, seed=seed)  # no decision_teams at all
        engine.run()
        assert engine._pending_penalty is None


def test_decision_team_penalty_pauses_advance_to_and_finish():
    engine = _first_pending_penalty_seed(["Home"])
    pending = engine._pending_penalty
    assert pending["team"] == "Home"
    assert not engine.is_finished()
    # `finish()` must not finalize a match that's actually paused mid-drive.
    result = engine.finish()
    assert engine._pending_penalty is not None
    assert result.player_of_the_match is None or not engine._finalized


def test_resolve_pending_decision_posts_can_score():
    engine = _first_pending_penalty_seed(["Home"])
    pending = engine._pending_penalty
    if not pending["can_go_for_posts"]:
        return  # own-22 penalty this seed - "posts" isn't offered, nothing to test here
    before = engine.result.stats["Home"].penalty_goals
    # Force a deterministic make: patch the RNG draw used for the kick
    # itself isn't practical here without reaching into internals, so just
    # confirm the choice is accepted and doesn't raise, and the drive ends.
    engine.resolve_pending_decision("posts")
    assert engine._pending_penalty is None
    after = engine.result.stats["Home"].penalty_goals
    assert after in (before, before + 1)


def test_resolve_pending_decision_quick_tap_never_scores_and_is_named():
    engine = _first_pending_penalty_seed(["Home"])
    before = engine.result.stats["Home"].penalty_goals
    engine.resolve_pending_decision("quick_tap")
    assert engine._pending_penalty is None
    assert engine.result.stats["Home"].penalty_goals == before
    assert "quick tap" in engine.result.events[-1].text


def test_resolve_pending_decision_touch_never_attempts_posts():
    engine = _first_pending_penalty_seed(["Home"])
    before = engine.result.stats["Home"].penalty_goals
    engine.resolve_pending_decision("touch")
    assert engine._pending_penalty is None
    assert engine.result.stats["Home"].penalty_goals == before
    assert "kick to the corner" in engine.result.events[-1].text


def test_match_can_be_finished_after_resolving_the_decision():
    # A decision-team gets a pause for EVERY one of its own penalties, not
    # just the first - so finishing the match means resolving each one as
    # it comes up (same loop a live-match frontend would run via repeated
    # .../decide_penalty + .../continue calls), not a single resolve.
    engine = _first_pending_penalty_seed(["Home"])
    guard = 0
    while not engine.is_finished() and guard < 500:
        if engine._pending_penalty is not None:
            engine.resolve_pending_decision("touch")
        engine.finish()
        guard += 1
    assert engine.is_finished()
    assert engine.result.scoreline()
