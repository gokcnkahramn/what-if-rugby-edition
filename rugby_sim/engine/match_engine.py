"""Detailed phase-by-phase national-team match simulator.

The model is deliberately "what if"-first: every probability is derived
from the *lineup* the user built (ratings per position, including the
out-of-position fit penalty from `Player.rating_at`), not from any notion
of the real historical result. Put Jonah Lomu at fullback and the engine
will actually weigh his pace/footwork/aerial numbers at fullback's profile.

How a drive's outcome is decided: each drive is one weighted dice roll
across a fixed menu of outcomes (try / penalty conceded by the defense, at
the breakdown or the scrum / card / penalty conceded by the attack /
lineout turnover / handling error / no outcome), not a separate phase-by-
phase simulation of rucks, mauls, scrums and lineouts individually. Each
outcome's probability is a baseline plus a swing term built from the
*edge* between the two teams' relevant `team_sub_rating` categories (e.g.
`p_scrum_penalty` swings with `scrum_atk - scrum_def`) - see `_resolve_drive`.
"Scrum penalty" vs "breakdown penalty" are therefore driven by genuinely
different inputs (scrum fitness/scrummaging vs team discipline), but both
still resolve through the same single per-drive roll, not independent
set-piece-by-set-piece contests.

How a team rating is built from individual fit scores: `Player.rating_at`
gives one player's 0-100 fit at one position (position-profile-weighted
attributes, penalized if it's not their natural position). `sub_ratings`
turns that into per-category contributions (scrum/lineout/tackling/attack/
kicking/goal_kicking/handling/aerial all scaled by `fit/100`; `discipline`
is NOT fit-scaled - indiscipline isn't really position-dependent).
`Lineup`/`MatchEngine` then average those contributions into one team-level
number per category - and, since `CATEGORY_POSITION_GROUPS`
(`models/position.py`), only across the starters actually involved in that
category (scrum: front row + locks; lineout: locks + back row; lineout
throwing: the hooker; aerial: back three + locks; tactical kicking:
9/10/15) - not a flat average of all 15, which used to dilute a strong
front row's scrum rating with two wingers who barely scrummage. Categories
not in that map (tackling, attack, handling, discipline) are deliberately
whole-team averages, since those really are universal involvements.

In-match injuries and substitutions: each drive carries a small chance of
an injury to a random on-field player, and (in a ~50th-75th minute window)
a smaller chance of a tactical/fatigue substitution. Either swaps in the
best-fitting available bench player at that position (standard rugby cap
of 8 replacements per team); if a team has no bench player left when an
injury happens, it plays the rest of the match a player short (same rating
penalty machinery as a red card) rather than leaving an empty slot.
Ratings are read from a per-match *working copy* of the starting XV
(`_active`), never the original `Lineup`, so the same `Team` object can be
reused for another match unaffected by what happened in this one.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..models.team import Team, Lineup, SquadSlot
from ..models.position import Position, BACKS, CATEGORY_POSITION_GROUPS
from ..models.player import Player
from .commentary import CommentaryEvent

MATCH_MINUTES = 80
MAX_SUBSTITUTIONS = 8

# Per-drive probabilities for the two kinds of in-match personnel change.
P_INJURY_PER_DRIVE = 0.012
P_TACTICAL_SUB_PER_DRIVE = 0.02
TACTICAL_SUB_WINDOW = (50, 75)  # minute range tactical subs are allowed in


@dataclass
class TeamMatchStats:
    tries: int = 0
    conversions: int = 0
    penalty_goals: int = 0
    drop_goals: int = 0
    turnovers_won: int = 0
    handling_errors: int = 0
    penalties_conceded: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    possessions: int = 0
    territory_pct: float = 0.0
    injuries: int = 0
    substitutions: int = 0


@dataclass
class PlayerMatchStats:
    """A player's individual contribution to one match - built from the
    same events that already drive the commentary log (who scored each
    try, who kicked each conversion/penalty), not a separate simulation."""
    player: Player
    team: str
    tries: int = 0
    conversions: int = 0
    penalty_goals: int = 0

    @property
    def points(self) -> int:
        return self.tries * 5 + self.conversions * 2 + self.penalty_goals * 3

    @property
    def pom_score(self) -> float:
        """Heuristic Player-of-the-Match score - points scored, weighted
        slightly in favour of tries over the boot. Not an official award,
        just a read of what already happened in the match."""
        return self.tries * 6 + self.conversions * 2 + self.penalty_goals * 3


@dataclass
class MatchResult:
    home: Team
    away: Team
    score_home: int = 0
    score_away: int = 0
    events: List[CommentaryEvent] = field(default_factory=list)
    stats: Dict[str, TeamMatchStats] = field(default_factory=dict)
    player_stats: List[PlayerMatchStats] = field(default_factory=list)
    player_of_the_match: Optional[Player] = None
    # Specific players involved in an injury or a card this match - (team_name,
    # Player) / (team_name, Player, "yellow"|"red") - not just the team-level
    # counts in `stats`. Exists so a tournament can carry a layoff/suspension
    # forward to that player's *next* match (see `tournament/availability.py`);
    # a single match report has no use for this itself.
    injured_players: List[Tuple[str, Player]] = field(default_factory=list)
    carded_players: List[Tuple[str, Player, str]] = field(default_factory=list)

    @property
    def winner(self) -> Optional[Team]:
        if self.score_home == self.score_away:
            return None
        return self.home if self.score_home > self.score_away else self.away

    def scoreline(self) -> str:
        return f"{self.home.name} {self.score_home} - {self.score_away} {self.away.name}"

    def print_report(self) -> None:
        print(f"\n=== FULL TIME: {self.scoreline()} ===\n")
        for ev in self.events:
            print(ev)
        print()
        for team_name, s in self.stats.items():
            print(
                f"{team_name}: {s.tries} tries, {s.penalty_goals} pens, "
                f"{s.drop_goals} drop goals, {s.turnovers_won} turnovers won, "
                f"{s.handling_errors} errors, {s.penalties_conceded} pens conceded, "
                f"{s.yellow_cards} YC / {s.red_cards} RC, territory {s.territory_pct:.0f}%, "
                f"{s.injuries} injuries, {s.substitutions} subs"
            )
        if self.player_of_the_match:
            pom = next(
                (p for p in self.player_stats if p.player is self.player_of_the_match), None
            )
            extra = f" ({pom.points} pts)" if pom else ""
            print(f"\nPlayer of the Match: {self.player_of_the_match.name} ({pom.team if pom else ''}){extra}")
        top_scorers = sorted(self.player_stats, key=lambda p: p.points, reverse=True)[:5]
        if top_scorers:
            print("\nTop scorers:")
            for p in top_scorers:
                if p.points == 0:
                    continue
                print(
                    f"  {p.player.name} ({p.team}): {p.points} pts "
                    f"({p.tries} tries, {p.conversions} conv, {p.penalty_goals} pens)"
                )


class MatchEngine:
    def __init__(self, home: Team, away: Team, seed: Optional[int] = None,
                 weather: str = "dry"):
        self.home = home
        self.away = away
        self.weather = weather  # "dry" | "wet" | "windy" - mild modifiers
        self.rng = random.Random(seed)
        self._carded: Dict[str, List[int]] = {home.name: [], away.name: []}  # expiry minutes
        self._active: Dict[str, Dict[Position, SquadSlot]] = {}
        self._bench: Dict[str, List] = {}
        self._subs_used: Dict[str, int] = {home.name: 0, away.name: 0}
        self._player_stats: Dict[tuple, PlayerMatchStats] = {}  # keyed by (team_name, id(player))
        self._minute = 0
        self._territory_ticks: Dict[str, int] = {}
        self.result: Optional[MatchResult] = None
        self._started = False
        self._finalized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def minute(self) -> int:
        return self._minute

    def active_lineup(self, team: Team) -> Dict[Position, SquadSlot]:
        """The per-match working XV (reflects injuries/subs so far) for a
        team already in this match - for showing "who's on" when deciding
        a manual substitution."""
        return dict(self._active.get(team.name, {}))

    def bench_for(self, team: Team) -> List[Player]:
        return list(self._bench.get(team.name, []))

    def is_finished(self) -> bool:
        return self._started and self._minute >= MATCH_MINUTES and not self._has_live_advantage(self.result, self._minute)

    def start(self) -> None:
        """Validates both lineups and sets up the per-match working state
        (a copy of each starting XV - the original `Lineup` is never
        mutated, so the same `Team` can be reused for another match).
        Safe to call more than once; only the first call does anything."""
        if self._started:
            return
        for team in (self.home, self.away):
            problems = team.lineup.validate()
            if problems:
                raise ValueError(f"{team.name} lineup invalid: {problems}")

        for team in (self.home, self.away):
            self._active[team.name] = {
                pos: SquadSlot(position=slot.position, player=slot.player)
                for pos, slot in team.lineup.starters.items()
            }
            self._bench[team.name] = list(team.lineup.bench)

        self.result = MatchResult(home=self.home, away=self.away)
        self.result.stats[self.home.name] = TeamMatchStats()
        self.result.stats[self.away.name] = TeamMatchStats()
        self._minute = 0
        self._territory_ticks = {self.home.name: 0, self.away.name: 0}
        self._started = True

    def _advance_one_drive(self) -> None:
        attacking, defending = self._pick_attacking_team(self._territory_ticks)
        self._territory_ticks[attacking.name] += 1

        drive_minutes = self.rng.randint(1, 4)
        self._minute = min(MATCH_MINUTES, self._minute + drive_minutes)

        self._expire_cards(attacking, self._minute)
        self._expire_cards(defending, self._minute)

        self._resolve_drive(attacking, defending, self._minute, self.result)
        self._maybe_personnel_change(self._minute, self.result)

    def advance_to(self, minute: int) -> MatchResult:
        """Plays drives until at least `minute` has elapsed, or the match
        is already over - the building block for a pausable match: reach
        a checkpoint, optionally call `apply_substitution` (or make an
        injury/tactical change happen naturally), then call this again for
        the next checkpoint. `run()` is the backward-compatible one-shot
        version of this same machinery."""
        if not self._started:
            self.start()
        while self._minute < minute and not self.is_finished():
            self._advance_one_drive()
        return self.result

    def run_interactive(self, checkpoint_minutes: List[int], on_checkpoint) -> MatchResult:
        """Plays the match up to each minute in `checkpoint_minutes` (in
        order), calling `on_checkpoint(self, self.minute)` at each one
        before continuing - the hook a caller uses to pause, show the
        score/lineup so far, and optionally apply a manual substitution.
        Finishes the match (any remaining time + finalizing stats) after
        the last checkpoint."""
        self.start()
        for target in sorted(checkpoint_minutes):
            if self.is_finished():
                break
            self.advance_to(target)
            on_checkpoint(self, self._minute)
        return self.finish()

    def finish(self) -> MatchResult:
        """Plays out any remaining time and finalizes the `MatchResult`
        (territory %, player stats, Player of the Match). Safe to call
        more than once - finalizing only happens the first time."""
        if not self._started:
            self.start()
        while not self.is_finished():
            self._advance_one_drive()

        if not self._finalized:
            total_ticks = sum(self._territory_ticks.values()) or 1
            for team in (self.home, self.away):
                self.result.stats[team.name].territory_pct = (
                    100 * self._territory_ticks[team.name] / total_ticks
                )
            self.result.player_stats = list(self._player_stats.values())
            self.result.player_of_the_match = self._compute_player_of_the_match()
            self._finalized = True
        return self.result

    def run(self) -> MatchResult:
        """One-shot: play the full match and return the finalized report -
        unchanged behavior from before `start`/`advance_to`/`finish` existed
        to support pausing mid-match."""
        self.start()
        return self.finish()

    def _credit(self, team: Team, player, **increments) -> None:
        # Keyed by (team, player identity), not just player identity: the
        # exact same Player object can legitimately appear in both lineups
        # (e.g. two sides drafted from the same pool/sample list) and must
        # still be tracked as two separate per-team contributions.
        key = (team.name, id(player))
        ps = self._player_stats.get(key)
        if ps is None:
            ps = PlayerMatchStats(player=player, team=team.name)
            self._player_stats[key] = ps
        for field_name, amount in increments.items():
            setattr(ps, field_name, getattr(ps, field_name) + amount)

    def _pick_try_scorer(self, team: Team) -> "Player":
        """Weighted toward backs and players with a strong attacking
        profile at their current slot - not a uniform coin flip, but not a
        separate play-by-play simulation either."""
        slots = list(self._active[team.name].values())
        weights = []
        for slot in slots:
            attack = slot.player.sub_ratings(slot.position).get("attack", 50)
            weight = attack + (25 if slot.position in BACKS else 0)
            weights.append(max(weight, 1))
        return self.rng.choices(slots, weights=weights, k=1)[0].player

    def _compute_player_of_the_match(self) -> Optional["Player"]:
        if not self._player_stats:
            return None
        best = max(self._player_stats.values(), key=lambda ps: ps.pom_score)
        return best.player if best.pom_score > 0 else None

    def apply_substitution(self, team: Team, position: Position, bench_player: Optional[Player] = None) -> bool:
        """Manually bring a bench player on at `position` - the interactive
        "pause the match, make a substitution" control. `bench_player`
        picks exactly who comes on (must actually be on this team's bench
        right now); omit it to fall back to the best-fitting bench player
        for that slot, same as the old auto-only behavior. Returns False if
        the team has no bench player left, has used all 8 replacements, or
        `bench_player` isn't actually on the bench."""
        bench = self._bench.get(team.name)
        if not bench or self._subs_used[team.name] >= MAX_SUBSTITUTIONS:
            return False
        if bench_player is not None:
            if bench_player not in bench:
                return False
            replacement = bench_player
        else:
            replacement = max(bench, key=lambda p: p.rating_at(position))
        outgoing = self._active[team.name].get(position)
        bench.remove(replacement)
        self._subs_used[team.name] += 1
        self._active[team.name][position] = SquadSlot(position=position, player=replacement)
        if self.result is not None:
            self.result.stats[team.name].substitutions += 1
            self.result.events.append(self._event(
                self._minute, team,
                f"Substitution: {replacement.name} replaces "
                f"{outgoing.player.name if outgoing else '(empty slot)'} ({team.name}, {position.value}).",
                self.result,
            ))
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _active_card_penalty(self, team: Team) -> float:
        """Multiplier applied to a team's ratings while a man down."""
        n_down = len(self._carded[team.name])
        if n_down <= 0:
            return 1.0
        return max(0.6, 1.0 - 0.15 * n_down)

    def _expire_cards(self, team: Team, minute: int) -> None:
        self._carded[team.name] = [m for m in self._carded[team.name] if m > minute]

    def _team_sub_rating(self, team: Team, category: str) -> float:
        """Like `Lineup.team_sub_rating`, but sourced from the per-match
        working roster (`_active`), which injuries/subs can have changed -
        same position-group scoping (see `CATEGORY_POSITION_GROUPS`)."""
        group = CATEGORY_POSITION_GROUPS.get(category)
        all_slots = list(self._active[team.name].values())
        slots = [s for s in all_slots if s.position in group] if group else all_slots
        if not slots:
            slots = all_slots
        values = [slot.player.sub_ratings(slot.position).get(category, 50) for slot in slots]
        return sum(values) / len(values) if values else 50.0

    def _maybe_personnel_change(self, minute: int, result: MatchResult) -> None:
        """Rolls for an injury (any time) and, inside a mid-match window,
        a tactical/fatigue substitution - for each team, once per drive."""
        for team in (self.home, self.away):
            if self.rng.random() < P_INJURY_PER_DRIVE:
                self._apply_injury(team, minute, result)
            elif (
                TACTICAL_SUB_WINDOW[0] <= minute <= TACTICAL_SUB_WINDOW[1]
                and self._bench[team.name]
                and self._subs_used[team.name] < MAX_SUBSTITUTIONS
                and self.rng.random() < P_TACTICAL_SUB_PER_DRIVE
            ):
                self._apply_tactical_sub(team, minute, result)

    def _apply_injury(self, team: Team, minute: int, result: MatchResult) -> None:
        slots = list(self._active[team.name].items())
        if not slots:
            return
        position, slot = self.rng.choice(slots)
        injured = slot.player
        result.stats[team.name].injuries += 1
        result.injured_players.append((team.name, injured))

        bench = self._bench[team.name]
        if bench and self._subs_used[team.name] < MAX_SUBSTITUTIONS:
            replacement = max(bench, key=lambda p: p.rating_at(position))
            bench.remove(replacement)
            self._subs_used[team.name] += 1
            self._active[team.name][position] = SquadSlot(position=position, player=replacement)
            result.stats[team.name].substitutions += 1
            result.events.append(self._event(
                minute, team,
                f"Injury: {injured.name} ({team.name}) goes off at {position.value} - "
                f"{replacement.name} comes on.",
                result,
            ))
        else:
            # No cover left - the team plays the rest of the match a player
            # short, using the same rating-penalty machinery as a red card.
            self._carded[team.name].append(MATCH_MINUTES)
            result.events.append(self._event(
                minute, team,
                f"Injury: {injured.name} ({team.name}) goes off at {position.value} - "
                f"no replacements left, {team.name} continue a player short.",
                result,
            ))

    def _apply_tactical_sub(self, team: Team, minute: int, result: MatchResult) -> None:
        bench = self._bench[team.name]
        slots = list(self._active[team.name].items())
        if not slots or not bench:
            return
        # Bring on whichever bench player would be the biggest upgrade at
        # whichever position they'd replace - a simple proxy for "freshest
        # legs for a tiring starter" rather than a specific injury.
        position, slot = max(
            slots,
            key=lambda item: max(p.rating_at(item[0]) for p in bench) - item[1].player.rating_at(item[0]),
        )
        replacement = max(bench, key=lambda p: p.rating_at(position))
        outgoing = slot.player
        bench.remove(replacement)
        self._subs_used[team.name] += 1
        self._active[team.name][position] = SquadSlot(position=position, player=replacement)
        result.stats[team.name].substitutions += 1
        result.events.append(self._event(
            minute, team,
            f"Tactical substitution: {replacement.name} replaces {outgoing.name} "
            f"({team.name}, {position.value}).",
            result,
        ))

    def _has_live_advantage(self, result: MatchResult, minute: int) -> bool:
        return False

    def _pick_attacking_team(self, territory_ticks: Dict[str, int]):
        home_terr = self._territory_strength(self.home) * self._active_card_penalty(self.home)
        away_terr = self._territory_strength(self.away) * self._active_card_penalty(self.away)
        weather_adj = 1.0
        if self.weather == "windy":
            weather_adj = 0.9  # flattens differences, more chaos
        total = home_terr + away_terr
        home_prob = 0.5 if total == 0 else (home_terr / total) * weather_adj + (1 - weather_adj) * 0.5
        if self.rng.random() < home_prob:
            return self.home, self.away
        return self.away, self.home

    def _territory_strength(self, team: Team) -> float:
        return (
            self._team_sub_rating(team, "kicking") * 0.5
            + self._team_sub_rating(team, "aerial") * 0.3
            + self._team_sub_rating(team, "handling") * 0.2
        )

    def _resolve_drive(self, attacking: Team, defending: Team, minute: int, result: MatchResult):
        stats_a = result.stats[attacking.name]
        stats_a.possessions += 1

        atk_card_pen = self._active_card_penalty(attacking)
        def_card_pen = self._active_card_penalty(defending)

        attack_rating = self._team_sub_rating(attacking, "attack") * atk_card_pen
        handling_rating = self._team_sub_rating(attacking, "handling") * atk_card_pen
        discipline_atk = self._team_sub_rating(attacking, "discipline") * atk_card_pen
        tackling_def = self._team_sub_rating(defending, "tackling") * def_card_pen
        discipline_def = self._team_sub_rating(defending, "discipline") * def_card_pen
        scrum_atk = self._team_sub_rating(attacking, "scrum") * atk_card_pen
        scrum_def = self._team_sub_rating(defending, "scrum") * def_card_pen

        lineout_quality_atk = (
            self._team_sub_rating(attacking, "lineout")
            + self._team_sub_rating(attacking, "lineout_throw")
        ) / 2 * atk_card_pen
        lineout_def = self._team_sub_rating(defending, "lineout") * def_card_pen

        # Base probabilities, tuned so an evenly matched drive yields a try
        # roughly 1 time in 7-8, consistent with real Test rugby try counts.
        edge = (attack_rating - tackling_def) / 100  # roughly [-1, 1]
        p_try = self._clamp(0.11 + edge * 0.10, 0.02, 0.45)

        handling_edge = (handling_rating - 60) / 100
        p_error = self._clamp(0.16 - handling_edge * 0.10, 0.04, 0.35)

        discipline_edge = (70 - discipline_def) / 100
        p_pen_conceded_by_def = self._clamp(0.14 + discipline_edge * 0.12, 0.03, 0.35)

        discipline_edge_atk = (70 - discipline_atk) / 100
        p_pen_conceded_by_atk = self._clamp(0.08 + discipline_edge_atk * 0.10, 0.02, 0.30)

        scrum_edge = (scrum_atk - scrum_def) / 100
        p_scrum_penalty = self._clamp(0.04 + scrum_edge * 0.05, 0.0, 0.12)

        lineout_edge = (lineout_quality_atk - lineout_def) / 100
        p_lineout_turnover = self._clamp(0.05 - lineout_edge * 0.06, 0.01, 0.14)

        p_card = 0.015 * self._clamp(1.4 - discipline_atk / 70, 0.3, 2.0)

        roll = self.rng.random()
        cumulative = 0.0

        def take(p):
            nonlocal cumulative
            cumulative += p
            return roll < cumulative

        if take(p_try):
            self._score_try(attacking, minute, result)
        elif take(p_pen_conceded_by_def):
            self._score_penalty_chance(attacking, defending, minute, result)
        elif take(p_scrum_penalty):
            self._score_penalty_chance(attacking, defending, minute, result, via="scrum")
        elif take(p_lineout_turnover):
            result.stats[defending.name].turnovers_won += 1
            result.events.append(self._event(
                minute, defending,
                f"{defending.name} win the lineout - overthrow/steal from {attacking.name}.",
                result,
            ))
        elif take(p_card):
            is_red, carded_player = self._issue_card(defending, minute, result)
            card_word = "red card" if is_red else "yellow card"
            who = f"{carded_player.name} ({defending.name})" if carded_player else defending.name
            result.events.append(self._event(minute, defending, f"{who} is shown a {card_word}.", result))
        elif take(p_pen_conceded_by_atk):
            self._score_penalty_chance(defending, attacking, minute, result)
        elif take(p_error):
            stats_a.handling_errors += 1
            result.events.append(self._event(minute, attacking, f"{attacking.name} lose the ball - handling error, scrum to {defending.name}.", result))
            result.stats[defending.name].turnovers_won += 1
        else:
            result.events.append(self._event(minute, attacking, f"{attacking.name} work through the phases but {defending.name}'s defense holds firm.", result))

    def _issue_card(self, team: Team, minute: int, result: MatchResult) -> Tuple[bool, Optional[Player]]:
        is_red = self.rng.random() < 0.12
        duration = MATCH_MINUTES if is_red else 10
        self._carded[team.name].append(minute + duration)

        slots = list(self._active[team.name].values())
        carded_player = self.rng.choice(slots).player if slots else None

        if is_red:
            result.stats[team.name].red_cards += 1
            if carded_player is not None:
                result.carded_players.append((team.name, carded_player, "red"))
        else:
            result.stats[team.name].yellow_cards += 1
            if carded_player is not None:
                result.carded_players.append((team.name, carded_player, "yellow"))
        return is_red, carded_player

    def _best_kicker(self, team: Team):
        best_slot = max(
            self._active[team.name].values(),
            key=lambda slot: slot.player.attributes.goal_kicking,
        )
        return best_slot.player

    def _score_try(self, team: Team, minute: int, result: MatchResult):
        stats = result.stats[team.name]
        stats.tries += 1
        scorer = self._pick_try_scorer(team)
        self._credit(team, scorer, tries=1)
        result.events.append(self._event(minute, team, f"TRY! {scorer.name} ({team.name}) crosses the whitewash after a well-worked move.", result, add_score=(team, 5)))

        kicker = self._best_kicker(team)
        conv_prob = self._clamp(0.35 + kicker.attributes.goal_kicking / 150, 0.15, 0.95)
        if self.rng.random() < conv_prob:
            stats.conversions += 1
            self._credit(team, kicker, conversions=1)
            result.events.append(self._event(minute, team, f"{kicker.name} slots the conversion.", result, add_score=(team, 2)))
        else:
            result.events.append(self._event(minute, team, f"{kicker.name}'s conversion drifts wide.", result))

    def _score_penalty_chance(self, attacking: Team, defending: Team, minute: int, result: MatchResult, via: str = "foul"):
        conceded_by = defending
        stats_conceded = result.stats[conceded_by.name]
        stats_conceded.penalties_conceded += 1
        reason = "at the scrum" if via == "scrum" else "at the breakdown"
        result.events.append(self._event(minute, conceded_by, f"Penalty against {conceded_by.name} {reason}.", result))

        kicker = self._best_kicker(attacking)
        # Occasionally the attacking team kicks to the corner instead of at goal
        # (more likely with a weak kicker, deep territory heuristics omitted for simplicity).
        go_for_posts = self.rng.random() < 0.75 or kicker.attributes.goal_kicking > 70
        if not go_for_posts:
            result.events.append(self._event(minute, attacking, f"{attacking.name} kick to the corner instead of taking the points.", result))
            return

        pen_prob = self._clamp(0.55 + kicker.attributes.goal_kicking / 200, 0.3, 0.95)
        stats_atk = result.stats[attacking.name]
        if self.rng.random() < pen_prob:
            stats_atk.penalty_goals += 1
            self._credit(attacking, kicker, penalty_goals=1)
            result.events.append(self._event(minute, attacking, f"{kicker.name} kicks the penalty.", result, add_score=(attacking, 3)))
        else:
            result.events.append(self._event(minute, attacking, f"{kicker.name}'s penalty attempt is off target.", result))

    def _event(self, minute, team, text, result, add_score=None) -> CommentaryEvent:
        if add_score:
            scoring_team, pts = add_score
            if scoring_team is self.home:
                result.score_home += pts
            else:
                result.score_away += pts
        return CommentaryEvent(minute=minute, team=team.name, text=text, score_home=result.score_home, score_away=result.score_away)

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))
