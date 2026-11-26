"""Verification for the referee system (match-engine-depth Phase 13):
knock-on/forward pass and offside/not-releasing are now distinct, named
infringements (previously both lumped under one generic "handling error"/
"at the breakdown" text), and a real advantage concept exists - the
referee doesn't blow immediately on a penalty if the attack was already
about to score anyway."""

from collections import Counter

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Lineup, Position, Team


def _team(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def _event_text_counts(seeds=60):
    counts = Counter()
    for seed in range(seeds):
        home, away = _team("Home"), _team("Away")
        result = MatchEngine(home, away, seed=seed).run()
        for e in result.events:
            if "knock-on" in e.text:
                counts["knock_on"] += 1
            if "forward pass" in e.text:
                counts["forward_pass"] += 1
            if "for offside" in e.text:
                counts["offside"] += 1
            if "not releasing" in e.text:
                counts["not_releasing"] += 1
            if "plays advantage" in e.text:
                counts["advantage_try"] += 1
    return counts


def test_handling_errors_are_named_knock_on_or_forward_pass_not_one_generic_text():
    counts = _event_text_counts()
    assert counts["knock_on"] > 0
    assert counts["forward_pass"] > 0
    # Knock-ons should be the more common of the two real infringements.
    assert counts["knock_on"] > counts["forward_pass"]


def test_general_play_penalties_are_named_offside_or_not_releasing():
    counts = _event_text_counts()
    assert counts["offside"] > 0
    assert counts["not_releasing"] > 0


def test_advantage_is_a_real_mechanic_that_sometimes_produces_a_try_instead_of_a_penalty():
    counts = _event_text_counts()
    assert counts["advantage_try"] > 0


def test_old_generic_at_the_breakdown_text_is_gone_from_general_play_penalties():
    # The old version always wrote the same generic text for every
    # general-play penalty - confirm the new named reasons have actually
    # replaced it, not just been added alongside it.
    for seed in range(20):
        home, away = _team("Home"), _team("Away")
        result = MatchEngine(home, away, seed=seed).run()
        for e in result.events:
            if "Penalty against" in e.text:
                assert "for offside" in e.text or "not releasing" in e.text or "at the scrum" in e.text
