"""Verification for defensive organization (match-engine-depth Phase 12):
a team's own `tackle_technique`/`positioning` sub-ratings now derive a
real "blitz vs. drift" defensive style (`MatchEngine._defensive_style`),
with genuinely different effects - blitz raises cards/breakdown turnovers
and compresses the attacking team's territory, drift specifically damps
the attacking team's individual break tries (snipe/wing-break/cross-field)
without the other two effects. Also covers the real bug this phase's own
research uncovered and fixed: `Player.sub_ratings()` never had a
"tackle_technique" key, so `_resolve_drive`'s breakdown-turnover formula
silently read the generic default (50) for every player, never real
attributes, since the feature was first written."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.engine.match_engine import team_defensive_identity
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


BLITZ_ATTRS = dict(tackle_technique=95, positioning=20)
DRIFT_ATTRS = dict(tackle_technique=20, positioning=95)


def test_player_sub_ratings_now_reports_a_real_tackle_technique_and_positioning():
    # Regression guard for the real pre-existing bug this phase found and
    # fixed - these two keys must reflect the player's own attributes, not
    # a flat default.
    player = ENGLAND_SAMPLE[0]
    sub_ratings = player.sub_ratings(player.natural_position)
    assert "tackle_technique" in sub_ratings
    assert "positioning" in sub_ratings
    assert sub_ratings["tackle_technique"] != 50.0 or player.attributes.tackle_technique == 50


def test_team_defensive_identity_labels_blitz_and_drift_correctly():
    assert team_defensive_identity(_team("Home", BLITZ_ATTRS).lineup) == "Blitz / rush defence"
    assert team_defensive_identity(_team("Home", DRIFT_ATTRS).lineup) == "Drift defence"
    assert team_defensive_identity(_team("Home").lineup) in (
        "Blitz / rush defence", "Drift defence", "Balanced",
    )


def test_a_blitz_defence_concedes_more_cards_and_forces_more_turnovers_than_drift():
    # The card gap is modest by design (capped at +30% at full blitz
    # extreme, since the existing discipline-based baseline dominates) -
    # 60 seeds turned out too noisy to separate reliably (11 vs 14 on one
    # run); verified 200 seeds gives a consistent, correctly-directioned
    # gap (46 vs 40) for this exact attribute pair.
    def cards_and_turnovers(away_attrs, seeds=200):
        cards, turnovers = 0, 0
        for seed in range(seeds):
            home, away = _team("Home"), _team("Away", away_attrs)
            result = MatchEngine(home, away, seed=seed).run()
            cards += result.stats["Away"].yellow_cards + result.stats["Away"].red_cards
            turnovers += result.stats["Away"].turnovers_won
        return cards, turnovers

    blitz_cards, blitz_turnovers = cards_and_turnovers(BLITZ_ATTRS)
    drift_cards, drift_turnovers = cards_and_turnovers(DRIFT_ATTRS)
    assert blitz_cards > drift_cards
    assert blitz_turnovers > drift_turnovers


def test_a_drift_defence_suppresses_the_opponents_individual_break_tries_more_than_blitz():
    # match-engine-depth Phase 15 (tactics/strategy system) deliberately
    # gave the cross-field kick its own partial counter-bonus against a
    # drift defence ("attacking the drift" is a real rugby concept - a
    # cross-field ball goes OVER a drifting line, not through it, so it
    # shouldn't be suppressed the same way a ground-level break is) -
    # excluded here on purpose, this check is now specifically about the
    # two break types that ARE still purely ground-level (snipe, wing
    # break), where drift's suppression is undiluted.
    def break_tries(away_attrs, seeds=300):
        total = 0
        for seed in range(seeds):
            home, away = _team("Home"), _team("Away", away_attrs)
            result = MatchEngine(home, away, seed=seed).run()
            total += sum(
                1 for e in result.events
                if e.team == "Home" and ("snipes over" in e.text or "steps the last defender" in e.text)
            )
        return total

    assert break_tries(BLITZ_ATTRS) > break_tries(DRIFT_ATTRS)
