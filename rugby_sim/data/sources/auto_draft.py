"""Greedy best-fit auto-drafting: build a full matchday squad from a player
pool without a human picking every slot - for "I'll draft my team, auto-fill
the rest of the tournament" in the interactive CLI and the web UI.

This is the same greedy algorithm used throughout this project's own tests
(highest `rating_at(position)` remaining, one slot at a time) - not a new
or smarter drafting strategy, just packaged as a reusable function instead
of being copy-pasted into test scripts and ad-hoc checks.
"""

from __future__ import annotations

from typing import List, Optional

from ...models.player import Player
from ...models.position import Position
from ...models.team import Lineup, Team


def auto_draft_lineup(pool: List[Player], bench_size: int = 8) -> Lineup:
    """Fills all 15 starting positions by always taking, for each position
    in turn, whichever remaining player rates highest at it - then fills
    the bench with the next-best remaining players by their own natural
    position, and names whoever has the highest `leadership` as captain."""
    lineup = Lineup()
    remaining = list(pool)

    for position in Position:
        if not remaining:
            break
        best = max(remaining, key=lambda p: p.rating_at(position))
        lineup.set_starter(position, best)
        remaining = [p for p in remaining if p is not best]

    if lineup.starters:
        lineup.captain = max(
            lineup.starters.values(), key=lambda slot: slot.player.attributes.leadership
        ).player

    for player in sorted(remaining, key=lambda p: -p.rating_at(p.natural_position))[:bench_size]:
        try:
            lineup.add_bench(player)
        except ValueError:
            break

    return lineup


def auto_draft_team(name: str, pool: List[Player], short_code: Optional[str] = None) -> Team:
    lineup = auto_draft_lineup(pool)
    return Team(name=name, short_code=short_code or name[:3].upper(), lineup=lineup)
