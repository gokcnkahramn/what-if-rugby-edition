"""Verification for `team_tactical_identity` (match-engine-depth follow-up:
surfacing a team's existing kick-vs-carry tendency, already used live
mid-match by `MatchEngine._kick_tendency`, as a labeled trait on the
pre-match team sheet / match report)."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine.match_engine import team_tactical_identity
from rugby_sim.models import Attributes, Lineup, Player, Position


def _lineup(attrs=None):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        player = p if attrs is None else Player(
            p.name, p.nation, p.natural_position,
            Attributes(**{**p.attributes.as_dict(), **attrs}),
        )
        lineup.set_starter(player.natural_position, player)
    lineup.captain = lineup.starters[Position.FLY_HALF].player
    return lineup


def test_kick_heavy_lineup_is_labeled_kick_heavy():
    lineup = _lineup(attrs=dict(kicking_game=99, place_kicking_range=99, handling=10, offload=10))
    assert team_tactical_identity(lineup) == "Kick-heavy / territorial"


def test_handling_heavy_lineup_is_labeled_ball_in_hand():
    lineup = _lineup(attrs=dict(kicking_game=10, place_kicking_range=10, handling=99, offload=99))
    assert team_tactical_identity(lineup) == "Ball-in-hand / expansive"


def test_unmodified_sample_squad_is_balanced_or_at_least_a_known_label():
    lineup = _lineup()
    assert team_tactical_identity(lineup) in (
        "Kick-heavy / territorial", "Ball-in-hand / expansive", "Balanced",
    )
