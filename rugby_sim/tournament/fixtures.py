"""Synthetic fixture generators for custom (not real-world) tournaments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Fixture:
    home: str
    away: str
    round_no: int
    stage: str = "round-robin"  # "round-robin" | "pool" | "quarter-final" | ... | "final"


def round_robin(team_codes: List[str], home_and_away: bool = False) -> List[Fixture]:
    """Circle-method single round-robin; every team plays every other once
    (or twice, home and away, if `home_and_away`)."""
    teams = list(team_codes)
    if len(teams) % 2 == 1:
        teams.append("BYE")

    n = len(teams)
    rounds: List[Fixture] = []
    fixed = teams[0]
    rotating = teams[1:]

    for round_no in range(n - 1):
        pairing = [fixed] + rotating
        for i in range(n // 2):
            home, away = pairing[i], pairing[n - 1 - i]
            if "BYE" in (home, away):
                continue
            rounds.append(Fixture(home=home, away=away, round_no=round_no + 1))
        rotating = rotating[-1:] + rotating[:-1]

    if home_and_away:
        second_leg = [
            Fixture(home=f.away, away=f.home, round_no=f.round_no + (n - 1))
            for f in rounds
        ]
        rounds += second_leg

    return rounds


def pool_stage(team_codes: List[str], pool_count: int = 2) -> Tuple[List[List[str]], List[Fixture]]:
    """Splits teams evenly into `pool_count` pools and round-robins each."""
    teams = list(team_codes)
    pools = [teams[i::pool_count] for i in range(pool_count)]
    fixtures: List[Fixture] = []
    for idx, pool in enumerate(pools):
        for f in round_robin(pool):
            fixtures.append(Fixture(home=f.home, away=f.away, round_no=f.round_no, stage=f"pool_{idx + 1}"))
    return pools, fixtures


def knockout_bracket(seeded_teams: List[str]) -> List[Fixture]:
    """First round of a single-elimination bracket from a seeded list
    (1 vs last, 2 vs second-last, ...). Later rounds depend on results, so
    the tournament orchestrator generates them round by round at runtime."""
    teams = list(seeded_teams)
    n = len(teams)
    stage_name = {2: "final", 4: "semi-final", 8: "quarter-final", 16: "round-of-16"}.get(n, "knockout")
    fixtures = []
    for i in range(n // 2):
        fixtures.append(Fixture(home=teams[i], away=teams[n - 1 - i], round_no=1, stage=stage_name))
    return fixtures


def next_knockout_round(winners: List[str]) -> List[Fixture]:
    """Pairs up winners in bracket order for the next knockout round."""
    n = len(winners)
    stage_name = {2: "final", 4: "semi-final", 8: "quarter-final", 16: "round-of-16"}.get(n, "knockout")
    fixtures = []
    for i in range(0, n, 2):
        fixtures.append(Fixture(home=winners[i], away=winners[i + 1], round_no=1, stage=stage_name))
    return fixtures
