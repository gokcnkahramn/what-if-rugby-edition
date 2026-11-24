"""Shared `ClassicMatch`/`Objective` model and the generic, parameterized
objective-type vocabulary used by `classic_matches.py` and every Tier-B
module (`classic_matches_tier_b_six_nations.py`,
`classic_matches_tier_b_rugby_championship.py`).

Deliberately split out into its own module with NO dependency on
`classic_matches.py` (or any Tier-B module): `classic_matches.py` imports
the Tier-B modules at module level (to merge their match lists into
`CLASSIC_MATCHES`), and the Tier-B modules need this same `ClassicMatch`
class and objective helpers - if the Tier-B modules imported them from
`classic_matches.py` directly, that would be a genuine import cycle
(`classic_matches` -> tier-B module -> `classic_matches`), which breaks
whenever a Tier-B module (or a test importing one) happens to be the
first thing imported. Keeping this model here, with `classic_matches.py`
re-exporting it for backward compatibility, avoids the cycle entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Literal, Optional

from ..engine.match_engine import MatchResult

Tier = Literal["base", "bonus"]


@dataclass
class Objective:
    key: str
    tier: Tier
    description: str
    # (result, home_code_or_name, away_code_or_name) -> bool. The checker
    # only ever needs team NAMES (MatchResult.stats/player_stats are keyed
    # by Team.name, confirmed in rugby_sim/engine/match_engine.py) - the
    # extra two positional args exist so a single generic `check` fn can be
    # parameterized per-match without a closure per entry.
    check: Callable[[MatchResult], bool]


@dataclass
class ClassicMatch:
    id: str
    tournament: str  # "rwc" | "six_nations" | "rugby_championship"
    year: int
    display_name: str
    date: str
    home_code: str
    home_name: str
    away_code: str
    away_name: str
    blurb: str
    real_score: str
    # Which side the match's objectives are actually about (per Rugby 08's
    # "Classic Rugby" mode convention: you draft only this side; the other
    # side auto-drafts from its own real pool, same as any AI opponent
    # elsewhere in this project) - always "home" or "away", never both/none.
    focus_team: Literal["home", "away"] = "home"
    objectives: List[Objective] = field(default_factory=list)
    # True for a real single-elimination/final/semi-final/quarter-final/
    # historical-knockout match (a genuine tie there, in real rugby, always
    # goes to extra time -> sudden death -> a kicking competition - see
    # `MatchEngine.decide_winner` - never just ends level). Threaded into
    # the live `MatchEngine` for this match's `/start` -> live-match flow
    # (see `webapp.py`). Defaults to False - every pool-stage/regular-
    # season entry (round-robin Six Nations/Rugby Championship rounds,
    # Rugby World Cup pool matches) stays genuinely draw-eligible, exactly
    # as real rugby allows there.
    must_have_winner: bool = False
    # Real venue this match was actually played at - a key into
    # `rugby_sim.data.sources.venues.VENUES` (e.g. "twickenham",
    # "stade_de_france"). `None` only for an entry whose real venue hasn't
    # been researched/added yet - never guessed. Combined with the real
    # `date` above, this is what lets `/api/classic_matches/<id>/start`
    # look up real historical weather for the match (see
    # `rugby_sim.data.sources.historical_weather`).
    venue: Optional[str] = None


# ---------------------------------------------------------------------------
# Generic, parameterized objective-type vocabulary. Each returns an
# `Objective` already bound to a real match's two team names. Deliberately a
# SMALL, FIXED set of types (not one-off hand code per match) - see the
# plan's "Objective model" section. `PlayerMatchStats` now has a
# `drop_goals` field too (added once the engine actually started
# simulating drop goals - see `MatchEngine`'s outcome menu), but no
# `player_drop_goals_at_least` objective type was added here - the
# existing `team_drop_goals_at_least` already covers every match that
# currently references a drop goal, and drop goals are rare enough per
# drive that a per-player threshold would mostly just be unreachable
# flavor, not a meaningful extra objective.
# ---------------------------------------------------------------------------


def win(team: str) -> Objective:
    def _check(result: MatchResult) -> bool:
        stats = result.stats
        if team not in stats:
            return False
        if result.home.name == team:
            return result.score_home > result.score_away
        if result.away.name == team:
            return result.score_away > result.score_home
        return False

    return Objective(f"win:{team}", "base", f"{team} win the match", _check)


def win_margin_at_least(team: str, margin: int) -> Objective:
    def _check(result: MatchResult) -> bool:
        if result.home.name == team:
            diff = result.score_home - result.score_away
        elif result.away.name == team:
            diff = result.score_away - result.score_home
        else:
            return False
        return diff >= margin

    return Objective(
        f"win_margin:{team}:{margin}", "base",
        f"{team} win by {margin}+ points", _check,
    )


def team_tries_at_least(team: str, n: int) -> Objective:
    def _check(result: MatchResult) -> bool:
        stats = result.stats.get(team)
        return stats is not None and stats.tries >= n

    return Objective(
        f"team_tries:{team}:{n}", "bonus",
        f"{team} score {n}+ tries", _check,
    )


def team_drop_goals_at_least(team: str, n: int) -> Objective:
    def _check(result: MatchResult) -> bool:
        stats = result.stats.get(team)
        return stats is not None and stats.drop_goals >= n

    return Objective(
        f"team_drop_goals:{team}:{n}", "bonus",
        f"{team} kick {n}+ drop goals", _check,
    )


def player_points_at_least(team: str, position_or_name: str, n: int) -> Objective:
    """`position_or_name`: matched against a `PlayerMatchStats.player`'s
    `natural_position.value` OR `name` (whichever matches, name first -
    lets a match target either "the left wing, whoever you draft there" or
    a specific real name)."""

    def _matches(ps) -> bool:
        if ps.team != team:
            return False
        if ps.player.name == position_or_name:
            return True
        return ps.player.natural_position.value == position_or_name

    def _check(result: MatchResult) -> bool:
        return any(_matches(ps) and ps.points >= n for ps in result.player_stats)

    return Objective(
        f"player_points:{team}:{position_or_name}:{n}", "bonus",
        f"A {position_or_name} for {team} scores {n}+ points", _check,
    )


def player_tries_at_least(team: str, position_or_name: str, n: int) -> Objective:
    def _matches(ps) -> bool:
        if ps.team != team:
            return False
        if ps.player.name == position_or_name:
            return True
        return ps.player.natural_position.value == position_or_name

    def _check(result: MatchResult) -> bool:
        return any(_matches(ps) and ps.tries >= n for ps in result.player_stats)

    return Objective(
        f"player_tries:{team}:{position_or_name}:{n}", "bonus",
        f"A {position_or_name} for {team} scores {n}+ tries", _check,
    )


def no_cards(team: str) -> Objective:
    def _check(result: MatchResult) -> bool:
        stats = result.stats.get(team)
        return stats is not None and stats.yellow_cards == 0 and stats.red_cards == 0

    return Objective(f"no_cards:{team}", "base", f"{team} finish with no cards", _check)


def no_injuries(team: str) -> Objective:
    def _check(result: MatchResult) -> bool:
        stats = result.stats.get(team)
        return stats is not None and stats.injuries == 0

    return Objective(f"no_injuries:{team}", "bonus", f"{team} finish with no injuries", _check)


def total_points_at_least(n: int) -> Objective:
    def _check(result: MatchResult) -> bool:
        return (result.score_home + result.score_away) >= n

    return Objective(
        f"total_points:{n}", "bonus",
        f"The match produces {n}+ combined points", _check,
    )
