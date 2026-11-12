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

from ..data.sources.auto_draft import auto_draft_team
from ..engine.match_engine import MatchEngine, MatchResult
from ..models.player import Player
from ..models.position import Position
from ..models.team import Team
from .availability import TournamentAvailability
from .fixtures import Fixture, knockout_bracket, next_knockout_round, pool_stage, round_robin
from .real_fixtures import RealFixture, load_real_fixtures
from .standings import Standings
from .tournament_stats import PlayerTournamentStats, TeamTournamentStats, attach_tournament_awards


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
    # Tournament-wide awards (see `tournament_stats.py`), filled in by
    # `attach_tournament_awards` at the end of every `run_*` method.
    team_stats: Dict[str, TeamTournamentStats] = field(default_factory=dict)
    player_stats_aggregate: Dict[tuple, PlayerTournamentStats] = field(default_factory=dict)
    team_of_tournament: Dict[Position, PlayerTournamentStats] = field(default_factory=dict)
    player_of_tournament: Optional[PlayerTournamentStats] = None

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
        if self.team_stats:
            print("\n-- Team tournament stats --")
            for s in self.team_stats.values():
                print(
                    f"  {s.team}: {s.played} played, {s.tries} tries, {s.penalty_goals} pens, "
                    f"{s.drop_goals} drop goals, {s.turnovers_won} turnovers won, "
                    f"{s.handling_errors} errors, {s.penalties_conceded} pens conceded, "
                    f"{s.yellow_cards} YC / {s.red_cards} RC, avg territory {s.avg_territory_pct}%, "
                    f"{s.injuries} injuries, {s.substitutions} subs"
                )
        if self.player_stats_aggregate:
            top_scorers = sorted(
                (s for s in self.player_stats_aggregate.values() if s.points > 0),
                key=lambda s: s.points, reverse=True,
            )[:10]
            if top_scorers:
                print("\n-- Tournament top scorers --")
                for s in top_scorers:
                    print(
                        f"  {s.player.name} ({s.team}): {s.points} pts "
                        f"({s.tries} tries, {s.conversions} conv, {s.penalty_goals} pens) "
                        f"over {s.matches_started} starts"
                    )
        if self.team_of_tournament:
            print("\n-- Team of the Tournament --")
            for position, s in self.team_of_tournament.items():
                print(f"  {position.value}: {s.player.name} ({s.team}) - avg {s.average_performance}")
        if self.player_of_tournament:
            s = self.player_of_tournament
            print(
                f"\nPlayer of the Tournament: {s.player.name} ({s.team}) - "
                f"avg performance {s.average_performance} over {s.matches_started} starts"
            )


class Tournament:
    """`teams` maps a fixture-side name to a fixed `Team` (one drafted
    lineup, reused for every match it plays - the original, simpler mode).

    `squads`, if given, maps a fixture-side name to its full player *pool*
    instead - that team gets a **fresh auto-drafted lineup before every
    single match**, built from whichever of its pool players aren't
    currently sidelined by an in-match injury or red card from an earlier
    match in this same tournament (see `availability.py`). This is the
    realistic alternative to one fixed lineup for the whole competition:
    a squad, not a single starting XV, the way a real tournament actually
    works. A name can be in `teams` or `squads`, never both."""

    def __init__(
        self, teams: Optional[Dict[str, Team]] = None, squads: Optional[Dict[str, List[Player]]] = None,
        my_team: Optional[str] = None, pause_hook=None, on_match_played=None,
    ):
        """`my_team`/`pause_hook` support an interactive tournament: when a
        fixture involves `my_team`, instead of auto-simulating it with
        `MatchEngine(...).run()`, `_play` calls
        `pause_hook(home_name, away_name, home_team, away_team, seed) -> MatchResult`
        - the caller (the web layer) is expected to run that match through
        the pausable `MatchEngine.start()/advance_to()/finish()` flow (the
        same one the single-match "live match" UI uses) and block until the
        user has played it through, then hand back the finished
        `MatchResult`. Every other fixture (not involving `my_team`) is
        still fully auto-simmed exactly as before - `pause_hook` is never
        called for those.

        `on_match_played(home_name, away_name, result)`, if given, is called
        once for *every* fixture right after it's resolved (auto-simmed or
        played through `pause_hook`) - this is how the web layer builds a
        running "results so far" feed for an interactive tournament, since
        the rest of this class otherwise only hands back one final
        `TournamentReport` at the very end."""
        self.teams = teams or {}
        self.squads = squads or {}
        self.availability = TournamentAvailability()
        self.my_team = my_team
        self.pause_hook = pause_hook
        self.on_match_played = on_match_played
        # Live progress, updated as the tournament runs (not just at the
        # end) - the web layer reads these after every `on_match_played`
        # call to show a current standings table / knockout stage while an
        # interactive tournament is still in progress. `current_standings`/
        # `current_pools` are the *same* `Standings` object(s) each run_*
        # method keeps mutating in place, so reading them mid-tournament
        # always reflects every match played so far; `current_bracket` is
        # likewise the same list each knockout round gets appended to.
        self.current_stage: Optional[str] = None
        self.current_standings: Optional[Standings] = None
        self.current_pools: Optional[Dict[str, Standings]] = None
        self.current_bracket: List[BracketRound] = []

    def known_names(self) -> set:
        return set(self.teams) | set(self.squads)

    def _team(self, name: str) -> Team:
        if name not in self.teams:
            raise ValueError(
                f"No Team registered for '{name}' - pass it in the `teams` dict "
                f"given to Tournament(...)."
            )
        return self.teams[name]

    def _resolve_team_for_match(self, name: str) -> Team:
        if name in self.squads:
            pool = self.availability.filter_available(name, self.squads[name])
            if not pool:
                raise ValueError(
                    f"No available players left for '{name}' this match - "
                    f"everyone in their pool is currently sidelined."
                )
            return auto_draft_team(name, pool, short_code=name[:3].upper())
        return self._team(name)

    def _play(self, home_name: str, away_name: str, seed: Optional[int]) -> MatchResult:
        home_team = self._resolve_team_for_match(home_name)
        away_team = self._resolve_team_for_match(away_name)
        if self.pause_hook is not None and self.my_team is not None and self.my_team in (home_name, away_name):
            result = self.pause_hook(home_name, away_name, home_team, away_team, seed)
        else:
            result = MatchEngine(home_team, away_team, seed=seed).run()
        self.availability.record_match(result)
        if self.on_match_played is not None:
            self.on_match_played(home_name, away_name, result)
        return result

    # -- synthetic formats --------------------------------------------
    def run_round_robin(self, home_and_away: bool = False, seed: Optional[int] = None) -> TournamentReport:
        team_names = sorted(self.known_names())
        fixtures = round_robin(team_names, home_and_away=home_and_away)
        standings = Standings(team_names)
        self.current_stage = "Round-robin"
        self.current_standings = standings
        results = []
        for i, fx in enumerate(fixtures):
            result = self._play(fx.home, fx.away, seed=None if seed is None else seed + i)
            standings.add_result(result)
            results.append(result)
        return attach_tournament_awards(TournamentReport(name="Round-robin", standings=standings, results=results))

    def run_pool_and_knockout(self, pool_count: int = 2, seed: Optional[int] = None) -> TournamentReport:
        team_names = sorted(self.known_names())
        pools, _ = pool_stage(team_names, pool_count=pool_count)
        named_pools = {f"Pool {i + 1}": p for i, p in enumerate(pools)}
        return self._run_named_pools_and_knockout(
            named_pools, name="Pool stage + knockout", qualifiers_per_pool=2, seed=seed,
        )

    def _run_named_pools_and_knockout(
        self, named_pools: Dict[str, List[str]], name: str,
        qualifiers_per_pool: int = 2, seed: Optional[int] = None,
    ) -> TournamentReport:
        """Shared by `run_pool_and_knockout` (auto-split pools) and
        `run_historical_world_cup` (real historical pool groupings) - plain
        top-N-per-pool-advance, standard bracket order. The 2027 World Cup's
        third-place-wildcard permutation table is a different, more
        complex rule (see `run_world_cup_2027`) that doesn't apply to any
        pre-2027 tournament, so it isn't reused here."""
        pool_standings = {pool_name: Standings(teams) for pool_name, teams in named_pools.items()}
        self.current_stage = "Pool stage"
        self.current_pools = pool_standings
        all_results: List[MatchResult] = []
        counter = 0
        for pool_name, teams in named_pools.items():
            for fx in round_robin(teams):
                result = self._play(fx.home, fx.away, seed=None if seed is None else seed + counter)
                counter += 1
                pool_standings[pool_name].add_result(result)
                all_results.append(result)

        qualifiers = []
        for standings in pool_standings.values():
            qualifiers.extend(row.team for row in standings.table()[:qualifiers_per_pool])

        bracket: List[BracketRound] = []
        self.current_bracket = bracket
        round_teams = qualifiers
        champion = None
        while len(round_teams) >= 2:
            fxs = knockout_bracket(round_teams) if not bracket else next_knockout_round(round_teams)
            self.current_stage = fxs[0].stage
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

        return attach_tournament_awards(TournamentReport(
            name=name, pools=pool_standings,
            results=all_results, bracket=bracket, champion=champion,
        ))

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
        self.current_stage = tournament_key.replace("_", " ").title()
        self.current_standings = standings
        results = []
        for i, fx in enumerate(real_fixtures):
            result = self._play(fx.home, fx.away, seed=None if seed is None else seed + i)
            standings.add_result(result)
            results.append(result)
        name = f"{tournament_key.replace('_', ' ').title()} {season} (real fixtures, simulated)"
        return attach_tournament_awards(TournamentReport(name=name, standings=standings, results=results))

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
        self.current_stage = "Pool stage"
        self.current_pools = pool_standings
        all_results: List[MatchResult] = []
        counter = 0
        for pool_name, teams in pools.items():
            standings = Standings(teams)
            pool_standings[f"Pool {pool_name}"] = standings
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
        self.current_bracket = bracket
        champion: Optional[str] = None
        fxs = r16_fixtures
        while True:
            self.current_stage = fxs[0].stage
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

        return attach_tournament_awards(TournamentReport(
            name=f"Rugby World Cup 2027 ({fixture_mode} pool order, real draw + official R16 pairing)",
            pools=pool_standings, results=all_results, bracket=bracket, champion=champion,
        ))

    # -- historical Rugby World Cups (1995-2023, professional era) ------
    def run_historical_world_cup(self, year: int, seed: Optional[int] = None) -> TournamentReport:
        """Replays a real past World Cup's real pool groupings (read
        straight off that edition's Wikipedia squads page - see
        `historical_rwc.get_rwc_year_data` - not hand-entered), with the
        simple top-2-per-pool-advance format every edition before 2027
        used (no third-place wildcards, unlike `run_world_cup_2027`)."""
        from ..data.sources.historical_rwc import get_rwc_year_data

        pools, _squads = get_rwc_year_data(year)
        known = self.known_names()
        missing = [name for pool in pools.values() for name in pool if name not in known]
        if missing:
            raise ValueError(
                f"Missing a Team for: {', '.join(sorted(set(missing)))} - "
                f"draft every {year} World Cup participant before running it."
            )
        if year == 1999:
            return self._run_1999_world_cup(pools, seed=seed)

        return self._run_named_pools_and_knockout(
            pools, name=f"{year} Rugby World Cup (real draw, historical squads)",
            qualifiers_per_pool=2, seed=seed,
        )

    def _run_1999_world_cup(self, named_pools: Dict[str, List[str]], seed: Optional[int] = None) -> TournamentReport:
        """1999 is the one professional-era edition with a genuinely
        different format: 5 pools of 4, pool **winners** go straight to the
        quarter-finals (5 slots); the 5 pool **runners-up** plus the single
        best third-placed team play a quarter-final play-off round (3
        knockout matches) for the remaining 3 quarter-final slots. Every
        other edition (1995, 2003-2023) is a plain top-2-per-pool, which
        `_run_named_pools_and_knockout` already covers.

        The real 1999 play-off pairings (England v Fiji, Scotland v Samoa,
        Argentina v Ireland) came down to the actual pool letters each team
        was drawn into, not a published general rule for an arbitrary
        set of results - so this reproduces it as a letter-based pattern
        (runner-up B v runner-up C, runner-up A v runner-up D, best third
        v runner-up E) that happens to match the real bracket for the real
        1999 draw. It's the only way to generalize a one-off event, not an
        official formula - flagged here rather than presented as fact."""
        pool_standings = {pool_name: Standings(teams) for pool_name, teams in named_pools.items()}
        self.current_stage = "Pool stage"
        self.current_pools = pool_standings
        all_results: List[MatchResult] = []
        counter = 0
        for pool_name, teams in named_pools.items():
            for fx in round_robin(teams):
                result = self._play(fx.home, fx.away, seed=None if seed is None else seed + counter)
                counter += 1
                pool_standings[pool_name].add_result(result)
                all_results.append(result)

        letters = sorted(named_pools.keys())  # ["Pool A", ..., "Pool E"]
        winners, runners_up, thirds = {}, {}, {}
        for letter in letters:
            table = pool_standings[letter].table()
            winners[letter] = table[0].team
            runners_up[letter] = table[1].team
            thirds[letter] = table[2]

        # Best third by table points/diff/for - but if that happens to be
        # pool E's own third, pair it against E's runner-up would be a
        # same-pool rematch (the two already played each other in the pool
        # stage). Real 1999 never hit this (the best third, Argentina, was
        # from pool D), so there's no real precedent for it - fall back to
        # the next-best third rather than replay a pool match in the
        # knockout stage.
        thirds_by_rank = sorted(
            letters,
            key=lambda l: (thirds[l].table_points, thirds[l].points_diff, thirds[l].points_for),
            reverse=True,
        )
        best_third_letter = next(l for l in thirds_by_rank if l != letters[4])

        playoff_pairs = [
            (runners_up[letters[1]], runners_up[letters[2]]),  # B v C
            (runners_up[letters[0]], runners_up[letters[3]]),  # A v D
            (thirds[best_third_letter].team, runners_up[letters[4]]),  # best 3rd v E
        ]
        playoff_fixtures = [
            Fixture(home=home, away=away, round_no=1, stage="quarter-final play-off")
            for home, away in playoff_pairs
        ]
        self.current_stage = "quarter-final play-off"
        playoff_results = []
        for fx in playoff_fixtures:
            result = self._play(fx.home, fx.away, seed=None if seed is None else seed + counter)
            counter += 1
            playoff_results.append(result)
            all_results.append(result)
        playoff_winners = [
            r.home.name if r.score_home >= r.score_away else r.away.name
            for r in playoff_results
        ]

        bracket: List[BracketRound] = [
            BracketRound(stage="quarter-final play-off", fixtures=playoff_fixtures, results=playoff_results),
        ]
        self.current_bracket = bracket
        qf_teams = [winners[l] for l in letters] + playoff_winners
        champion: Optional[str] = None
        round_teams = qf_teams
        first_round = True
        while len(round_teams) >= 2:
            fxs = knockout_bracket(round_teams) if first_round else next_knockout_round(round_teams)
            first_round = False
            self.current_stage = fxs[0].stage
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
            round_teams = round_winners

        return attach_tournament_awards(TournamentReport(
            name="1999 Rugby World Cup (real draw, historical squads, "
                 "5-pool + quarter-final play-off format)",
            pools=pool_standings, results=all_results, bracket=bracket, champion=champion,
        ))

    # -- historical Six Nations Championship (2009-2021) ----------------
    def run_historical_six_nations(self, year: int, seed: Optional[int] = None) -> TournamentReport:
        """Replays a historical Six Nations edition with that year's real
        squads (see `historical_six_nations.get_six_nations_year_data`) -
        plain round-robin + bonus-point table, same shape as `run_real`.
        The real match-by-match order isn't recoverable from the squads
        page (no fixture list there), so the round-robin uses a synthetic
        generated order, not the actual historical sequence - the final
        table's shape (10 matches, everyone plays everyone once) is real,
        the order they were played in isn't."""
        from ..data.sources.historical_six_nations import get_six_nations_year_data

        squads = get_six_nations_year_data(year)
        known = self.known_names()
        missing = [name for name in squads if name not in known]
        if missing:
            raise ValueError(
                f"Missing a Team for: {', '.join(sorted(missing))} - "
                f"draft every {year} Six Nations side before running it."
            )
        team_names = list(squads.keys())
        standings = Standings(team_names)
        self.current_stage = f"{year} Six Nations"
        self.current_standings = standings
        results: List[MatchResult] = []
        for i, fx in enumerate(round_robin(team_names)):
            result = self._play(fx.home, fx.away, seed=None if seed is None else seed + i)
            standings.add_result(result)
            results.append(result)
        return attach_tournament_awards(TournamentReport(
            name=f"{year} Six Nations Championship (historical squads, synthetic fixture order)",
            standings=standings, results=results,
        ))
