"""Verification for the match stats/analysis system (match-engine-depth
Phase 16): every new stat is credited at the exact point the engine
already resolves that real outcome (no new rolls), and the new DERIVED
percentages (possession/scrum/lineout/kicking/try-conversion/red-zone)
stay internally consistent with their underlying raw counts."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
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


def test_new_team_stats_are_non_negative_and_internally_consistent():
    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=7).run()
    for name in (home.name, away.name):
        s = result.stats[name]
        assert s.defenders_beaten >= 0
        assert s.turnovers_conceded >= 0
        assert s.rucks_lost >= 0
        # NOT `scrums_contested >= scrums_won`/`lineouts_contested >=
        # lineouts_won` - a real, pre-existing (not new) design fact this
        # seed happened to finally expose: `_won` can be credited to the
        # DEFENDING team on a steal "against the head"/a lineout turnover
        # (see `_resolve_scrum`/`_resolve_lineout`), while `_contested`
        # only ever credits the ATTACKING team's own throw/put-in - so a
        # team's own `_won` total can legitimately exceed its own
        # `_contested` total once enough of its wins came from stealing
        # the OTHER team's ball, not its own. The real, always-true
        # invariant is across both teams combined instead.
        assert s.kicks_attempted >= s.kicks_successful
        assert s.red_zone_possessions >= s.red_zone_tries
        if s.kicks_successful:
            assert s.kicking_metres > 0
    # The real, always-true invariant: every contested scrum/lineout is won
    # by EXACTLY ONE of the two teams (whether that's the throwing/put-in
    # team keeping it, or the other team stealing it) - so the totals
    # across BOTH teams combined must match exactly.
    home_s, away_s = result.stats[home.name], result.stats[away.name]
    assert home_s.scrums_won + away_s.scrums_won == home_s.scrums_contested + away_s.scrums_contested
    assert home_s.lineouts_won + away_s.lineouts_won == home_s.lineouts_contested + away_s.lineouts_contested


def test_defenders_beaten_is_rare_for_an_even_matchup_and_common_for_a_dominant_attack():
    # Statistical check (many seeds) - confirms the threshold is reachable
    # for a genuinely stronger attack, not an unreachable constant (a real
    # bug caught during this feature's own development: the first draft
    # threshold, 8, turned out to NEVER fire under this engine's real edge
    # range, even for a heavily boosted attack).
    dominant_attrs = dict(pace=95, footwork=95, offload=95)

    def total_defenders_beaten(attrs, seeds=30):
        total = 0
        for seed in range(seeds):
            home = _team("Home", attrs)
            away = _team("Away")
            result = MatchEngine(home, away, seed=seed).run()
            total += result.stats["Home"].defenders_beaten
        return total

    assert total_defenders_beaten(dominant_attrs) > total_defenders_beaten(None)


def test_turnovers_conceded_mirrors_the_opponents_turnovers_won():
    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=3).run()
    # Every turnover the engine credits to one team as "won" has a real,
    # matching "conceded" on the other side (breakdown turnover, handling
    # error, scrum-against-the-head, lineout steal, box-kick charge-down
    # all credit both sides together - see each branch's own comment) -
    # confirmed as an exact match, not just "both non-zero".
    assert result.stats["Home"].turnovers_won == result.stats["Away"].turnovers_conceded
    assert result.stats["Away"].turnovers_won == result.stats["Home"].turnovers_conceded


def test_performance_score_rewards_non_scoring_involvement_not_just_points():
    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=7).run()
    non_scorers_with_stats = [
        ps for ps in result.player_stats
        if ps.tries == 0 and ps.conversions == 0 and ps.penalty_goals == 0 and ps.drop_goals == 0
        and (ps.carries > 0 or ps.tackles_made > 0)
    ]
    assert non_scorers_with_stats, "expected at least one non-scoring player with real involvement"
    assert any(ps.performance_score > 0 for ps in non_scorers_with_stats)


def test_webapp_stats_json_exposes_consistent_derived_percentages():
    from rugby_sim.webapp import _team_stats_json

    home, away = _team("Home"), _team("Away")
    result = MatchEngine(home, away, seed=7).run()
    stats = _team_stats_json(result)

    total_pct = stats["Home"]["possession_pct"] + stats["Away"]["possession_pct"]
    assert abs(total_pct - 100.0) < 0.2

    for name in ("Home", "Away"):
        s = stats[name]
        if s["scrums_contested"]:
            expected = round(100 * s["scrums_won"] / s["scrums_contested"], 1)
            assert s["scrum_success_rate"] == expected
        else:
            assert s["scrum_success_rate"] is None
        if s["tries"]:
            expected_conv = round(100 * s["conversions"] / s["tries"], 1)
            assert s["try_conversion_rate"] == expected_conv
        else:
            assert s["try_conversion_rate"] is None
