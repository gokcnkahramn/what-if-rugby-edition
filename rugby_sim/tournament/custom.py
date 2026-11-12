"""Thin builder for fully custom tournaments - pick whichever shape you
want without memorizing `Tournament`'s method names."""

from __future__ import annotations

from typing import Dict, List, Optional

from ..models.player import Player
from ..models.team import Team
from .tournament import Tournament, TournamentReport


class CustomTournament:
    def __init__(
        self, teams: Optional[Dict[str, Team]] = None, format: str = "round_robin",
        squads: Optional[Dict[str, List[Player]]] = None,
        my_team: Optional[str] = None, pause_hook=None, on_match_played=None,
    ):
        """`format`: "round_robin" | "round_robin_home_away" | "pool_knockout".
        `squads`, like `Tournament`'s own, drafts a fresh lineup for that
        team before every match instead of reusing one fixed lineup.
        `my_team`/`pause_hook`/`on_match_played`: see `Tournament.__init__` -
        lets an interactive tournament pause exactly on `my_team`'s fixtures
        and stream a running results feed."""
        self.teams = teams or {}
        self.format = format
        self._tournament = Tournament(
            teams=teams, squads=squads, my_team=my_team, pause_hook=pause_hook, on_match_played=on_match_played,
        )

    # -- live-progress passthrough (see `Tournament.current_stage` etc.) --
    @property
    def current_stage(self):
        return self._tournament.current_stage

    @property
    def current_standings(self):
        return self._tournament.current_standings

    @property
    def current_pools(self):
        return self._tournament.current_pools

    @property
    def current_bracket(self):
        return self._tournament.current_bracket

    def run(self, pool_count: int = 2, seed: Optional[int] = None) -> TournamentReport:
        if self.format == "round_robin":
            return self._tournament.run_round_robin(seed=seed)
        if self.format == "round_robin_home_away":
            return self._tournament.run_round_robin(home_and_away=True, seed=seed)
        if self.format == "pool_knockout":
            return self._tournament.run_pool_and_knockout(pool_count=pool_count, seed=seed)
        raise ValueError(f"Unknown custom tournament format: {self.format}")
