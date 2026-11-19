"""Verification for the knockout-tiebreak fix (see the plan's "Fix: knockout
matches silently 'decided' a draw by home-side default" section):

- `MatchEngine(decide_winner=True)` plays extra time (full fixed length,
  regardless of scoring during it) -> sudden death (stops instantly on the
  first score change) -> a kicking competition (resolves a still-tied match
  without ever touching the scoreline) instead of just ending level.
- `decide_winner=False` (the default) is a pure no-op - every existing
  round-robin/pool/friendly match can still end in a genuine draw.
- All 5 buggy `rugby_sim/tournament/tournament.py` call sites
  (`run_pool_and_knockout`/`_run_named_pools_and_knockout`,
  `run_nations_championship`'s finals weekend, `run_world_cup_2027`,
  `_run_1999_world_cup`'s playoff round and main knockout loop) now read
  `result.winner` instead of the old `score_home >= score_away` comparison,
  so a tied knockout fixture is decided by the real tiebreak outcome, never
  silently defaulted to the home side.
"""

import pytest

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine.match_engine import (
    EXTRA_TIME_MINUTES,
    MATCH_MINUTES,
    MatchEngine,
    SUDDEN_DEATH_CAP_MINUTES,
)
from rugby_sim.models import Lineup, Team
from rugby_sim.tournament.tournament import Tournament
from rugby_sim.tournament.world_cup_2027 import ALL_TEAMS_2027, POOLS_2027


def make_team(name: str) -> Team:
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = ENGLAND_SAMPLE[0]
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


# ---------------------------------------------------------------------------
# MatchEngine-level: extra time / sudden death / kicking competition
# ---------------------------------------------------------------------------

def test_decide_winner_false_is_a_regression_noop_a_real_draw_still_stands(monkeypatch):
    """`decide_winner=False` (the default) must behave exactly as before
    this feature existed - a tied scoreline at full time just ends the
    match, `winner` is None, and no shootout fields are ever set."""
    home, away = make_team("Home"), make_team("Away")
    monkeypatch.setattr(MatchEngine, "_resolve_drive", lambda self, a, d, m, r: None)

    engine = MatchEngine(home, away, seed=1, decide_winner=False)
    result = engine.run()

    assert engine.minute == MATCH_MINUTES
    assert result.score_home == result.score_away == 0
    assert result.winner is None
    assert result.shootout_winner is None
    assert result.shootout_detail is None


def test_extra_time_plays_its_full_fixed_length_even_if_scoring_changes_early(monkeypatch):
    """A score during extra time must NOT end the match early - extra time
    is always played to its full fixed length (real law: two 10-minute
    periods, no sudden-death behavior inside them)."""
    home, away = make_team("Home"), make_team("Away")
    scored = {"done": False}

    def resolve(self, attacking, defending, minute, result):
        if self._knockout_stage == "extra_time" and not scored["done"]:
            scored["done"] = True
            result.score_home += 7

    monkeypatch.setattr(MatchEngine, "_resolve_drive", resolve)
    engine = MatchEngine(home, away, seed=3, decide_winner=True)
    result = engine.run()

    assert scored["done"], "expected the stubbed early extra-time score to have fired"
    assert engine.minute == MATCH_MINUTES + EXTRA_TIME_MINUTES
    assert result.score_home == 7 and result.score_away == 0
    assert result.shootout_winner is None
    assert result.winner is not None and result.winner.name == home.name


def test_sudden_death_stops_the_instant_the_score_changes(monkeypatch):
    """Unlike extra time, sudden death must end IMMEDIATELY on the first
    score change, well before its own simulation-safety cap."""
    home, away = make_team("Home"), make_team("Away")
    state = {"sudden_death_drives": 0}

    def resolve(self, attacking, defending, minute, result):
        if self._knockout_stage == "sudden_death":
            state["sudden_death_drives"] += 1
            if state["sudden_death_drives"] == 2:
                result.score_away += 3

    monkeypatch.setattr(MatchEngine, "_resolve_drive", resolve)
    engine = MatchEngine(home, away, seed=3, decide_winner=True)
    result = engine.run()

    assert state["sudden_death_drives"] >= 2
    assert engine.minute < MATCH_MINUTES + EXTRA_TIME_MINUTES + SUDDEN_DEATH_CAP_MINUTES
    assert result.score_home == 0 and result.score_away == 3
    assert result.shootout_winner is None
    assert result.winner is not None and result.winner.name == away.name


def test_kicking_competition_resolves_a_still_tied_match_without_touching_the_scoreline(monkeypatch):
    """Engineered to still be tied after the sudden-death cap (scoring
    never happens at all) - must fall through to a real kicking
    competition, which decides a real winner WITHOUT changing the
    (still-tied) scoreline."""
    home, away = make_team("Home"), make_team("Away")
    monkeypatch.setattr(MatchEngine, "_resolve_drive", lambda self, a, d, m, r: None)

    engine = MatchEngine(home, away, seed=5, decide_winner=True)
    result = engine.run()

    assert engine.minute == MATCH_MINUTES + EXTRA_TIME_MINUTES + SUDDEN_DEATH_CAP_MINUTES
    assert result.score_home == result.score_away == 0, (
        "a shootout-decided match must keep its officially tied scoreline"
    )
    assert result.shootout_winner in (home.name, away.name)
    assert result.shootout_detail is not None
    assert result.shootout_detail["home"]["taken"] >= 5
    assert result.shootout_detail["away"]["taken"] >= 5
    assert result.shootout_detail["first_kicker"] in ("home", "away")
    assert result.winner is not None and result.winner.name == result.shootout_winner


def test_kicking_competition_probability_formula_moves_with_goal_kicking_rating():
    """House-style attribute->probability conversion sanity check: a better
    goal-kicker has a strictly higher per-kick success probability than a
    worse one, both inside the [0, 1] range."""
    home, away = make_team("Home"), make_team("Away")
    engine = MatchEngine(home, away, seed=1, decide_winner=True)
    weak = engine._kick_success_probability(10)
    average = engine._kick_success_probability(50)
    strong = engine._kick_success_probability(95)
    assert 0.0 <= weak < average < strong <= 1.0


# ---------------------------------------------------------------------------
# Tournament-level: all 5 buggy call sites, forced to a tied regulation
# scoreline and an engineered AWAY-side shootout win - proving the bracket
# advances on the real decisive result, never silently defaulting to home
# (the old bug: `score_home >= score_away` is True on any tie, so it always
# picked home regardless of what "should" have happened).
# ---------------------------------------------------------------------------

def _force_every_knockout_fixture_to_a_tied_away_win_shootout(monkeypatch):
    """Every match ends 0-0 in normal time (no scoring at all), and any
    kicking competition that gets triggered is stubbed to always hand the
    win to the fixture's AWAY side - deterministic and fast (skips the
    actual kick-by-kick simulation), while still exercising the real
    `decide_winner`/`is_finished`/`winner` plumbing this fix added."""
    monkeypatch.setattr(MatchEngine, "_resolve_drive", lambda self, a, d, m, r: None)

    def fake_shootout(self):
        self.result.shootout_winner = self.away.name
        self.result.shootout_detail = {
            "home": {"taken": 5, "made": 2}, "away": {"taken": 5, "made": 3},
            "first_kicker": "home",
        }

    monkeypatch.setattr(MatchEngine, "_run_kicking_competition", fake_shootout)


def _assert_every_knockout_round_picked_the_away_side(report):
    """For every knockout round in `report.bracket`, the real winner must
    be the fixture's away side (per the forced stub above) - if the old
    `score_home >= score_away` bug were still active, every one of these
    (tied 0-0) would have incorrectly gone to the HOME side instead."""
    assert report.bracket, "expected at least one knockout round to have been played"
    for rnd in report.bracket:
        assert len(rnd.fixtures) == len(rnd.results)
        for fx, result in zip(rnd.fixtures, rnd.results):
            assert result.shootout_winner == fx.away, (
                f"{fx.stage}: {fx.home} v {fx.away} - expected the away side "
                f"({fx.away}) to have been recorded as the winner"
            )
            assert result.winner is not None and result.winner.name == fx.away


def test_run_pool_and_knockout_never_defaults_ties_to_home(monkeypatch):
    _force_every_knockout_fixture_to_a_tied_away_win_shootout(monkeypatch)
    teams = {n: make_team(n) for n in ["A", "B", "C", "D"]}
    report = Tournament(teams).run_pool_and_knockout(pool_count=2, seed=1)

    _assert_every_knockout_round_picked_the_away_side(report)
    final_fixture = report.bracket[-1].fixtures[0]
    assert report.champion == final_fixture.away


def test_run_world_cup_2027_never_defaults_ties_to_home(monkeypatch):
    _force_every_knockout_fixture_to_a_tied_away_win_shootout(monkeypatch)
    teams = {name: make_team(name) for name in ALL_TEAMS_2027}
    report = Tournament(teams).run_world_cup_2027(fixture_mode="specific", seed=1)

    _assert_every_knockout_round_picked_the_away_side(report)
    assert len(report.pools) == 6
    final_fixture = report.bracket[-1].fixtures[0]
    assert report.champion == final_fixture.away


@pytest.mark.slow
def test_run_nations_championship_finals_weekend_never_defaults_ties_to_home(monkeypatch):
    """Covers both the Grand Final AND the 5 placement matches - all 6
    finals-weekend fixtures get `decide_winner=True` per the fix, and every
    one of them (per the forced stub) must resolve to the away side, not
    home."""
    from rugby_sim.data.sources.nations_championship_2026 import NORTH_POOL, SOUTH_POOL

    _force_every_knockout_fixture_to_a_tied_away_win_shootout(monkeypatch)
    teams = {name: make_team(name) for name in sorted(NORTH_POOL | SOUTH_POOL)}
    report = Tournament(teams).run_nations_championship(2026, seed=1)

    assert len(report.bracket) == 1
    finals_round = report.bracket[0]
    assert len(finals_round.fixtures) == 6
    _assert_every_knockout_round_picked_the_away_side(report)

    # The Grand Final result also determines `report.champion`.
    grand_final = finals_round.fixtures[0]
    assert grand_final.stage == "Grand Final"
    assert report.champion == grand_final.away

    # Every finals-weekend match's winner was recorded, not just the Grand
    # Final's (the 5 placement matches get the same plumbing).
    assert len(report.finals_placements) == 6
    for fx in finals_round.fixtures:
        assert report.finals_placements[fx.stage] == fx.away


@pytest.mark.slow
def test_run_1999_world_cup_playoff_and_main_knockout_never_default_ties_to_home(monkeypatch):
    """Covers BOTH remaining call sites in one run: `_run_1999_world_cup`'s
    quarter-final play-off round (3 matches) and its main knockout loop
    (QF/SF/Final) - every one of these must resolve to the away side."""
    from rugby_sim.data.sources.auto_draft import auto_draft_team
    from rugby_sim.data.sources.historical_rwc import get_rwc_year_data

    _force_every_knockout_fixture_to_a_tied_away_win_shootout(monkeypatch)
    _pools, squads = get_rwc_year_data(1999)
    teams = {name: auto_draft_team(name, squad) for name, squad in squads.items()}

    report = Tournament(teams).run_historical_world_cup(1999, seed=1)

    stages = [rnd.stage for rnd in report.bracket]
    assert stages == ["quarter-final play-off", "quarter-final", "semi-final", "final"]
    assert len(report.bracket[0].fixtures) == 3  # the play-off round

    _assert_every_knockout_round_picked_the_away_side(report)
    final_fixture = report.bracket[-1].fixtures[0]
    assert report.champion == final_fixture.away
