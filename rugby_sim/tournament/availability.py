"""Tracks which players are unavailable for a tournament's upcoming
matches due to an in-match injury or a red card, for the "fresh squad every
match" mode (`Tournament(..., squads={...})` - see `tournament.py`). Pure
bookkeeping: it doesn't touch ratings or who gets picked, just which names
are allowed to be picked from for the *next* match.

Lay-off lengths are a simplified, documented heuristic - real recovery
times and disciplinary-panel suspensions vary hugely by injury/offense.
This is "plausible enough to matter", not a medical or disciplinary model.
An injury's actual layoff length varies by its rolled severity tier (see
`engine.match_engine.INJURY_SEVERITY_TIERS`) rather than one flat number -
`record_match` reads each injury's own `layoff_matches`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from ..engine.match_engine import MatchResult
from ..models.player import Player

INJURY_LAYOFF_MATCHES = 1  # fallback only - a real injury's own layoff comes
# from its rolled severity tier (`engine.match_engine.INJURY_SEVERITY_TIERS`,
# stored per-injury as `injury_details[i]["layoff_matches"]`); this constant
# is used only if a `MatchResult` has no `injury_details` for some reason
# (e.g. a hand-built test double), so old callers keep working unchanged.
RED_CARD_SUSPENSION_MATCHES = 1
# Yellow cards deliberately do NOT appear anywhere in this module: a yellow
# is purely an in-match sin-bin (see `engine/match_engine.py`) and does not,
# on its own, cost a player any future match under real World Rugby law -
# only a citation/disciplinary panel could do that, and (like this project's
# injury model) that process isn't simulated here. Only a red card (a
# first-time one, or one escalated from a second yellow to the same player
# in the same match - see `MatchEngine._issue_card`) sidelines a player,
# below.

# -- Short-rest condition penalty (stamina carryover between tournament
# matches, see `engine/match_engine.py`'s per-match stamina model and
# `data/sources/auto_draft.py`'s condition-aware greedy pick) --------------
# This project doesn't have real fixture dates for every tournament format
# (synthetic round-robins/knockouts have no calendar at all, and even the
# real-fixture formats are just an ordered list, not dated - see
# `real_fixtures.py`), so there's no way to compute actual days-of-rest
# between two fixtures. The honest, simple stand-in used here: a squad-mode
# player who was selected into their team's matchday squad (started OR was
# on the bench) for that team's MOST RECENT match starts their next match at
# a reduced condition, representing a quick turnaround; anyone not in that
# last squad (first match of the tournament, or genuinely rested out) starts
# at a full 100. This only tracks "one match ago", not a running fatigue
# total across a whole tournament - deliberately simple, flagged here rather
# than presented as a real travel/recovery model.
REST_PENALTY_CONDITION = 70.0  # starting condition for someone in last match's squad


@dataclass
class TournamentAvailability:
    # (team_name, id(player)) -> matches still remaining they must sit out,
    # counting from (and not including) the match that caused it.
    _sidelined: Dict[Tuple[str, int], int] = field(default_factory=dict)
    # team_name -> set of id(player) selected (started or benched) in that
    # team's most recently resolved match - see REST_PENALTY_CONDITION above.
    _last_squad: Dict[str, Set[int]] = field(default_factory=dict)

    def mark_squad(self, team_name: str, player_ids: Set[int]) -> None:
        """Call right after building the lineup that's about to play this
        team's next match (before the result is known) - records who's in
        it so the match AFTER THIS ONE can apply the short-rest penalty."""
        self._last_squad[team_name] = set(player_ids)

    def starting_condition(self, team_name: str, pool: List[Player]) -> Dict[int, float]:
        """`{id(player): starting condition}` for `MatchEngine`'s
        `initial_condition` - only players who need a penalty appear here;
        anyone absent defaults to a fresh 100 (see `MatchEngine.start`)."""
        last = self._last_squad.get(team_name)
        if not last:
            return {}
        return {id(p): REST_PENALTY_CONDITION for p in pool if id(p) in last}

    def filter_available(self, team_name: str, pool: List[Player]) -> List[Player]:
        """The subset of `pool` that isn't currently sidelined for this
        team - what a fresh per-match draft is actually allowed to pick
        from."""
        return [p for p in pool if self._sidelined.get((team_name, id(p)), 0) <= 0]

    def is_sidelined(self, team_name: str, player: Player) -> bool:
        return self._sidelined.get((team_name, id(player)), 0) > 0

    def matches_remaining(self, team_name: str, player: Player) -> int:
        """How many MORE of this team's matches `player` currently has to
        sit out, as of right now - not the original injury's tier length,
        since matches may already have ticked that down (see
        `record_match`). 0 if they're not currently sidelined at all."""
        return max(0, self._sidelined.get((team_name, id(player)), 0))

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

        # `injury_details` is appended to in lockstep with `injured_players`
        # (one entry each, same call, same order - see
        # `MatchEngine._apply_injury`), so zipping them lines up each injury
        # with its own severity/layoff record. A result without
        # `injury_details` (e.g. a hand-built test double) falls back to the
        # flat `INJURY_LAYOFF_MATCHES`.
        details = list(getattr(result, "injury_details", []))
        for i, (team_name, player) in enumerate(result.injured_players):
            detail = details[i] if i < len(details) else {}
            layoff = detail.get("layoff_matches", INJURY_LAYOFF_MATCHES)
            if layoff <= 0:
                continue  # e.g. a "knock" - no layoff for the next match
            key = (team_name, id(player))
            self._sidelined[key] = max(self._sidelined.get(key, 0), layoff)

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
