"""Quick demo entry point.

    python -m rugby_sim.cli

Builds two lineups (one standard England XV, one "what if" XV where Jonah
Lomu starts at fullback instead of the wing), then simulates a match.
"""

from __future__ import annotations

from .data import ENGLAND_SAMPLE, LEGENDS
from .engine import MatchEngine
from .models import Team, Lineup, Position


def build_standard_england() -> Team:
    lineup = Lineup()
    for player in ENGLAND_SAMPLE:
        lineup.set_starter(player.natural_position, player)
    lineup.captain = next(p for p in ENGLAND_SAMPLE if p.name == "Maro Itoje")
    return Team(name="England", short_code="ENG", lineup=lineup)


def build_whatif_england() -> Team:
    """Same squad, but Lomu is parachuted in at fullback instead of Steward,
    and Steward is shifted out to the wing - the kind of experiment this
    project exists for."""
    lineup = Lineup()
    lomu = next(p for p in LEGENDS if p.name == "Jonah Lomu")
    for player in ENGLAND_SAMPLE:
        if player.name == "Freddie Steward":
            continue
        lineup.set_starter(player.natural_position, player)
    lineup.set_starter(Position.FULLBACK, lomu)
    # Steward moves to the wing instead, bumping Feyi-Waboso to the bench.
    freddie = next(p for p in ENGLAND_SAMPLE if p.name == "Freddie Steward")
    del lineup.starters[Position.RIGHT_WING]
    lineup.set_starter(Position.RIGHT_WING, freddie)
    lineup.captain = next(p for p in ENGLAND_SAMPLE if p.name == "Maro Itoje")
    return Team(name="England (What If)", short_code="WIF", lineup=lineup)


def main():
    home = build_standard_england()
    away = build_whatif_england()

    print(f"--- {home.name} ---")
    print(home.lineup.pretty_print())
    print(f"\n--- {away.name} ---")
    print(away.lineup.pretty_print())

    engine = MatchEngine(home, away, seed=42)
    result = engine.run()
    result.print_report()


if __name__ == "__main__":
    main()
