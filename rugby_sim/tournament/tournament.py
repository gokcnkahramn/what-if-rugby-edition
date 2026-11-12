"""Orchestrates a tournament: drives `MatchEngine` over a fixture list
(real or synthetic) and accumulates a `Standings` table.

Two usage modes:
- `Tournament(teams).run_real("six_nations", season="2026")` - replays the
  actual fixture list for a named real competition (see `real_fixtures.py`).
- `Tournament(teams).run_round_robin()` / `.run_pool_and_knockout()` - a
  synthetic fixture list for a fully custom tournament (see `fixtures.py`).

`teams` maps a fixture-side name (e.g. "England", or a user's own team code)
to the `Team` the user has drafted a lineup for - the orchestrator never
builds lineups itself, same philosophy as the rest of the project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..engine.match_engine import MatchEngine, MatchResult
from ..models.team import Team
from .fixtures import Fixture, knockout_bracket, next_knockout_round, pool_stage, round_robin
from .real_fixtures import RealFixture, load_real_fixtures
from .standings import Standings


@dataclass
class BracketRound:
    stage: str
    fixtures: List[Fixture]
    results: List[MatchResult] = field(default_factory=list)


@dataclass
class TournamentReport:
    name: str
    standings: Optional[Standings] = None
    results: List[MatchResult] = field(default_factory=list)
    pools: Optional[Dict[str, Standings]] = None
    bracket: List[BracketRound] = field(default_factory=list)
    champion: Optional[str] = None

    def print_report(self) -> None:
        print(f"\n=== {self.name} ===")
        for result in self.results:
            print(f"  {result.scoreline()}")
        if self.pools:
            for pool_name, standings in self.pools.items():
                print(f"\n-- {pool_name} --")
                standings.print_table()
        if self.standings:
            print()
            self.standings.print_table()
        for rnd in self.bracket:
            print(f"\n-- {rnd.stage} --")
            for r in rnd.results:
                print(f"  {r.scoreline()}")
        if self.champion:
            print(f"\nChampion: {self.champion}")


class Tournament:
    def __init__(self, teams: Dict[str, Team]):
        self.teams = teams

    def _team(self, name: str) -> Team:
        if name not in self.teams:
            raise ValueError(
                f"No Team registered for '{name}' - pass it in the `teams` dict "
                f"given to Tournament(...)."
            )
        return self.teams[name]

    def _play(self, home_name: str, away_name: str, seed: Optional[int]) -> MatchResult:
        engine = MatchEngine(self._team(home_name), self._team(away_name), seed=seed)
        return engine.run()

    # -- synthetic formats --------------------------------------------
    def run_round_robin(self, home_and_away: bool = False, seed: Optional[int] = None) -> TournamentReport:
        team_names = list(self.teams.keys())
        fixtures = round_robin(team_names, home_and_away=home_and_away)
        standings = Standings(team_names)
        results = []
        for i, fx in enumerate(fixtures):
            result = self._play(fx.home, fx.away, seed=None if seed is None else seed + i)
            standings.add_result(result)
            results.append(result)
        return TournamentReport(name="Round-robin", standings=standings, results=results)

    def run_pool_and_knockout(self, pool_count: int = 2, seed: Optional[int] = None) -> TournamentReport:
        team_names = list(self.teams.keys())
        pools, fixtures = pool_stage(team_names, pool_count=pool_count)
        pool_standings = {f"Pool {i + 1}": Standings(p) for i, p in enumerate(pools)}
        all_results = []
        counter = 0
        for fx in fixtures:
            result = self._play(fx.home, fx.away, seed=None if seed is None else seed + counter)
            counter += 1
            pool_standings[f"Pool {int(fx.stage.split('_')[1])}"].add_result(result)
            all_results.append(result)

        qualifiers = []
        for pool_name, standings in pool_standings.items():
            top_two = [row.team for row in standings.table()[:2]]
            qualifiers.extend(top_two)

        bracket: List[BracketRound] = []
        round_teams = qualifiers
        champion = None
        while len(round_teams) >= 2:
            fxs = knockout_bracket(round_teams) if bracket == [] else next_knockout_round(round_teams)
            round_results = []
            for fx in fxs:
                result = self._play(fx.home, fx.away, seed=None if seed is None else seed + counter)
                counter += 1
                round_results.append(result)
                all_results.append(result)
            winners = [
                r.home.name if r.score_home >= r.score_away else r.away.name
                for r in round_results
            ]
            bracket.append(BracketRound(stage=fxs[0].stage, fixtures=fxs, results=round_results))
            if len(winners) == 1:
                champion = winners[0]
                break
            round_teams = winners

        return TournamentReport(
            name="Pool stage + knockout", pools=pool_standings,
            results=all_results, bracket=bracket, champion=champion,
        )

    # -- real-world replay ----------------------------------------------
    def run_real(self, tournament_key: str, season: str, seed: Optional[int] = None) -> TournamentReport:
        real_fixtures: List[RealFixture] = load_real_fixtures(tournament_key, season)
        if not real_fixtures:
            raise ValueError(
                f"No fixtures recovered for '{tournament_key}' in {season} - "
                f"the dataset may not cover that season/competition."
            )
        team_names = sorted({f.home for f in real_fixtures} | {f.away for f in real_fixtures})
        standings = Standings(team_names)
        results = []
        for i, fx in enumerate(real_fixtures):
            result = self._play(fx.home, fx.away, seed=None if seed is None else seed + i)
            standings.add_result(result)
            results.append(result)
        name = f"{tournament_key.replace('_', ' ').title()} {season} (real fixtures, simulated)"
        return TournamentReport(name=name, standings=standings, results=results)

    # -- 2027 Rugby World Cup (real draw, no fixtures exist yet) ---------
    def run_world_cup_2027(self, fixture_mode: str = "specific", seed: Optional[int] = None) -> TournamentReport:
        """`fixture_mode`: "specific" plays each pool's round-robin in the
        fixed order the pool was drawn in; "random" shuffles each pool's
        team order first (same pools, just a different match order) -
        there's no real fixture list to replay since the tournament hasn't
        been played, only a real draw (see `world_cup_2027.py`)."""
        import random

        from .world_cup_2027 import POOLS_2027, THIRD_PLACE_PAIRINGS

        if fixture_mode not in ("specific", "random"):
            raise ValueError("fixture_mode must be 'specific' or 'random'")
        rng = random.Random(seed)

        pool_letters = list(POOLS_2027.keys())  # ["A", "B", "C", "D", "E", "F"]
        pools = {name: list(teams) for name, teams in POOLS_2027.items()}
        if fixture_mode == "random":
            for teams in pools.values():
                rng.shuffle(teams)

        pool_standings: Dict[str, Standings] = {}
        all_results: List[MatchResult] = []
        counter = 0
        for pool_name, teams in pools.items():
            standings = Standings(teams)
            for fx in round_robin(teams):
                result = self._play(fx.home, fx.away, seed=None if seed is None else seed + counter)
                counter += 1
                standings.add_result(result)
                all_results.append(result)
            pool_standings[f"Pool {pool_name}"] = standings

        winner_by_letter, runner_up_by_letter, third_by_letter = {}, {}, {}
        for letter, standings in zip(pool_letters, pool_standings.values()):
            table = standings.table()
            winner_by_letter[letter] = table[0].team
            runner_up_by_letter[letter] = table[1].team
            third_by_letter[letter] = table[2]

        best_third_letters = sorted(
            pool_letters,
            key=lambda l: (
                third_by_letter[l].table_points,
                third_by_letter[l].points_diff,
                third_by_letter[l].points_for,
            ),
            reverse=True,
        )[:4]
        # Official permutation table: given which 4 pools' third-placed
        # teams qualified, this says which one plays the winner of Pools
        # A/B/C/D - guarantees no Round-of-16 match is a same-pool rematch.
        slot_to_source = THIRD_PLACE_PAIRINGS[frozenset(best_third_letters)]
        third_opponent = {
            slot: third_by_letter[source].team for slot, source in slot_to_source.items()
        }

        r16_pairs = [
            (winner_by_letter["A"], third_opponent["A"]),
            (winner_by_letter["B"], third_opponent["B"]),
            (winner_by_letter["C"], third_opponent["C"]),
            (winner_by_letter["D"], third_opponent["D"]),
            (winner_by_letter["E"], runner_up_by_letter["D"]),
            (winner_by_letter["F"], runner_up_by_letter["B"]),
            (runner_up_by_letter["A"], runner_up_by_letter["E"]),
            (runner_up_by_letter["C"], runner_up_by_letter["F"]),
        ]
        r16_fixtures = [
            Fixture(home=home, away=away, round_no=1, stage="round-of-16")
            for home, away in r16_pairs
        ]

        bracket: List[BracketRound] = []
        champion: Optional[str] = None
        fxs = r16_fixtures
        while True:
            round_results = []
            for fx in fxs:
                result = self._play(fx.home, fx.away, seed=None if seed is None else seed + counter)
                counter += 1
                round_results.append(result)
                all_results.append(result)
            round_winners = [
                r.home.name if r.score_home >= r.score_away else r.away.name
                for r in round_results
            ]
            bracket.append(BracketRound(stage=fxs[0].stage, fixtures=fxs, results=round_results))
            if len(round_winners) == 1:
                champion = round_winners[0]
                break
            # QF/SF/Final bracket order hasn't been published by World Rugby
            # (only the Round of 16 pairing rule above is official), so this
            # pairs consecutive winners in bracket order - a standard,
            # unofficial progression.
            fxs = next_knockout_round(round_winners)

        return TournamentReport(
            name=f"Rugby World Cup 2027 ({fixture_mode} pool order, real draw + official R16 pairing)",
            pools=pool_standings, results=all_results, bracket=bracket, champion=champion,
        )
