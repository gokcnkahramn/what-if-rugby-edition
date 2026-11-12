"""Tournament-wide awards: aggregated team/player stats across every match
played, a "Team of the Tournament" (best performer per starting slot), and
a Player of the Tournament.

Deliberately takes a loosely-typed `report` (duck-typed: `.results` and
`.bracket`) rather than importing `TournamentReport` from `tournament.py`,
since `tournament.py` calls into this module to fill those fields in -
importing the other way round would be circular.

The "performance score" a player gets per match they started is a
heuristic, not a real advanced-stats model (the engine doesn't track
per-player tackles/metres/etc. - only who scored): `rating_at(position)`
(their quality at the slot they were actually picked in) plus a bonus for
anything they personally scored that match. This means a prop who starts
every match and does their job well still ranks on their real quality,
while a back who racks up tries gets rewarded for actually producing -
reasonably fair across forwards and backs, unlike a pure points-scored
ranking (which would never pick a single prop or lock).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..models.player import Player
from ..models.position import JERSEY_NUMBER, Position

# How much one match's personal points total nudges the performance score,
# relative to the player's own quality rating at the position they started
# in. Tuned so a big scoring game matters, without making a fly-half who
# nabbed a couple of penalties automatically outrank a dominant lock.
POINTS_SCORE_WEIGHT = 2.0

# Stages that count as "played deep into the tournament" for Player of the
# Tournament eligibility - see `pick_player_of_tournament`.
LATE_STAGES = ("semi-final", "final")


@dataclass
class TeamTournamentStats:
    team: str
    played: int = 0
    tries: int = 0
    conversions: int = 0
    penalty_goals: int = 0
    drop_goals: int = 0
    turnovers_won: int = 0
    handling_errors: int = 0
    penalties_conceded: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    injuries: int = 0
    substitutions: int = 0
    _territory_pct_sum: float = 0.0

    @property
    def avg_territory_pct(self) -> float:
        return round(self._territory_pct_sum / self.played, 1) if self.played else 0.0


@dataclass
class PlayerTournamentStats:
    player: Player
    team: str
    primary_position: Optional[Position] = None
    matches_started: int = 0
    tries: int = 0
    conversions: int = 0
    penalty_goals: int = 0
    played_late_stage: bool = False
    _performance_sum: float = 0.0

    @property
    def points(self) -> int:
        return self.tries * 5 + self.conversions * 2 + self.penalty_goals * 3

    @property
    def average_performance(self) -> float:
        return round(self._performance_sum / self.matches_started, 1) if self.matches_started else 0.0


def _late_stage_player_keys(report) -> set:
    keys = set()
    for rnd in (getattr(report, "bracket", None) or []):
        if rnd.stage not in LATE_STAGES:
            continue
        for result in rnd.results:
            for team in (result.home, result.away):
                for slot in team.lineup.starters.values():
                    keys.add((team.name, id(slot.player)))
    return keys


def has_late_knockout_stage(report) -> bool:
    return any(rnd.stage in LATE_STAGES for rnd in (getattr(report, "bracket", None) or []))


def aggregate_team_stats(report) -> Dict[str, TeamTournamentStats]:
    out: Dict[str, TeamTournamentStats] = {}
    for result in report.results:
        for team in (result.home, result.away):
            s = result.stats.get(team.name)
            if s is None:
                continue
            agg = out.setdefault(team.name, TeamTournamentStats(team=team.name))
            agg.played += 1
            agg.tries += s.tries
            agg.conversions += s.conversions
            agg.penalty_goals += s.penalty_goals
            agg.drop_goals += s.drop_goals
            agg.turnovers_won += s.turnovers_won
            agg.handling_errors += s.handling_errors
            agg.penalties_conceded += s.penalties_conceded
            agg.yellow_cards += s.yellow_cards
            agg.red_cards += s.red_cards
            agg.injuries += s.injuries
            agg.substitutions += s.substitutions
            agg._territory_pct_sum += s.territory_pct
    return out


def aggregate_player_stats(report) -> Dict[Tuple[str, int], PlayerTournamentStats]:
    late_stage_keys = _late_stage_player_keys(report)
    out: Dict[Tuple[str, int], PlayerTournamentStats] = {}

    for result in report.results:
        for team in (result.home, result.away):
            team_name = team.name
            scoring_by_key = {
                (ps.team, id(ps.player)): ps for ps in result.player_stats if ps.team == team_name
            }
            for position, slot in team.lineup.starters.items():
                player = slot.player
                key = (team_name, id(player))
                agg = out.get(key)
                if agg is None:
                    agg = PlayerTournamentStats(player=player, team=team_name, primary_position=position)
                    out[key] = agg
                agg.matches_started += 1
                ps = scoring_by_key.get(key)
                match_points = 0
                if ps is not None:
                    agg.tries += ps.tries
                    agg.conversions += ps.conversions
                    agg.penalty_goals += ps.penalty_goals
                    match_points = ps.points
                agg._performance_sum += player.rating_at(position) + match_points * POINTS_SCORE_WEIGHT
                if key in late_stage_keys:
                    agg.played_late_stage = True
    return out


def pick_team_of_tournament(
    player_stats: Dict[Tuple[str, int], PlayerTournamentStats],
) -> Dict[Position, PlayerTournamentStats]:
    """Best average-performance player per starting slot, across every team
    in the tournament - one each at their own primary (started) position,
    never double-booking the same real person into two slots."""
    by_position: Dict[Position, List[PlayerTournamentStats]] = {}
    for s in player_stats.values():
        if s.matches_started == 0 or s.primary_position is None:
            continue
        by_position.setdefault(s.primary_position, []).append(s)

    chosen: Dict[Position, PlayerTournamentStats] = {}
    used_keys = set()
    for position in JERSEY_NUMBER:  # canonical 1-15 order
        pool = sorted(by_position.get(position, []), key=lambda s: s.average_performance, reverse=True)
        for candidate in pool:
            key = (candidate.team, id(candidate.player))
            if key in used_keys:
                continue
            chosen[position] = candidate
            used_keys.add(key)
            break
    return chosen


def pick_player_of_tournament(
    player_stats: Dict[Tuple[str, int], PlayerTournamentStats],
    report,
) -> Optional[PlayerTournamentStats]:
    """The single best average-performance player - restricted to players
    who started at least one semi-final/final if the tournament actually
    has a knockout stage that deep (a round-robin-only competition, e.g.
    Six Nations, has no such restriction - there's no "semi-final" to have
    played in)."""
    pool = [s for s in player_stats.values() if s.matches_started > 0]
    if not pool:
        return None
    if has_late_knockout_stage(report):
        eligible = [s for s in pool if s.played_late_stage]
        if eligible:
            pool = eligible
    return max(pool, key=lambda s: s.average_performance)


def attach_tournament_awards(report):
    """Mutates and returns `report`, filling `team_stats`/`player_stats`/
    `team_of_tournament`/`player_of_tournament` - called once at the end
    of every `Tournament.run_*` method."""
    report.team_stats = aggregate_team_stats(report)
    report.player_stats_aggregate = aggregate_player_stats(report)
    report.team_of_tournament = pick_team_of_tournament(report.player_stats_aggregate)
    report.player_of_tournament = pick_player_of_tournament(report.player_stats_aggregate, report)
    return report
