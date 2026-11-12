"""World-Rugby-style league table with bonus points.

Points: 4 for a win, 2 for a draw, 0 for a loss, +1 bonus point for scoring
4+ tries in a match, +1 losing bonus point for losing by 7 points or fewer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..engine.match_engine import MatchResult


@dataclass
class StandingsRow:
    team: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    points_for: int = 0
    points_against: int = 0
    try_bonus_points: int = 0
    losing_bonus_points: int = 0

    @property
    def points_diff(self) -> int:
        return self.points_for - self.points_against

    @property
    def table_points(self) -> int:
        return (
            self.won * 4 + self.drawn * 2
            + self.try_bonus_points + self.losing_bonus_points
        )


class Standings:
    def __init__(self, teams: List[str]):
        self.rows: Dict[str, StandingsRow] = {t: StandingsRow(team=t) for t in teams}

    def add_result(self, result: MatchResult) -> None:
        home, away = result.home.name, result.away.name
        for name in (home, away):
            if name not in self.rows:
                self.rows[name] = StandingsRow(team=name)

        row_h, row_a = self.rows[home], self.rows[away]
        row_h.played += 1
        row_a.played += 1
        row_h.points_for += result.score_home
        row_h.points_against += result.score_away
        row_a.points_for += result.score_away
        row_a.points_against += result.score_home

        if result.score_home > result.score_away:
            row_h.won += 1
            row_a.lost += 1
            margin = result.score_home - result.score_away
            if margin <= 7:
                row_a.losing_bonus_points += 1
        elif result.score_away > result.score_home:
            row_a.won += 1
            row_h.lost += 1
            margin = result.score_away - result.score_home
            if margin <= 7:
                row_h.losing_bonus_points += 1
        else:
            row_h.drawn += 1
            row_a.drawn += 1

        tries_h = result.stats.get(home)
        tries_a = result.stats.get(away)
        if tries_h is not None and tries_h.tries >= 4:
            row_h.try_bonus_points += 1
        if tries_a is not None and tries_a.tries >= 4:
            row_a.try_bonus_points += 1

    def table(self) -> List[StandingsRow]:
        return sorted(
            self.rows.values(),
            key=lambda r: (r.table_points, r.points_diff, r.points_for),
            reverse=True,
        )

    def print_table(self) -> None:
        print(f"{'Team':<20}{'P':>3}{'W':>3}{'D':>3}{'L':>3}{'PF':>5}{'PA':>5}{'+/-':>6}{'Pts':>5}")
        for row in self.table():
            print(
                f"{row.team:<20}{row.played:>3}{row.won:>3}{row.drawn:>3}{row.lost:>3}"
                f"{row.points_for:>5}{row.points_against:>5}{row.points_diff:>6}{row.table_points:>5}"
            )
