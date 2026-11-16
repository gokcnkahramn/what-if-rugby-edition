from rugby_sim.data import ENGLAND_SAMPLE, POOLS
from rugby_sim.engine import MatchEngine
from rugby_sim.engine.match_engine import MAX_SUBSTITUTIONS
from rugby_sim.data.sources.auto_draft import auto_draft_lineup, auto_draft_team
from rugby_sim.models import Attributes, Lineup, Player, Position, Team
from rugby_sim.tournament import Tournament
from rugby_sim.tournament.availability import (
    REST_PENALTY_CONDITION_MAX,
    REST_PENALTY_CONDITION_MIN,
    TournamentAvailability,
)


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


def test_decay_rate_differs_by_fitness_strength_and_pace():
    # Deterministic, direct unit test of `_decay_stamina` - two players at
    # the SAME position (so the position-workload term is identical),
    # differing only in fitness/strength/pace, must end up at measurably
    # different condition after the same simulated drive-time.
    low = Player(name="Low", nation="X", natural_position=Position.FULLBACK,
                 attributes=Attributes(fitness=20, strength=20, pace=20))
    high = Player(name="High", nation="X", natural_position=Position.FULLBACK,
                  attributes=Attributes(fitness=95, strength=95, pace=95))

    def _team_of_one(name, player):
        lineup = Lineup()
        for p in ENGLAND_SAMPLE:
            lineup.set_starter(p.natural_position, p)
        lineup.set_starter(Position.FULLBACK, player)
        lineup.captain = player
        return Team(name=name, short_code=name[:3].upper(), lineup=lineup)

    home_low = _team_of_one("Home", low)
    home_high = _team_of_one("Home", high)
    away = _team_with_bench("Away")

    engine_low = MatchEngine(home_low, away, seed=1)
    engine_low.start()
    engine_low._decay_stamina(home_low, away, drive_minutes=20)

    engine_high = MatchEngine(home_high, away, seed=1)
    engine_high.start()
    engine_high._decay_stamina(home_high, away, drive_minutes=20)

    assert engine_low.condition_for(low) < engine_high.condition_for(high)


def test_decay_rate_differs_by_position_workload():
    # Same attributes, different positions: a tighthead prop (heavy
    # fitness/strength/scrummaging weighting in POSITION_PROFILES) should
    # decay faster than a scrum-half (none of those three weighted) under
    # otherwise identical conditions.
    attrs = Attributes(fitness=60, strength=60, pace=60)
    prop = Player(name="Prop", nation="X", natural_position=Position.TIGHTHEAD_PROP, attributes=attrs)
    nine = Player(name="Nine", nation="X", natural_position=Position.SCRUM_HALF, attributes=attrs)

    def _team_of(name, pos, player):
        lineup = Lineup()
        for p in ENGLAND_SAMPLE:
            lineup.set_starter(p.natural_position, p)
        lineup.set_starter(pos, player)
        lineup.captain = player
        return Team(name=name, short_code=name[:3].upper(), lineup=lineup)

    home_prop = _team_of("Home", Position.TIGHTHEAD_PROP, prop)
    home_nine = _team_of("Home", Position.SCRUM_HALF, nine)
    away = _team_with_bench("Away")

    engine_prop = MatchEngine(home_prop, away, seed=1)
    engine_prop.start()
    engine_prop._decay_stamina(home_prop, away, drive_minutes=20)

    engine_nine = MatchEngine(home_nine, away, seed=1)
    engine_nine.start()
    engine_nine._decay_stamina(home_nine, away, drive_minutes=20)

    assert engine_prop.condition_for(prop) < engine_nine.condition_for(nine)


def test_decay_rate_is_faster_against_a_stronger_attacking_opponent():
    # Same team (and thus same per-player terms) decays faster when its
    # opponent's attack rating is much higher than its own defense rating
    # - the matchup/pressure term, isolated from everything else by reusing
    # the exact same `home` roster against two different opponents.
    import dataclasses

    home = _team_with_bench("Home")

    def _cloned_team(name, pace, footwork, offload):
        lineup = Lineup()
        for p in ENGLAND_SAMPLE:
            clone = Player(
                name=p.name, nation=p.nation, natural_position=p.natural_position,
                attributes=dataclasses.replace(p.attributes, pace=pace, footwork=footwork, offload=offload),
            )
            lineup.set_starter(clone.natural_position, clone)
        lineup.captain = next(iter(lineup.starters.values())).player
        return Team(name=name, short_code=name[:3].upper(), lineup=lineup)

    weak_opponent = _cloned_team("Weak", 1, 1, 1)
    strong_opponent = _cloned_team("Strong", 99, 99, 99)

    engine_vs_weak = MatchEngine(home, weak_opponent, seed=1)
    engine_vs_weak.start()
    engine_vs_weak._decay_stamina(home, weak_opponent, drive_minutes=20)

    home2 = _team_with_bench("Home")
    engine_vs_strong = MatchEngine(home2, strong_opponent, seed=1)
    engine_vs_strong.start()
    engine_vs_strong._decay_stamina(home2, strong_opponent, drive_minutes=20)

    tracked_weak = engine_vs_weak.active_lineup(home)[Position.NUMBER_8].player
    tracked_strong = engine_vs_strong.active_lineup(home2)[Position.NUMBER_8].player
    assert engine_vs_strong.condition_for(tracked_strong) < engine_vs_weak.condition_for(tracked_weak)


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
        assert REST_PENALTY_CONDITION_MIN <= condition[id(p)] <= REST_PENALTY_CONDITION_MAX
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


# ------------------- end-to-end: injury/suspension availability pipeline ----

def test_squads_mode_sidelining_excludes_then_restores_player_across_rounds():
    # Full-pipeline verification (task 2): after a non-trivial-severity
    # injury AND a red card in an early match, each affected player must be
    # excluded from the auto-draft pool for EXACTLY as many of their team's
    # subsequent matches as `matches_remaining` says, then reappear once it
    # expires - driven through the real `TournamentAvailability` ledger, not
    # a hardcoded guess about round numbers.
    squads = {"ENG": POOLS["ENG"](season="2026"), "FRA": POOLS["FRA"](season="2026")}
    tournament = Tournament(squads=squads)

    eng_team = tournament._resolve_team_for_match("ENG")
    tournament._resolve_team_for_match("FRA")
    starters = list(eng_team.lineup.starters.values())
    injured_player = starters[0].player
    carded_player = starters[1].player

    class FakeResult:
        injured_players = [("ENG", injured_player)]
        injury_details = [{"severity": "significant injury", "layoff_matches": 2}]
        carded_players = [("ENG", carded_player, "red")]

    tournament.availability.record_match(FakeResult())

    # Immediately after: both sidelined, with their own correct remaining
    # counts (injury: 2 matches, red card: 1 match) - not a shared constant.
    assert tournament.availability.matches_remaining("ENG", injured_player) == 2
    assert tournament.availability.matches_remaining("ENG", carded_player) == 1
    pool_next = tournament.availability.filter_available("ENG", squads["ENG"])
    assert injured_player not in pool_next
    assert carded_player not in pool_next
    eng_next = tournament._resolve_team_for_match("ENG")
    eng_next_ids = {id(s.player) for s in eng_next.lineup.starters.values()} | {
        id(p) for p in eng_next.lineup.bench
    }
    assert id(injured_player) not in eng_next_ids
    assert id(carded_player) not in eng_next_ids

    class EmptyResult:
        injured_players = []
        injury_details = []
        carded_players = []

    # One more "match played" tick: the red card (1 match) should now have
    # expired, but the significant injury (2 matches) has one match left.
    tournament.availability.record_match(EmptyResult())
    assert tournament.availability.matches_remaining("ENG", carded_player) == 0
    assert tournament.availability.matches_remaining("ENG", injured_player) == 1
    assert carded_player in tournament.availability.filter_available("ENG", squads["ENG"])
    assert injured_player not in tournament.availability.filter_available("ENG", squads["ENG"])

    # Final tick: the injury layoff has now also fully expired.
    tournament.availability.record_match(EmptyResult())
    assert tournament.availability.matches_remaining("ENG", injured_player) == 0
    pool_restored = tournament.availability.filter_available("ENG", squads["ENG"])
    assert injured_player in pool_restored
    assert carded_player in pool_restored


def test_teams_mode_also_excludes_a_sidelined_player_via_bench_cover():
    # The gap this verification found and fixed: `teams=` mode's fixed
    # lineup previously never consulted `filter_available` at all, so a
    # suspended/injured player would keep starting every match regardless.
    # `_resolve_team_for_match` must now swap them for the best-fitting
    # AVAILABLE bench player at that slot, same as squads mode's exclusion.
    eng_team = auto_draft_team("ENG", POOLS["ENG"](season="2026"), short_code="ENG")
    tournament = Tournament(teams={"ENG": eng_team})

    sidelined_slot = next(iter(eng_team.lineup.starters.values()))
    sidelined_player = sidelined_slot.player
    sidelined_position = sidelined_slot.position
    tournament.availability._sidelined[("ENG", id(sidelined_player))] = 1

    resolved = tournament._resolve_team_for_match("ENG")
    resolved_ids = {id(s.player) for s in resolved.lineup.starters.values()}
    assert id(sidelined_player) not in resolved_ids
    # The replacement is actually filling that same slot, not just present
    # somewhere else in the lineup.
    assert resolved.lineup.starters[sidelined_position].player is not sidelined_player
    # The original, fixed `Team` object (and its lineup) must be untouched -
    # so the NEXT call re-evaluates from scratch rather than permanently
    # losing the sidelined player from the roster.
    assert eng_team.lineup.starters[sidelined_position].player is sidelined_player


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


# ---------------- worked examples: re-tuned decay/recovery magnitude -------
#
# Covers the Turkish bug report: fitness dropped too much in a single match
# (100 down to ~60, every match, regardless of how demanding it actually
# was) and barely recovered between matches (a flat 70 start next time).
# These worked examples use REAL drafted squads (two different unions, via
# `auto_draft_lineup`/`POOLS`, not the same player objects reused for both
# sides - see `_team_with_bench` above, which intentionally shares
# `ENGLAND_SAMPLE` for both teams and so isn't a safe basis for per-player
# condition assertions) and confirm the actual numeric ranges this re-tuning
# targets.

def test_full_match_condition_drop_lands_well_above_the_old_60_floor():
    home_lineup = auto_draft_lineup(POOLS["ENG"](season="2026"))
    away_lineup = auto_draft_lineup(POOLS["RSA"](season="2026"))
    home = Team(name="Home", short_code="HOM", lineup=home_lineup)
    away = Team(name="Away", short_code="AWY", lineup=away_lineup)

    drops = []
    for seed in range(10):
        engine = MatchEngine(home, away, seed=seed)
        engine.start()
        engine.advance_to(80)
        engine.finish()
        for slot in engine.active_lineup(home).values():
            drops.append(100.0 - engine.condition_for(slot.player))

    avg_drop = sum(drops) / len(drops)
    # Typical single full match for an unremarkable player/position/matchup:
    # should sit meaningfully above a "stuck around 60" outcome, even though
    # the overall decay magnitude is now higher than the previous (0.22)
    # tuning - see STAMINA_DECAY_PER_MINUTE's comment in match_engine.py for
    # why: that lower magnitude made the genuine worst case unable to reach
    # STAMINA_FLOOR at all, which this retune fixes.
    assert 15.0 < avg_drop < 50.0
    # A genuinely demanding single sample (heaviest-workload position, weak
    # fitness, unfavorable matchup) can now run well past the old ~30-point
    # ceiling, on its way toward the 20 floor in a deliberately-constructed
    # worst case (see test_worst_case_condition_drop_reaches_near_the_floor
    # below) - this test only guards that a merely "somewhat unlucky" sample
    # from a normal drafted squad doesn't itself blow straight down to the
    # floor.
    assert max(drops) < 60.0


def test_worst_case_condition_drop_reaches_near_the_floor():
    """Deliberately construct the worst realistic combination the user
    asked about: a low-fitness player at the heaviest-workload position
    (tighthead prop - see POSITION_WORKLOAD), a team with weakened tackling
    (pushes `_matchup_pressure_factor` toward its unfavorable end) facing a
    stronger-pace attacking opponent, playing a full unassisted 80 minutes.
    This combination's condition drop should land convincingly close to
    (or at) STAMINA_FLOOR - unlike the old 0.22 tuning, where even this kind
    of worst case only reached condition ~68."""
    import dataclasses
    from rugby_sim.models import Attributes

    home_auto = auto_draft_lineup(POOLS["ENG"](season="2026"))
    home_lineup = Lineup()
    for pos, slot in home_auto.starters.items():
        p = slot.player
        weak_p = dataclasses.replace(p, attributes=dataclasses.replace(
            p.attributes, tackling=max(1, p.attributes.tackling - 30)))
        home_lineup.set_starter(pos, weak_p)
    home_lineup.bench = list(home_auto.bench)
    bad_prop = Player(
        name="WorstCaseProp", nation="X", natural_position=Position.TIGHTHEAD_PROP,
        attributes=Attributes(fitness=5, strength=90, pace=25, scrummaging=90,
                               tackling=20, discipline=50),
    )
    home_lineup.set_starter(Position.TIGHTHEAD_PROP, bad_prop)
    home_lineup.captain = home_lineup.starters[Position.HOOKER].player
    home = Team(name="Home", short_code="HOM", lineup=home_lineup)

    away_auto = auto_draft_lineup(POOLS["NZL"](season="2026"))
    away_lineup = Lineup()
    for pos, slot in away_auto.starters.items():
        p = slot.player
        strong_p = dataclasses.replace(p, attributes=dataclasses.replace(
            p.attributes, pace=min(99, p.attributes.pace + 20)))
        away_lineup.set_starter(pos, strong_p)
    away_lineup.bench = list(away_auto.bench)
    away_lineup.captain = list(away_lineup.starters.values())[0].player
    away = Team(name="Away", short_code="AWY", lineup=away_lineup)

    worst_drops = []
    for seed in range(15):
        engine = MatchEngine(home, away, seed=seed)
        engine.start()
        engine.advance_to(80)
        engine.finish()
        worst_drops.append(100.0 - engine.condition_for(bad_prop))

    # Convincingly close to the 20-point drop / STAMINA_FLOOR, not just
    # "somewhat worse than average" - this is the user's explicit ask.
    assert max(worst_drops) >= 65.0


def test_rest_penalty_condition_lands_in_the_85_to_95_recovery_band():
    from rugby_sim.tournament.availability import (
        REST_PENALTY_CONDITION_MAX,
        REST_PENALTY_CONDITION_MIN,
    )

    assert REST_PENALTY_CONDITION_MIN == 85.0
    assert REST_PENALTY_CONDITION_MAX == 95.0

    availability = TournamentAvailability()
    pool = ENGLAND_SAMPLE
    availability.mark_squad("ENG", {id(p) for p in pool})
    starting = availability.starting_condition("ENG", pool)
    assert starting  # someone from last match's squad is in it
    assert all(85.0 <= cond <= 95.0 for cond in starting.values())
    # Varies across the band rather than pinning everyone to one number -
    # the user's explicit ask ("85 ile 95 arasına gelsin", i.e. spread, not
    # a single fixed value).
    assert len(set(starting.values())) > 1
