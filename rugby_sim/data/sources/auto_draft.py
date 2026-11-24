"""Greedy best-fit auto-drafting: build a full matchday squad from a player
pool without a human picking every slot - for "I'll draft my team, auto-fill
the rest of the tournament" in the interactive CLI and the web UI.

This is the same greedy algorithm used throughout this project's own tests
(highest `rating_at(position)` remaining, one slot at a time) - not a new
or smarter drafting strategy, just packaged as a reusable function instead
of being copy-pasted into test scripts and ad-hoc checks.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ...models.player import Player
from ...models.position import Position
from ...models.team import Lineup, Team

# How much a player's currently-recovered condition (0-100, from
# `tournament/availability.py`'s short-rest tracking - always 100/absent for
# a plain pool with no tournament rest bookkeeping) discounts their raw fit
# rating during greedy auto-draft selection. Deliberately the SAME
# 0.7-1.0 scaling `MatchEngine` uses for in-match stamina (see
# `engine/match_engine.py` STAMINA_MIN_FACTOR/STAMINA_MAX_FACTOR) so "how
# much a tired player is worth" means the same thing whether it's being
# judged for live-match ratings or for "should the AI start them again so
# soon". This can let a fresher, slightly-lower-rated squad player edge out
# a fatigued starter for a slot - it never makes a tired player unselectable.
CONDITION_MIN_FACTOR = 0.7
CONDITION_MAX_FACTOR = 1.0


def _condition_factor(player: Player, condition: Optional[Dict[int, float]]) -> float:
    if not condition:
        return 1.0
    cond = condition.get(id(player), 100.0)
    cond = max(0.0, min(100.0, cond))
    span = CONDITION_MAX_FACTOR - CONDITION_MIN_FACTOR
    return CONDITION_MIN_FACTOR + span * (cond / 100.0)


def auto_draft_lineup(
    pool: List[Player], bench_size: int = 8, condition: Optional[Dict[int, float]] = None,
) -> Lineup:
    """Fills all 15 starting positions by always taking, for each position
    in turn, whichever remaining player rates highest at it (discounted by
    their current recovered `condition`, if given - see `_condition_factor`
    above) - then fills the bench with the next-best remaining players by
    their own natural position, and names whoever has the highest
    `leadership` as captain.

    `condition`: optional `{id(player): 0-100}` of currently-recovered
    condition, from `TournamentAvailability.starting_condition` - a player
    missing from this dict (or `condition=None`, the default - every caller
    outside tournament squads mode) is treated as fully fresh (100), so a
    friendly/draft-mode auto-draft is completely unaffected by this feature."""
    lineup = Lineup()
    remaining = list(pool)

    for position in Position:
        if not remaining:
            break
        best = max(remaining, key=lambda p: p.rating_at(position) * _condition_factor(p, condition))
        lineup.set_starter(position, best)
        # Excludes by NAME, not just object identity: a real player mapped
        # to one of `wikipedia_squad.TWIN_POSITION`'s pairs (e.g. a real
        # winger with no recorded left/right split) exists in the pool as
        # TWO distinct `Player` objects - same name, two different
        # `natural_position`s, each a genuine candidate for either slot
        # (see `with_twin_position_duplicates`). Excluding only the exact
        # object just drafted would let this auto-drafter happily pick the
        # SAME real person's other copy for the twin slot too, fielding
        # one real person in two positions at once - `is not best` alone
        # used to be correct back when every name in a pool was unique.
        remaining = [p for p in remaining if p is not best and p.name != best.name]

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


def auto_draft_team(
    name: str, pool: List[Player], short_code: Optional[str] = None,
    condition: Optional[Dict[int, float]] = None,
) -> Team:
    lineup = auto_draft_lineup(pool, condition=condition)
    return Team(name=name, short_code=short_code or name[:3].upper(), lineup=lineup)
