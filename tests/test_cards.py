"""Card-report feature: the second-yellow-same-player-same-match escalation
mechanic, the engine's `card_details`, the web API's `_card_report_json`,
and that only a red (including an escalated one) sidelines a player for a
tournament's next match while a plain yellow does not - the card-report
mirror of `tests/test_stamina_and_swap.py`'s injury-report coverage."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Lineup, Team
from rugby_sim.tournament.availability import TournamentAvailability
from rugby_sim.webapp import _card_report_json


def _team_with_bench(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = ENGLAND_SAMPLE[0]
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


class _FakeRng:
    """A tiny deterministic stand-in for `random.Random` so `_issue_card`'s
    two rolls (which slot gets carded, is it red) are fully controlled -
    no reliance on finding a lucky seed."""

    def __init__(self, red_rolls):
        # `red_rolls`: one float per call to `.random()` for the red/not-red
        # roll - below 0.12 means "red" (see `_issue_card`'s `is_red` roll).
        self._red_rolls = list(red_rolls)

    def random(self):
        return self._red_rolls.pop(0)

    def choice(self, seq):
        return seq[0]  # always the same slot -> always the same player


def test_second_yellow_to_same_player_same_match_escalates_to_red():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    result = engine.result

    # Both rolls are well above 0.12, so neither would be a red on its own -
    # the second one must become red purely from the escalation rule.
    engine.rng = _FakeRng([0.5, 0.5])
    is_red_1, player_1 = engine._issue_card(home, 10, result)
    is_red_2, player_2 = engine._issue_card(home, 20, result)

    assert player_1 is player_2  # same player both times (fake rng always picks slot 0)
    assert is_red_1 is False
    assert is_red_2 is True

    assert len(result.card_details) == 2
    first, second = result.card_details
    assert first["card_type"] == "yellow" and first["escalated_second_yellow"] is False
    assert second["card_type"] == "red" and second["escalated_second_yellow"] is True

    assert ("Home", player_2, "red") in result.carded_players
    assert result.stats["Home"].yellow_cards == 1
    assert result.stats["Home"].red_cards == 1


def test_sent_off_player_cannot_be_carded_again():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    result = engine.result

    # First roll IS a straight red (< 0.12); the fake rng always "picks" the
    # first slot that's still eligible, so once that player is sent off they
    # must drop out of the pool entirely for any later card roll.
    engine.rng = _FakeRng([0.01, 0.01])
    is_red, player = engine._issue_card(home, 5, result)
    assert is_red is True

    # The now-excluded player would otherwise be slot 0 again - confirm the
    # pool handed to `rng.choice` no longer contains them.
    original_choice = engine.rng.choice
    seen_slots = []

    def spy_choice(seq):
        seen_slots.extend(seq)
        return original_choice(seq)

    engine.rng.choice = spy_choice
    engine._issue_card(home, 15, result)
    assert all(slot.player is not player for slot in seen_slots)


def test_only_red_card_sidelines_for_next_tournament_match():
    availability = TournamentAvailability()
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    result = engine.result

    engine.rng = _FakeRng([0.5])  # a plain yellow
    engine._issue_card(home, 10, result)
    availability.record_match(result)
    yellow_player = result.carded_players[0][1]
    assert not availability.is_sidelined("Home", yellow_player)

    result2 = engine.result
    engine.rng = _FakeRng([0.01])  # a straight red for a different player
    bench_free_player_slot = [s for s in engine._active["Home"].values() if s.player is not yellow_player][0]
    engine.rng.choice = lambda seq: bench_free_player_slot
    engine._issue_card(home, 20, result2)
    availability.record_match(result2)
    red_player = bench_free_player_slot.player
    assert availability.is_sidelined("Home", red_player)
    assert availability.matches_remaining("Home", red_player) == 1


def test_escalated_second_yellow_also_sidelines_for_next_match():
    availability = TournamentAvailability()
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    result = engine.result

    engine.rng = _FakeRng([0.5, 0.5])
    engine._issue_card(home, 10, result)
    _, player = engine._issue_card(home, 20, result)  # escalated red

    availability.record_match(result)
    assert availability.is_sidelined("Home", player)
    assert availability.matches_remaining("Home", player) == 1


def test_card_report_json_shape_and_live_matches_remaining():
    availability = TournamentAvailability()
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    result = engine.result

    engine.rng = _FakeRng([0.01])  # straight red
    engine._issue_card(home, 33, result)
    import random as _random
    # Seed picked so the REST of the match (played out with a real RNG from
    # here on) doesn't roll any further cards - this test only wants to
    # check the ONE card it explicitly issued. Re-picked from 99 after the
    # stamina decay re-tuning (see `engine/match_engine.py`
    # STAMINA_DECAY_PER_MINUTE) changed downstream RNG consumption enough to
    # make seed 99 roll a spurious extra yellow card.
    engine.rng = _random.Random(0)
    engine.finish()
    availability.record_match(result)

    report = _card_report_json([result], availability=availability)
    assert len(report) == 1
    entry = report[0]
    assert entry["minute"] == 33
    assert entry["team"] == "Home"
    assert entry["card_type"] == "red"
    assert entry["escalated_second_yellow"] is False
    assert entry["matches_remaining"] == 1
    assert "match_id" in entry and "scoreline" in entry


def test_card_report_json_without_availability_has_no_matches_remaining_field():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    result = engine.result
    engine.rng = _FakeRng([0.5])  # yellow
    engine._issue_card(home, 7, result)
    import random as _random
    # See comment on the same re-seeding above.
    engine.rng = _random.Random(0)
    engine.finish()

    report = _card_report_json([result])
    assert len(report) == 1
    assert "matches_remaining" not in report[0]
