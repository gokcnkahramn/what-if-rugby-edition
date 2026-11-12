"""Thin builder for fully custom tournaments - pick whichever shape you
want without memorizing `Tournament`'s method names."""

from __future__ import annotations

from typing import Dict, Optional

from ..models.team import Team
from .tournament import Tournament, TournamentReport


class CustomTournament:
    def __init__(self, teams: Dict[str, Team], format: str = "round_robin"):
        """`format`: "round_robin" | "round_robin_home_away" | "pool_knockout" """
        self.teams = teams
        self.format = format
        self._tournament = Tournament(teams)

    def run(self, pool_count: int = 2, seed: Optional[int] = None) -> TournamentReport:
        if self.format == "round_robin":
            return self._tournament.run_round_robin(seed=seed)
        if self.format == "round_robin_home_away":
            return self._tournament.run_round_robin(home_and_away=True, seed=seed)
        if self.format == "pool_knockout":
            return self._tournament.run_pool_and_knockout(pool_count=pool_count, seed=seed)
        raise ValueError(f"Unknown custom tournament format: {self.format}")
