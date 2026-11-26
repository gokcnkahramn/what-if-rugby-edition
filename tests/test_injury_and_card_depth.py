"""Verification for match-engine-depth Phase 14 (condition/injury/card
depth, the user's third checklist): fatigue-scaled + fatigue-weighted
injury risk, named injury types (with a real concussion-protocol rule),
position-specific card/injury impact, and a return-from-injury
conditioning deficit."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.engine.commentary import CommentaryEvent
from rugby_sim.engine.match_engine import (
    INJURY_SEVERITY_TIERS,
    INJURY_TYPES,
    MatchResult,
    TeamMatchStats,
)
from rugby_sim.models import Attributes, Lineup, Player, Position, Team
from rugby_sim.tournament.availability import (
    RETURN_FROM_INJURY_CONDITION_MAX,
    RETURN_FROM_INJURY_CONDITION_MIN,
    TournamentAvailability,
)


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


def test_team_fatigue_factor_rises_as_tracked_condition_drops():
    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    assert engine._team_fatigue_factor(home) == 0.0
    for pid in list(engine._stamina.keys()):
        engine._stamina[pid] = 20.0
    assert engine._team_fatigue_factor(home) > 0.0


def test_a_fatigued_team_suffers_more_injuries_than_a_fresh_one():
    # Statistical, many-seed check (RNG noise on one run proves nothing) -
    # force the home team to start every drive exhausted and confirm it
    # racks up more injuries than a team that stays fresh.
    def total_injuries(force_tired, seeds=60):
        total = 0
        for seed in range(seeds):
            home, away = _team("Home"), _team("Away")
            engine = MatchEngine(home, away, seed=seed)
            engine.start()
            if force_tired:
                for pid in list(engine._stamina.keys()):
                    if pid in [id(s.player) for s in engine._active[home.name].values()]:
                        engine._stamina[pid] = 15.0
            engine.finish()
            total += engine.result.stats[home.name].injuries
        return total

    assert total_injuries(force_tired=True) > total_injuries(force_tired=False)


def test_injury_types_table_is_named_and_real_concussions_always_carry_a_layoff():
    names = [t[0] for t in INJURY_TYPES]
    assert "concussion" in names
    assert len(names) == len(set(names))
    assert all(weight > 0 for _, weight in INJURY_TYPES)

    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=3)
    engine.start()
    result = engine.result
    for _ in range(200):
        engine._apply_injury(home, 10, result)
    concussions = [d for d in result.injury_details if d["type"] == "concussion"]
    assert concussions, "expected at least one concussion across 200 rolls"
    assert all(d["layoff_matches"] > 0 for d in concussions)


def test_a_sent_off_prop_hurts_scrum_rating_more_than_a_flat_penalty_alone_would():
    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    before = engine._team_sub_rating(home, "scrum")
    engine._sent_off_positions[home.name].append(Position.TIGHTHEAD_PROP)
    after = engine._team_sub_rating(home, "scrum")
    assert after < before
    # A category this position doesn't contribute to (kicking - scrum-half/
    # fly-half/fullback only) should be unaffected by losing a prop.
    before_kicking = engine._team_sub_rating(away, "kicking")
    engine._sent_off_positions[away.name].append(Position.TIGHTHEAD_PROP)
    after_kicking = engine._team_sub_rating(away, "kicking")
    assert after_kicking == before_kicking


def test_return_from_injury_conditioning_deficit_applies_once_then_clears():
    availability = TournamentAvailability()
    player = ENGLAND_SAMPLE[0]
    pool = list(ENGLAND_SAMPLE)

    result = MatchResult(home=_team("Home"), away=_team("Away"))
    result.stats = {"Home": TeamMatchStats(), "Away": TeamMatchStats()}
    result.injured_players = [("Home", player)]
    result.injury_details = [{
        "minute": 10, "team": "Home", "player": player.name,
        "position": player.natural_position.value, "type": "knee injury",
        "severity": "significant injury", "layoff_matches": 2,
    }]
    availability.record_match(result)
    assert availability.matches_remaining("Home", player) == 2

    # Tick the layoff down with two more empty results (no new injuries).
    for _ in range(2):
        empty = MatchResult(home=_team("Home"), away=_team("Away"))
        empty.stats = {"Home": TeamMatchStats(), "Away": TeamMatchStats()}
        availability.record_match(empty)

    assert availability.matches_remaining("Home", player) == 0
    condition = availability.starting_condition("Home", pool)
    assert id(player) in condition
    assert RETURN_FROM_INJURY_CONDITION_MIN <= condition[id(player)] <= RETURN_FROM_INJURY_CONDITION_MAX

    # Consumed - the NEXT match no longer carries the deficit.
    condition_again = availability.starting_condition("Home", pool)
    assert id(player) not in condition_again


def test_a_red_card_suspension_does_not_trigger_the_injury_return_deficit():
    availability = TournamentAvailability()
    player = ENGLAND_SAMPLE[1]
    pool = list(ENGLAND_SAMPLE)

    result = MatchResult(home=_team("Home"), away=_team("Away"))
    result.stats = {"Home": TeamMatchStats(), "Away": TeamMatchStats()}
    result.carded_players = [("Home", player, "red")]
    availability.record_match(result)
    assert availability.matches_remaining("Home", player) == 1

    empty = MatchResult(home=_team("Home"), away=_team("Away"))
    empty.stats = {"Home": TeamMatchStats(), "Away": TeamMatchStats()}
    availability.record_match(empty)
    assert availability.matches_remaining("Home", player) == 0

    condition = availability.starting_condition("Home", pool)
    assert id(player) not in condition
