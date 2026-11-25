"""Verification for real set-piece (scrum/lineout) resolution (match-engine-
depth Phase 5 - see the plan file's "Match engine depth, phase 5" section):
a drive now rolls an explicit "possession origin" (scrum/lineout/open play)
instead of treating every drive as a contested set piece, and a scrum/
lineout drive is resolved via NAMED individual players (a specific hooker's
throw, a specific jumper, a specific front-row pairing), not a team-wide
average."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Attributes, Lineup, Player, Position, Team
from rugby_sim.models.position import CATEGORY_POSITION_GROUPS


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


def test_scrum_and_lineout_counts_land_in_a_plausible_range_per_match():
    # Statistical, many-seed check (RNG noise on one run proves nothing) -
    # these should be single digits to low teens per team, not 0 and not
    # anywhere near the ~32 total drives a match runs (that would mean
    # every single drive was treated as a set piece, the old bug this
    # pass fixed).
    scrums, lineouts, drives = [], [], []
    for seed in range(30):
        home, away = _team("Home"), _team("Away")
        result = MatchEngine(home, away, seed=seed).run()
        scrums.append(result.stats["Home"].scrums_won + result.stats["Away"].scrums_won)
        lineouts.append(result.stats["Home"].lineouts_won + result.stats["Away"].lineouts_won)
        drives.append(result.stats["Home"].possessions + result.stats["Away"].possessions)

    avg_scrums = sum(scrums) / len(scrums)
    avg_lineouts = sum(lineouts) / len(lineouts)
    avg_drives = sum(drives) / len(drives)
    assert 4 <= avg_scrums <= 20
    assert 4 <= avg_lineouts <= 24
    # Not every drive is a set piece - the combined total should be a
    # genuine subset of all drives, not close to all of them.
    assert (avg_scrums + avg_lineouts) < avg_drives


def test_a_much_stronger_scrum_concedes_far_fewer_scrum_penalties():
    # `scrums_won` itself turned out to be the WRONG metric to check this
    # with: the team with the put-in wins their own clean ball the large
    # majority of the time regardless of scrum strength (realistic - most
    # real scrums ARE won by the put-in side), so `scrums_won` barely moves
    # with `scrum_edge` at all (verified: 801 vs 814 over 150 seeds each -
    # no real signal). Scrum dominance shows up in `p_scrum_penalty`
    # instead - a much stronger scrum should concede far FEWER scrum
    # penalties, which is directly, reliably measurable (verified: 14 vs
    # 24 conceded over 60 seeds for this exact attribute pair).
    strong_attrs = dict(scrummaging=95, strength=90)
    weak_attrs = dict(scrummaging=15, strength=15)

    def scrum_penalties_conceded(home_attrs, seeds=60):
        total = 0
        for seed in range(seeds):
            home = _team("Home", attrs=home_attrs)
            away = _team("Away")
            result = MatchEngine(home, away, seed=seed).run()
            total += sum(1 for e in result.events if "at the scrum" in e.text and e.team == "Home")
        return total

    assert scrum_penalties_conceded(strong_attrs) < scrum_penalties_conceded(weak_attrs)


class _ConstFakeRng:
    """A deterministic stand-in for `random.Random` whose `.random()`
    always returns the same high value - high enough to miss every
    probability check in `_resolve_drive`/`_resolve_phase` (card, origin,
    try/penalty/turnover/error), so a drive resolved with this always
    takes the `"open_play"` origin branch and every phase "continues"
    (falls through to the `MAX_PHASES_PER_DRIVE`-exhausted "held up"
    ending) - deterministic, not reliant on finding a lucky seed."""

    def __init__(self, value=0.99):
        self.value = value

    def random(self):
        return self.value

    def choice(self, seq):
        return seq[0]

    def choices(self, population, weights=None, k=1):
        return [population[0]] * k


def test_open_play_origin_drive_never_touches_set_piece_stats():
    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=5)
    engine.start()
    result = engine.result
    engine.rng = _ConstFakeRng(0.99)

    engine._resolve_drive(home, away, 1, result)

    assert result.stats["Home"].scrums_won == 0
    assert result.stats["Home"].lineouts_won == 0
    assert result.stats["Away"].scrums_won == 0
    assert result.stats["Away"].lineouts_won == 0


def test_best_lineout_jumper_and_weakest_scrum_player_are_real_position_holders():
    home = _team("Home")
    engine = MatchEngine(home, home, seed=1)
    engine.start()
    jumper = engine._best_lineout_jumper(home)
    assert jumper is not None
    lineout_group = CATEGORY_POSITION_GROUPS["lineout"]
    jumper_slot = next(s for s in engine._active[home.name].values() if s.player is jumper)
    assert jumper_slot.position in lineout_group

    weakest = engine._weakest_scrum_player(home)
    assert weakest is not None
    scrum_positions = (Position.LOOSEHEAD_PROP, Position.HOOKER, Position.TIGHTHEAD_PROP)
    weakest_slot = next(s for s in engine._active[home.name].values() if s.player is weakest)
    assert weakest_slot.position in scrum_positions
