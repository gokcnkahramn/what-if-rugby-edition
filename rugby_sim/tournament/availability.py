"""Tracks which players are unavailable for a tournament's upcoming
matches due to an in-match injury or a red card, for the "fresh squad every
match" mode (`Tournament(..., squads={...})` - see `tournament.py`). Pure
bookkeeping: it doesn't touch ratings or who gets picked, just which names
are allowed to be picked from for the *next* match.

Lay-off lengths are a simplified, documented heuristic - real recovery
times and disciplinary-panel suspensions vary hugely by injury/offense.
This is "plausible enough to matter", not a medical or disciplinary model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..engine.match_engine import MatchResult
from ..models.player import Player

INJURY_LAYOFF_MATCHES = 1
RED_CARD_SUSPENSION_MATCHES = 1


@dataclass
class TournamentAvailability:
    # (team_name, id(player)) -> matches still remaining they must sit out,
    # counting from (and not including) the match that caused it.
    _sidelined: Dict[Tuple[str, int], int] = field(default_factory=dict)

    def filter_available(self, team_name: str, pool: List[Player]) -> List[Player]:
        """The subset of `pool` that isn't currently sidelined for this
        team - what a fresh per-match draft is actually allowed to pick
        from."""
        return [p for p in pool if self._sidelined.get((team_name, id(p)), 0) <= 0]

    def is_sidelined(self, team_name: str, player: Player) -> bool:
        return self._sidelined.get((team_name, id(player)), 0) > 0

    def record_match(self, result: MatchResult) -> None:
        """Call once after a match finishes: ticks every existing layoff
        down by one match (removing it once it reaches zero), then adds
        fresh layoffs for anyone injured or red-carded in *this* match -
        in that order, so a layoff added here always means "sits out the
        next match", not "already counted as served"."""
        for key in list(self._sidelined.keys()):
            self._sidelined[key] -= 1
            if self._sidelined[key] <= 0:
                del self._sidelined[key]

        for team_name, player in result.injured_players:
            key = (team_name, id(player))
            self._sidelined[key] = max(self._sidelined.get(key, 0), INJURY_LAYOFF_MATCHES)

        for team_name, player, card_type in result.carded_players:
            if card_type != "red":
                continue
            key = (team_name, id(player))
            self._sidelined[key] = max(self._sidelined.get(key, 0), RED_CARD_SUSPENSION_MATCHES)

    def sidelined_names(self, team_name: str, pool: List[Player]) -> List[str]:
        """For a status message: which of this team's pool players are
        currently sidelined, and why long."""
        return [
            p.name for p in pool
            if self._sidelined.get((team_name, id(p)), 0) > 0
        ]
