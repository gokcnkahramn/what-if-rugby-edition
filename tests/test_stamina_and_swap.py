from rugby_sim.data import ENGLAND_SAMPLE, POOLS
from rugby_sim.engine import MatchEngine
from rugby_sim.engine.match_engine import MAX_SUBSTITUTIONS
from rugby_sim.data.sources.auto_draft import auto_draft_lineup, auto_draft_team
from rugby_sim.models import Attributes, Lineup, Player, Position, Team
from rugby_sim.tournament import Tournament
from rugby_sim.tournament.availability import REST_PENALTY_CONDITION, TournamentAvailability


def _team_with_bench(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = ENGLAND_SAMPLE[0]
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


# -------------------------- item 2: positional swaps -----------------------

def test_swap_positions_exchanges_the_two_players_and_logs_an_event():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()

    fly_half = engine.active_lineup(home)[Position.FLY_HALF].player
    fullback = engine.active_lineup(home)[Position.FULLBACK].player
    assert engine.swap_positions(home, Position.FLY_HALF, Position.FULLBACK) is True

    active = engine.active_lineup(home)
    assert active[Position.FLY_HALF].player is fullback
    assert active[Position.FULLBACK].player is fly_half
    assert engine.result.stats[home.name].substitutions == 0  # not a substitution
    swap_events = [e for e in engine.result.events if "Positional swap" in e.text]
    assert swap_events


def test_swap_positions_rejects_same_position_or_unfilled_slot():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    assert engine.swap_positions(home, Position.FLY_HALF, Position.FLY_HALF) is False

    # Vacate a slot (simulate "no cover left" style empty slot) and confirm
    # a swap involving it is rejected rather than crashing.
    del engine._active[home.name][Position.FULLBACK]
    assert engine.swap_positions(home, Position.FLY_HALF, Position.FULLBACK) is False


def test_swap_positions_does_not_consume_a_substitution_slot():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    for _ in range(3):
        engine.swap_positions(home, Position.FLY_HALF, Position.FULLBACK)
    assert engine.result.stats[home.name].substitutions == 0
    assert engine._subs_used[home.name] == 0


# -------------------------- item 3: stamina/fatigue -------------------------

def test_friendly_match_everyone_starts_at_full_condition():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    for slot in engine.active_lineup(home).values():
        assert engine.condition_for(slot.player) == 100.0


def test_stamina_decays_as_the_match_progresses():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=3)
    engine.start()
    tracked_player = engine.active_lineup(home)[Position.NUMBER_8].player
    assert engine.condition_for(tracked_player) == 100.0
    engine.advance_to(80)
    engine.finish()
    # Over a full match, a starter who played throughout must have lost at
    # least some condition (never gains it back mid-match).
    assert engine.condition_for(tracked_player) < 100.0


def test_stamina_affects_team_sub_rating():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=3)
    engine.start()
    fresh_rating = engine._team_sub_rating(home, "attack")
    engine.advance_to(80)
    tired_rating = engine._team_sub_rating(home, "attack")
    assert tired_rating <= fresh_rating


def test_initial_condition_seeds_a_below_100_starting_stamina():
    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    starter = ENGLAND_SAMPLE[0]
    engine = MatchEngine(home, away, seed=1, initial_condition={id(starter): 70.0})
    engine.start()
    assert engine.condition_for(starter) == 70.0
    # anyone not in the dict still starts fresh
    other = ENGLAND_SAMPLE[1]
    assert engine.condition_for(other) == 100.0


def test_auto_draft_prefers_a_fresher_player_when_ratings_are_close():
    # Position.LOOSEHEAD_PROP is the first position auto_draft_lineup fills
    # (enum declaration order), so with only 2 candidates it's decided
    # before anything else about the rest of the lineup.
    tired = Player(name="Tired Starter", nation="X", natural_position=Position.LOOSEHEAD_PROP,
                    attributes=Attributes(scrummaging=90, strength=90, tackling=90, fitness=90,
                                           agility=90, discipline=90))
    fresh = Player(name="Fresh Backup", nation="X", natural_position=Position.LOOSEHEAD_PROP,
                    attributes=Attributes(scrummaging=84, strength=84, tackling=84, fitness=84,
                                           agility=84, discipline=84))
    assert tired.rating_at(Position.LOOSEHEAD_PROP) > fresh.rating_at(Position.LOOSEHEAD_PROP)

    pool = [tired, fresh]
    condition = {id(tired): 20.0, id(fresh): 100.0}  # tired is near the stamina floor
    lineup = auto_draft_lineup(pool, bench_size=1, condition=condition)
    assert lineup.starters[Position.LOOSEHEAD_PROP].player is fresh


def test_auto_draft_without_condition_is_unaffected_friendly_and_draft_mode():
    lineup_a = auto_draft_lineup(list(ENGLAND_SAMPLE))
    lineup_b = auto_draft_lineup(list(ENGLAND_SAMPLE), condition=None)
    for pos in lineup_a.starters:
        assert lineup_a.starters[pos].player is lineup_b.starters[pos].player


# ------------------ item 3: tournament rest bookkeeping ---------------------

def test_tournament_availability_tracks_rest_between_matches():
    availability = TournamentAvailability()
    pool = POOLS["ENG"](season="2026")
    availability.mark_squad("ENG", {id(p) for p in pool[:23]})

    condition = availability.starting_condition("ENG", pool)
    for p in pool[:23]:
        assert condition[id(p)] == REST_PENALTY_CONDITION
    # a player never selected into last match's squad isn't penalized
    assert id(pool[-1]) not in condition or pool[-1] in pool[:23]


def test_squads_mode_tournament_runs_with_rest_bookkeeping_wired_through():
    # End-to-end smoke check: a squads-mode round robin still runs fine with
    # the new condition bookkeeping threaded through `_resolve_team_for_match`
    # /`_play` (item 3's tournament integration) - not asserting exact
    # numbers (randomized match outcomes), just that nothing breaks and the
    # availability ledger actually recorded a squad.
    squads = {code: POOLS[code](season="2026") for code in ["ENG", "FRA", "IRE", "SCO"]}
    tournament = Tournament(squads=squads)
    report = tournament.run_round_robin(seed=5)
    assert len(report.results) == 6
    assert tournament.availability._last_squad  # at least one team's squad was recorded


# ------------------- item 4: AI-only squads-mode fixtures still get injuries
# sidelined for their NEXT match (confirms the existing design actually works
# end-to-end, not just architecturally) ---------------------------------

def test_ai_only_fixture_injury_sidelines_player_for_that_teams_next_match():
    squads = {"ENG": POOLS["ENG"](season="2026"), "FRA": POOLS["FRA"](season="2026")}
    tournament = Tournament(squads=squads)  # no my_team/pause_hook - a fully AI/auto-simmed fixture
    import rugby_sim.engine.match_engine as me
    original = me.P_INJURY_PER_DRIVE
    original_tiers = me.INJURY_SEVERITY_TIERS
    me.P_INJURY_PER_DRIVE = 1.0  # force at least one injury per drive, deterministically
    # Also force every injury's rolled severity tier to one with a non-zero
    # layoff (since severity now varies - see INJURY_SEVERITY_TIERS - a
    # "knock" rolls 0 matches missed, which would make this test about
    # sidelining flaky/meaningless; this test is specifically about the
    # sidelining mechanism, not severity distribution, so it pins severity).
    me.INJURY_SEVERITY_TIERS = (("muscle strain", 1.0, 1),)
    try:
        eng_team = tournament._resolve_team_for_match("ENG")
        fra_team = tournament._resolve_team_for_match("FRA")
        result = MatchEngine(eng_team, fra_team, seed=11).run()
        tournament.availability.record_match(result)
    finally:
        me.P_INJURY_PER_DRIVE = original
        me.INJURY_SEVERITY_TIERS = original_tiers

    injured_eng = [p for team_name, p in result.injured_players if team_name == "ENG"]
    assert injured_eng, "expected at least one ENG injury with P_INJURY_PER_DRIVE forced to 1.0"

    # The same mechanism `_resolve_team_for_match` uses for every squads-mode
    # team, human-picked or AI-auto-drafted alike (no special-casing) -
    # confirms item 4: an AI-only fixture's injury really does sideline that
    # player from ENG's pool for their next match.
    available_next = tournament.availability.filter_available("ENG", squads["ENG"])
    assert injured_eng[0] not in available_next


# ------------------- injury severity tiers --------------------------------

def test_injury_severity_tiers_are_a_named_inspectable_table():
    from rugby_sim.engine.match_engine import INJURY_SEVERITY_TIERS

    names = [tier[0] for tier in INJURY_SEVERITY_TIERS]
    assert len(names) == len(set(names))  # no duplicate tier names
    assert len(INJURY_SEVERITY_TIERS) >= 3
    for name, weight, layoff in INJURY_SEVERITY_TIERS:
        assert isinstance(name, str) and name
        assert weight > 0
        assert isinstance(layoff, int) and layoff >= 0
    # weights don't need to sum to 1 (rng.choices normalizes), but at least
    # one tier should cost a real match - otherwise "severity" would never
    # actually mean anything for availability bookkeeping.
    assert any(layoff > 0 for _, _, layoff in INJURY_SEVERITY_TIERS)


def test_apply_injury_records_a_severity_and_layoff_from_the_table():
    from rugby_sim.engine.match_engine import INJURY_SEVERITY_TIERS

    home, away = _team_with_bench("Home"), _team_with_bench("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    result = engine.result
    position, slot = next(iter(engine.active_lineup(home).items()))
    engine._apply_injury(home, 10, result)

    assert len(result.injury_details) == 1
    detail = result.injury_details[0]
    assert detail["severity"] in {name for name, _, _ in INJURY_SEVERITY_TIERS}
    layoff_by_name = {name: layoff for name, _, layoff in INJURY_SEVERITY_TIERS}
    assert detail["layoff_matches"] == layoff_by_name[detail["severity"]]


# ------------------- live "matches until return" bookkeeping ---------------

def test_matches_remaining_is_live_and_decreases_as_further_matches_are_played():
    availability = TournamentAvailability()
    pool = POOLS["ENG"](season="2026")
    victim = pool[0]

    class InjuryResult:
        injured_players = [("ENG", victim)]
        injury_details = [{"severity": "serious injury", "layoff_matches": 3}]
        carded_players = []

    class EmptyResult:
        injured_players = []
        injury_details = []
        carded_players = []

    availability.record_match(InjuryResult())
    assert availability.matches_remaining("ENG", victim) == 3

    availability.record_match(EmptyResult())
    assert availability.matches_remaining("ENG", victim) == 2
    availability.record_match(EmptyResult())
    assert availability.matches_remaining("ENG", victim) == 1
    availability.record_match(EmptyResult())
    assert availability.matches_remaining("ENG", victim) == 0
    assert not availability.is_sidelined("ENG", victim)


# ------------------- teams=-mode condition carryover ------------------------

def test_teams_mode_tournament_also_tracks_rest_penalty_condition():
    # Previously only squads= mode threaded condition bookkeeping through
    # `_resolve_team_for_match`; a fixed lineup reused every match should
    # ALSO show its players getting less rested as fixtures pile up.
    from rugby_sim.data.sources.auto_draft import auto_draft_team

    eng_team = auto_draft_team("ENG", POOLS["ENG"](season="2026"), short_code="ENG")
    fra_team = auto_draft_team("FRA", POOLS["FRA"](season="2026"), short_code="FRA")
    tournament = Tournament(teams={"ENG": eng_team, "FRA": fra_team})

    # First match: nobody's been selected into a squad yet, so no penalty -
    # `_pending_condition` is populated fresh by this very call, so check it
    # BEFORE calling `_resolve_team_for_match`, which immediately marks this
    # squad as selected for the sake of the match AFTER this one.
    assert not tournament.availability._last_squad.get("ENG")
    resolved = tournament._resolve_team_for_match("ENG")
    assert resolved is eng_team
    assert tournament._pending_condition["ENG"] == {}  # nobody was in a PREVIOUS squad yet
    assert tournament.availability._last_squad.get("ENG")  # now recorded as selected

    # Resolve it again (simulating this same fixed lineup playing its next
    # match): the same starters, having been in the last match's squad,
    # should now carry the short-rest penalty - the exact mechanism squads
    # mode already had, now applying to a fixed lineup too.
    tournament._resolve_team_for_match("ENG")
    second_condition = tournament._pending_condition["ENG"]
    assert second_condition  # non-empty: someone now starts below 100
    starter_ids = {id(slot.player) for slot in eng_team.lineup.starters.values()}
    assert any(pid in second_condition for pid in starter_ids)
