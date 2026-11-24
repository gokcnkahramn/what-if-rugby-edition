"""Verification for the engine's field-position model (see
`MatchEngine.Zone`/`_advance_zone`/`_zone_relative_to`, `MATCH_ENGINE_MODEL.md`
item 3): a 5-zone (HOME_TRYLINE/HOME_22/MIDFIELD/AWAY_22/AWAY_TRYLINE)
territory tracker that gates try/penalty-kick probability, plus the
lateral `Side` dimension (LEFT/MIDDLE/RIGHT) that biases which wing scores
a try - and the `zone` field every `CommentaryEvent` carries."""

from collections import Counter

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.engine.match_engine import Side, Zone
from rugby_sim.models import Attributes, Lineup, Player, Position, Team

ALL_ZONES = ("home_tryline", "home_22", "midfield", "away_22", "away_tryline")


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


def _relative_zone(zone: str, is_home_event: bool) -> str:
    idx = ALL_ZONES.index(zone)
    distance_from_attacking_end = (4 - idx) if is_home_event else idx
    return {
        0: "attacking_tryline", 1: "attacking_22", 2: "midfield",
        3: "own_22", 4: "own_tryline",
    }[distance_from_attacking_end]


def test_zone_starts_at_midfield():
    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=1)
    engine.start()
    assert engine._zone == Zone.MIDFIELD
    assert engine._side == Side.MIDDLE


def test_strong_attack_advances_zone_more_often_than_a_weak_one():
    # A statistical, many-seed check (RNG noise on one run proves nothing,
    # same discipline as this engine's other worked-example tests) - a
    # heavily weakened attacking side should spend much more of the match
    # pinned near its own line than a full-strength one.
    weak_attrs = dict(pace=15, footwork=15, offload=15, handling=15, tackling=15, scrummaging=15, discipline=50)
    pinned_zones = (Zone.HOME_TRYLINE, Zone.HOME_22)

    def pinned_share(attacking_attrs):
        pinned_ticks = 0
        total_ticks = 0
        for seed in range(40):
            home = _team("Home", attrs=attacking_attrs)
            away = _team("Away")
            engine = MatchEngine(home, away, seed=seed)
            engine.start()
            for _ in range(60):
                engine._advance_zone(home, away, edge=(
                    engine._team_sub_rating(home, "attack") - engine._team_sub_rating(away, "tackling")
                ) / 100)
                total_ticks += 1
                if engine._zone in pinned_zones:
                    pinned_ticks += 1
        return pinned_ticks / total_ticks

    weak_pinned_share = pinned_share(weak_attrs)
    strong_pinned_share = pinned_share(None)
    assert weak_pinned_share > strong_pinned_share


def test_try_rate_is_much_higher_near_the_attacking_line_than_pinned_in_own_territory():
    buckets = Counter()
    for seed in range(100):
        home, away = _team("Home"), _team("Away")
        result = MatchEngine(home, away, seed=seed).run()
        for e in result.events:
            if not e.text.startswith("TRY!"):
                continue
            buckets[_relative_zone(e.zone, e.team == home.name)] += 1

    total = sum(buckets.values())
    assert total > 20, "expected plenty of simulated tries across 100 seeds"
    attacking_end = buckets["attacking_tryline"] + buckets["attacking_22"]
    own_end = buckets["own_22"] + buckets["own_tryline"]
    assert attacking_end > own_end * 5


def test_commentary_events_carry_a_zone_and_a_side():
    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=7).run()
    assert result.events
    assert all(e.zone in ALL_ZONES for e in result.events)
    assert all(e.side in ("left", "middle", "right") for e in result.events)


def test_penalty_kicks_at_posts_are_never_attempted_pinned_in_own_territory():
    # `_score_penalty_chance` is zone-gated (closes `MATCH_ENGINE_MODEL.md`
    # item 3's "deep territory heuristics omitted for simplicity" note) -
    # pinned in their own 22 OR right on their own try line, a side should
    # always kick for territory instead, regardless of kicker skill.
    at_posts = Counter()
    to_corner = Counter()
    for seed in range(80):
        home, away = _team("Home"), _team("Away")
        result = MatchEngine(home, away, seed=seed).run()
        for e in result.events:
            is_posts = "kicks the penalty" in e.text or "penalty attempt is off target" in e.text
            is_corner = "kick to the corner" in e.text
            if not (is_posts or is_corner):
                continue
            rel = _relative_zone(e.zone, e.team == home.name)
            (at_posts if is_posts else to_corner)[rel] += 1

    assert at_posts["own_22"] == 0
    assert at_posts["own_tryline"] == 0
    assert to_corner["own_22"] > 0 or to_corner["own_tryline"] > 0
    assert at_posts["attacking_22"] > 0


def test_wet_weather_increases_handling_errors_and_reduces_tries():
    def avg_errors_and_tries(weather, n=50):
        errors = tries = 0
        for seed in range(n):
            home, away = _team("Home"), _team("Away")
            result = MatchEngine(home, away, seed=seed, weather=weather).run()
            for stats in result.stats.values():
                errors += stats.handling_errors
                tries += stats.tries
        return errors / n, tries / n

    dry_errors, dry_tries = avg_errors_and_tries("dry")
    wet_errors, wet_tries = avg_errors_and_tries("wet")
    assert wet_errors > dry_errors
    assert wet_tries < dry_tries


def test_kicking_heavy_team_advances_zone_faster_than_a_handling_heavy_team():
    def away_zone_share(attrs, n=40):
        ticks = total = 0
        for seed in range(n):
            home = _team("Home", attrs=attrs)
            away = _team("Away")
            engine = MatchEngine(home, away, seed=seed)
            engine.start()
            for _ in range(60):
                edge = (
                    engine._team_sub_rating(home, "attack") - engine._team_sub_rating(away, "tackling")
                ) / 100
                engine._advance_zone(home, away, edge)
                total += 1
                if engine._zone in (Zone.AWAY_22, Zone.AWAY_TRYLINE):
                    ticks += 1
        return ticks / total

    kicking_heavy = away_zone_share(dict(kicking_game=95, handling=30))
    handling_heavy = away_zone_share(dict(kicking_game=30, handling=95))
    assert kicking_heavy > handling_heavy


def test_side_moves_off_middle_over_many_drives():
    home, away = _team("Home"), _team("Away")
    engine = MatchEngine(home, away, seed=5)
    engine.start()
    seen = set()
    for _ in range(80):
        engine._advance_side()
        seen.add(engine._side)
    assert seen == {Side.LEFT, Side.MIDDLE, Side.RIGHT}


def test_try_scorer_is_biased_toward_the_wing_matching_the_current_side():
    home, away = _team("Home"), _team("Away")
    counts = Counter()
    for seed in range(300):
        home, away = _team("Home"), _team("Away")
        engine = MatchEngine(home, away, seed=seed)
        engine.start()
        engine._side = Side.LEFT
        scorer = engine._pick_try_scorer(home)
        counts["left_at_left_side"] += int(scorer.natural_position == Position.LEFT_WING)
        engine._side = Side.MIDDLE
        scorer = engine._pick_try_scorer(home)
        counts["left_at_middle_side"] += int(scorer.natural_position == Position.LEFT_WING)

    assert counts["left_at_left_side"] > counts["left_at_middle_side"]
