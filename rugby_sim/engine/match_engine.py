"""Detailed phase-by-phase national-team match simulator.

See `MATCH_ENGINE_MODEL.md` (same directory) for the full, honest account of
how a match is actually decided: which attributes drive each drive-outcome
probability, the exact formulas, and a direct list of what this engine does
NOT model (it's a drive-by-drive weighted-dice-roll abstraction, not a
phase-by-phase physical simulation - despite this docstring's own name).

The model is deliberately "what if"-first: every probability is derived
from the *lineup* the user built (ratings per position, including the
out-of-position fit penalty from `Player.rating_at`), not from any notion
of the real historical result. Put Jonah Lomu at fullback and the engine
will actually weigh his pace/footwork/aerial numbers at fullback's profile.

How a drive's outcome is decided: the once-per-possession events (a card,
or the starting scrum/lineout producing a penalty or turnover) are each one
weighted dice roll, checked once per drive in `_resolve_drive` - these
genuinely only happen once per possession, not once per phase. The
open-play part of the drive is then a bounded LOOP of per-phase rolls
(`_resolve_phase`, up to `MAX_PHASES_PER_DRIVE` times), across a fixed menu
of outcomes (try / drop goal / penalty conceded by the defense / breakdown
turnover / penalty conceded by the attack / handling error / continue to
the next phase) - a "continue" keeps the drive alive and credits real
carry/tackle/ruck stats, any other outcome ends it. Each outcome's
probability is a baseline plus a swing term built from the *edge* between
the two teams' relevant `team_sub_rating` categories (e.g. `p_scrum_penalty`
swings with `scrum_atk - scrum_def`) - see `_resolve_drive`/`_resolve_phase`.
Set-piece (scrum penalty, lineout turnover) and breakdown/open-play outcomes
(breakdown turnover, driven by the defense's `tackle_technique` - dominant
hits + jackal threat - against attacking handling) are deliberately separate
swing terms with different inputs, so a scrum-dominant pack and a
jackal-heavy back row produce different, distinguishable match signatures
rather than both just moving one shared discipline number. This is still
not independent, continuous set-piece-by-set-piece or ruck-by-ruck physical
resolution - a deliberate scope limit, not an oversight - but it is a real,
multi-step phase loop now, not a single roll for the whole possession (see
`MATCH_ENGINE_MODEL.md`'s "What kind of simulation this is" for the full
account, including exactly what changed and what didn't).

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

Cards: a yellow card is a 10-minute sin-bin (`_issue_card`); a red card is
off for the rest of the match (modeled as a sin-bin lasting `MATCH_MINUTES`,
i.e. it never expires before full time), with no replacement brought on -
the team simply plays the rest of the match a player short (same rating
penalty machinery, `_active_card_penalty`, that a no-cover injury uses). A
second yellow card for the SAME player in the SAME match is escalated to a
red (real World Rugby law 19.2), tracked per-player for the match's
duration regardless of whether the first yellow's 10 minutes have actually
elapsed - see `_issue_card`. This project does NOT model the newer,
still-trialled "20-minute red card" law variant (where the team can bring
on a like-for-like replacement after 20 minutes following a send-off,
trialled in parts of the game since 2024-2026) - every red card here is the
older, simpler "player's gone, team's down a body for good" version, the
same as before this feature existed. Yellow cards do NOT carry any
automatic suspension into a player's next match - only a real disciplinary
citation/panel process could do that in actual rugby law, and (consistent
with this project's existing stance on not modeling injury tribunals) that
process isn't modeled here; see `tournament/availability.py` for exactly
what a red card (and only a red card) costs a player going forward.

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
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

from ..models.team import Team, Lineup, SquadSlot
from ..models.position import Position, BACKS, FORWARDS, CATEGORY_POSITION_GROUPS, POSITION_PROFILES
from ..models.player import Player
from .commentary import CommentaryEvent


class Zone(Enum):
    """Where the ball is notionally on the pitch, labelled relative to each
    team's OWN try line (not physical pitch ends - so no halftime-swap
    handling is needed; "AWAY_22" always means "near the away team's own
    22," for as long as the match runs). This is the engine's first real
    field-position concept - see `MATCH_ENGINE_MODEL.md` item 3, previously
    an acknowledged gap ("no field position beyond the coarse territory-
    percentage tally... no distance-to-try-line modeling at all").

    5 zones (grown from an original 3 - see `_advance_zone`/`_resolve_drive`'s
    zone-gated `p_try`/`_score_penalty_chance`'s zone-gated kick realism):
    `HOME_TRYLINE` (right on/near the home team's own line - highest danger
    if the away team is attacking there, rare in practice), `HOME_22`,
    `MIDFIELD`, `AWAY_22`, `AWAY_TRYLINE`. Still a discrete, coarse model
    (5 buckets, not continuous distance or x/y coordinates) - a deliberate
    stepping stone, not a claim of full spatial realism."""
    HOME_TRYLINE = "home_tryline"
    HOME_22 = "home_22"
    MIDFIELD = "midfield"
    AWAY_22 = "away_22"
    AWAY_TRYLINE = "away_tryline"


class Side(Enum):
    """Which side of the pitch play is notionally on (left/middle/right,
    from a neutral onlooker's perspective - not relative to either team).
    A simple, independent-of-`Zone` dimension (see `_advance_side`) used
    only to bias which wing scores a try (`_pick_try_scorer`) and to add
    an honest flavor detail to try commentary - deliberately NOT yet
    weighted by either team's actual wing attributes (a plain random walk
    this pass), and deliberately not a full lateral-position model."""
    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"


# Try-probability multiplier by "where the ball is, relative to the
# ATTACKING team" (see `MatchEngine._zone_relative_to`): highest right on
# the defending team's own line, still high (but a notch lower) in their
# 22, a reduced chance at midfield, and a small-but-nonzero chance when the
# attack is pinned deep in its own territory (a length-of-field
# counterattack/intercept try should stay possible, just rare, and rarer
# still right on the attacking side's own line) - five deliberately simple,
# clearly-labelled constants, not a formula reverse-engineered to hit a
# target number. Tuned by running many seeds and eyeballing the
# try-rate-by-zone split (see `tests/test_territory_zone.py`), same
# "worked-example, many seeds, modest not dramatic" discipline this file's
# other tuning passes (stamina, home advantage) already followed.
ZONE_TRY_MULTIPLIER = {
    "attacking_tryline": 1.15,  # ball right on the DEFENDING team's own line
    "attacking_22": 1.0,        # ball in the DEFENDING team's 22 - try range
    "midfield": 0.4,
    "own_22": 0.08,             # attack pinned in their own 22 - rare, not impossible
    "own_tryline": 0.03,        # pinned right on their OWN line - genuinely rare
}

# Zone-gated penalty-kick realism (see `_score_penalty_chance`): how often
# the attacking side goes for posts rather than kicking for territory, and
# a flat adjustment to the actual kick's success probability, by the same
# zone keys `ZONE_TRY_MULTIPLIER` uses. `"own_22"`/`"own_tryline"` have no
# entry here - `_score_penalty_chance` short-circuits `go_for_posts = False`
# for both zones outright (too far out to realistically attempt, regardless
# of kicker skill).
ZONE_GO_FOR_POSTS_BASE = {
    "attacking_tryline": 0.97,
    "attacking_22": 0.92,
    "midfield": 0.75,
}
ZONE_PEN_PROB_ADJUST = {
    "attacking_tryline": 0.15,
    "attacking_22": 0.10,
    "midfield": 0.0,
}

MATCH_MINUTES = 80
MAX_SUBSTITUTIONS = 8

# -- Phase-by-phase drive resolution (Phase 4 of the match-engine-depth arc) -
# A drive used to be resolved as ONE weighted roll covering the whole
# possession. It's now a bounded loop of explicit phases (one ruck/tackle/
# carry exchange each) - `MAX_PHASES_PER_DRIVE` is a simulation safety valve
# (a real multi-phase rugby passage of play is commonly ~3-6 phases before a
# break), not a claimed real-world law, same role `SUDDEN_DEATH_CAP_MINUTES`
# already plays for the knockout state machine. `PHASE_TRY_RAMP` layers a
# small per-phase multiplier on top of the existing `ZONE_TRY_MULTIPLIER`
# (not replacing it): a try is still reachable from phase 1 if the zone is
# already deep in the defending team's territory (an instant line break/
# intercept stays possible), but is otherwise damped on the earliest phases
# and reaches full strength by phase 3 - this is what lets a quick-ball,
# high-edge attack still score in very few phases (a real "quick pass,
# 1-on-1 overlap" try) while a grinding, low-edge forwards drive takes
# longer, instead of every drive having an identical, phase-count-blind try
# chance the way the old single-roll model structurally had to.
MAX_PHASES_PER_DRIVE = 6
PHASE_TRY_RAMP: Dict[int, float] = {1: 0.3, 2: 0.7}

# -- Set-piece origin (Phase 5 of the match-engine-depth arc) --------------
# Every drive used to run the SAME scrum-penalty/lineout-turnover check,
# unconditionally - treating every one of a match's ~32 drives as a
# contested set piece, when a real Test match only has ~8-15 scrums and
# ~12-20 lineouts per team in 80 minutes. These two constants decide, once
# per drive, whether THIS possession actually started from a scrum, a
# lineout, or open play (a turnover/kick return/continuation) - tuned by
# running many seeds and counting realized scrums/lineouts per match
# against that real range, not invented to hit an exact number. The
# remainder (1 - these two) is `"open_play"`, which skips the set-piece
# check entirely and goes straight to the phase loop, same as before.
DRIVE_ORIGIN_SCRUM_PROB = 0.35
DRIVE_ORIGIN_LINEOUT_PROB = 0.40

# -- Knockout tiebreak (decide_winner=True only - see MatchEngine.__init__) -
# Real World Rugby knockout procedure when a tie, draws aren't allowed:
# extra time (2x10 = 20 min, played in FULL regardless of scoring during it
# - no sudden-death behavior inside normal extra time, that's real law) ->
# sudden death (first score wins, no fixed real-world time limit, but this
# engine's drive loop needs a termination bound - see SUDDEN_DEATH_CAP_MINUTES,
# a simulation safety valve, not a real rugby rule) -> a place-kick
# competition (`_run_kicking_competition`) if STILL level after the cap.
EXTRA_TIME_MINUTES = 20
SUDDEN_DEATH_CAP_MINUTES = 20
# Kicking-competition shape (5 kicks per side from the 22m line, alternating,
# then sudden-death kicks if still level after 5 - confirmed against current
# World Rugby knockout tournament rules).
KICK_COMPETITION_ROUNDS = 5
# Safety valve for the sudden-death-kicks loop (see _run_kicking_competition) -
# not a real rule, just a termination guarantee for a degenerate RNG run.
KICK_COMPETITION_SAFETY_CAP = 50

# -- Home advantage (real, small, scoped - see `home_advantage` below) -----
# Deliberately mirrors `rankings.HOME_ADVANTAGE` (3.0) for consistency: the
# same project already has one small, documented "home advantage" magnitude
# for the separate post-match ELO-style rating update, so a second,
# independently-invented number for this in-match effect would be an
# unjustified inconsistency. Not imported directly (this module shouldn't
# depend on `tournament/rankings.py`, the dependency runs the other way -
# `rankings.py` is tournament-layer, `match_engine.py` is engine-layer), so
# the value is mirrored here with a comment pointing at the source of truth.
HOME_ADVANTAGE_BONUS = 3.0

# Per-drive probabilities for the two kinds of in-match personnel change.
P_INJURY_PER_DRIVE = 0.012
# How much a fully exhausted team's injury risk multiplies by, on top of
# the baseline above (match-engine-depth Phase 14 - see
# `MatchEngine._team_fatigue_factor`) - 1.5 means a team at full tracked
# fatigue carries 2.5x the baseline per-drive injury risk; a fully fresh
# team is unaffected (multiplier of 1.0). Modest and bounded, same
# philosophy as every other fatigue-linked constant in this file.
INJURY_FATIGUE_MULTIPLIER = 1.5
P_TACTICAL_SUB_PER_DRIVE = 0.02
TACTICAL_SUB_WINDOW = (50, 75)  # minute range tactical subs are allowed in

# -- Stamina/fatigue (heuristic, documented honestly - no real sports-science
# fatigue model is being claimed here) --------------------------------------
# Every player starts a match at condition 100 (single friendlies and draft
# mode ALWAYS start here - see module docstring; tournament squads mode can
# start a player below 100, see `tournament/availability.py`). Condition
# decays every drive while a player is actively on the field, at a rate
# built from four small, separately-justified terms (see `_decay_stamina`
# and `_position_workload` below) instead of just one:
#   1. `Attributes.fitness` (the original, still the dominant term): a
#      fitness-50 player decays at the "base" rate, fitness 100 at half
#      that, fitness 1 at 1.5x that - not a physiological model, just a
#      plausible, tunable gradient so "fitness" has a visible payoff.
#   2. Position workload: reuses `POSITION_PROFILES` (`models/position.py`),
#      the SAME per-position attribute-weight table already used for rating
#      and sub-rating math - no new, parallel table invented. A position
#      whose profile already leans heavily on fitness/strength/scrummaging
#      (prop, lock, back row) is read as a position with heavier physical/
#      static-contact demand than one that doesn't (half-back, back three),
#      so it decays somewhat faster - a prop doing scrum after scrum vs. a
#      winger who sprints in bursts but isn't in constant contact.
#   3. `Attributes.strength`: a small extra fatigue cost for bigger players,
#      on the plausible one-line reasoning that more strength usually comes
#      with carrying/tackling more contact load per minute on the pitch.
#   4. `Attributes.pace`: a small extra fatigue cost for faster players, on
#      the plausible one-line reasoning that a quicker player covers more
#      ground per minute of actual play, which is itself tiring.
# Plus one team-level, matchup-aware term (not per-player): a team facing a
# stronger attacking opponent than its own defense tires a little faster,
# reusing the SAME `attack`/`tackling` team_sub_ratings `_resolve_drive`
# already computes for the drive outcome rolls - no new signal invented,
# and the swing is kept modest (+/-10%) rather than dramatic.
STAMINA_DECAY_PER_MINUTE = 0.52
# Re-tuned (was 0.22, briefly, then before that 0.4): 0.22 made the realistic
# WORST case (low-fitness player, heaviest-physical-workload position -
# tighthead prop, see POSITION_WORKLOAD below - playing a full unassisted 80
# minutes under unfavorable matchup pressure) only reach condition ~68
# (drop ~32), nowhere near the documented STAMINA_FLOOR of 20 - the floor was
# effectively unreachable by anything but a hand-crafted extreme. Traced the
# actual formula (see `_decay_stamina`): decay_rate for that worst-case
# combination tops out around ~1.7-1.8 (well under STAMINA_RATE_MAX=2.2, so
# the rate clamp was never the binding constraint - STAMINA_DECAY_PER_MINUTE
# itself was). 0.52 is the smallest value, empirically verified via a real
# `MatchEngine` run over drafted squads (not a hand-wavy estimate), at which
# that worst-case combination's drop over a full match lands convincingly
# close to the 20 floor (empirically ~76-80 points down, i.e. final
# condition ~20-24) while a TYPICAL player in a typical match - using the
# same formula's own existing fitness/position/strength/pace/matchup spread,
# not flattened - still lands noticeably higher (empirically ~38 points
# down on average, final ~62), clearly distinct from "every player ends up
# stuck around 60" since that was the typical/AVERAGE outcome, not a rare
# worst case.
STAMINA_FLOOR = 20.0  # a gassed player still plays, just at reduced effectiveness
# How much a player's condition actually softens their rating contribution:
# at condition 100 this is 1.0 (no change); at the floor (20) it's 0.76 - a
# deliberately modest effect (fatigue should be noticeable late in a tight
# match, not swing the whole simulation on its own). This mapping is
# unchanged by the richer decay-rate formula above - only how FAST a player
# reaches a given condition changed, not what a given condition is worth.
STAMINA_MIN_FACTOR = 0.7
STAMINA_MAX_FACTOR = 1.0
# Overall per-minute decay-rate multiplier is clamped to this range so that
# stacking four inputs (vs. the original one) can't produce a wildly more
# extreme swing than before - the old formula alone ranged 0.5x-1.5x; this
# keeps the combined result in a comparably modest neighborhood.
STAMINA_RATE_MIN = 0.3
STAMINA_RATE_MAX = 2.2

# -- Per-phase involvement stamina (match-engine-depth Phase 7) ------------
# The team-wide decay above (`_decay_stamina`, once per DRIVE) already
# scales with `drive_minutes`, but `drive_minutes` is an unrelated random
# roll (1-4, no attribute input at all - see its own comment) - a drive
# that grinds through 6 real phases (lots of carries/tackles/rucks) could
# easily roll the SAME `drive_minutes` as a drive that scores clean on
# phase 1, so both cost the SAME team-wide stamina regardless of how much
# actual physical involvement happened. This adds a small, SEPARATE extra
# cost on top of that unchanged team-wide decay: only the specific player
# actually credited with a carry or a tackle that phase (see
# `_credit_phase_continue`) pays it - so a team's go-to ball-carrier/
# go-to tackler genuinely tires faster over a match than a teammate who's
# rarely involved, which the old once-per-drive-only model had no way to
# express at all. Deliberately small (a single phase's involvement costs
# far less than a whole drive's team-wide decay) so it doesn't require
# re-tuning the whole `STAMINA_DECAY_PER_MINUTE` calibration above.
PHASE_INVOLVEMENT_STAMINA_COST = 0.4

# -- Match stats/analysis system (match-engine-depth Phase 16) -------------
# `_credit_phase_continue`'s own `metres` roll (4 + edge*8, clamped 1-15)
# is already a real, simulated-from-the-edge number - this just names the
# threshold above which that same carry also counts as "beating a
# defender" (a real rugby stats category), not a new invented roll.
# Verified live (not guessed): even a strongly attack-favoured matchup's
# realistic edge range rarely pushes `metres` much past 5, so a threshold
# of 8 (the original draft) would have NEVER fired in practice - 5 is the
# value this engine's own real edge distribution actually reaches.
DEFENDERS_BEATEN_METRES_THRESHOLD = 5
# How many real metres one zone-step (`_advance_zone`) represents, for
# `kicking_metres` - the 5-zone model spans roughly 100m of real pitch
# across 4 steps (tryline to tryline), so ~22m per step is the honest,
# already-implied real distance, not a separately invented number.
KICKING_METRES_PER_ZONE_STEP = 22

# Position "physical workload" signal for stamina decay, derived from
# `POSITION_PROFILES` rather than a new table: the share of each position's
# total attribute weight that sits on fitness/strength/scrummaging - the
# three weights in that table that are already, independently, about
# physical/contact demand. 0 for positions with none of those three
# weighted at all (most backs), up to ~0.8 for tighthead prop. Computed
# once at import time, not hand-tuned per position.
def _compute_position_workload() -> Dict[Position, float]:
    workload = {}
    for position, profile in POSITION_PROFILES.items():
        total = sum(profile.values()) or 1.0
        physical = profile.get("fitness", 0.0) + profile.get("strength", 0.0) + profile.get("scrummaging", 0.0)
        workload[position] = physical / total
    return workload


POSITION_WORKLOAD: Dict[Position, float] = _compute_position_workload()

# Manager-selectable tactics (match-engine-depth, manager-controls pass):
# real, named choices a user can pick for their own team before/during a
# live match, each resolving to the same [-1, 1] scale the three tendency
# methods already compute from real attributes - a chosen value REPLACES
# the derived one for that axis, it isn't blended with it. "balanced" is a
# genuine explicit choice (force a neutral 0.0), distinct from leaving the
# axis unset entirely (which keeps the attribute-derived default).
TACTIC_CHOICES: Dict[str, Dict[str, float]] = {
    "attack_shape": {"forward_heavy": 0.8, "balanced": 0.0, "backs_heavy": -0.8},
    "defensive_style": {"blitz": 0.8, "balanced": 0.0, "drift": -0.8},
    "kick_tendency": {"kick_heavy": 0.8, "balanced": 0.0, "ball_in_hand": -0.8},
}

# A manager's preferred kick TYPE - a strategic, pre-match preference (not
# a per-phase pop-up, which would mean interrupting a live match dozens of
# times a game - unrealistic for a "pick your gameplan" control). Reusing
# `_tactics_override`'s own per-team dict (a new, separate key,
# `"kick_style"`, not one of `TACTIC_CHOICES`'s [-1,1] overrides - this one
# is a label, not a number) so it rides the exact same `tactics={team:
# {...}}` request shape the other three axes already use. "auto"/missing
# means no preference (every kick type keeps its existing attribute-driven
# odds); any other value gives that ONE kick type's probability a real,
# bounded boost (see `KICK_STYLE_BOOST` at each kick type's own `take(...)`
# call) - never a 100% guarantee (the underlying skill/zone/defensive-style
# gates described at each kick type still apply; a manager can't make a
# fly-half with poor `kicking_game` land a grubber just by picking it).
KICK_STYLE_CHOICES = ("grubber", "chip", "cross_field", "box_kick")
KICK_STYLE_BOOST = 1.6

# The real choices a decision-team manager can make for a just-awarded
# penalty (see `MatchEngine.resolve_pending_decision`). "posts" is only
# ever a valid choice when `_pending_penalty["can_go_for_posts"]` is True
# (own-22/own-tryline penalties stay realism-gated, see
# `_apply_penalty_decision`) - webapp.py validates against this list.
PENALTY_CHOICES = ("posts", "touch", "quick_tap")

# Thresholds for `team_tactical_identity` below - same [-1, 1] scale
# `MatchEngine._kick_tendency` already uses live, mid-match (see that
# method's own docstring); these just name three bands of it for display.
TACTICAL_IDENTITY_THRESHOLD = 0.35


def team_tactical_identity(lineup: Lineup) -> str:
    """Labels a team's natural attacking tendency - kick-heavy/territorial
    vs. ball-in-hand/expansive vs. balanced - purely from the STARTING
    lineup's own kicking/handling sub-ratings (`Lineup.team_sub_rating`,
    no new manual data, no new per-team setting to invent). Same formula
    `MatchEngine._kick_tendency` already applies live, mid-match (reading
    the per-match working roster instead of the static starting lineup) to
    nudge `_advance_zone`'s odds - this is the same signal, just computed
    from the pre-match team sheet so it can be shown on a report/team-sheet
    screen, not only inferred from watching a live match unfold. A real,
    attribute-derived label, not a cosmetic flavor string: swap in a
    kicking-heavy backline and this label genuinely changes."""
    kicking = lineup.team_sub_rating("kicking")
    handling = lineup.team_sub_rating("handling")
    tendency = max(-1.0, min(1.0, (kicking - handling) / 40))
    if tendency >= TACTICAL_IDENTITY_THRESHOLD:
        return "Kick-heavy / territorial"
    if tendency <= -TACTICAL_IDENTITY_THRESHOLD:
        return "Ball-in-hand / expansive"
    return "Balanced"


def team_defensive_identity(lineup: Lineup) -> str:
    """Labels a team's natural defensive organization - blitz/rush vs.
    drift vs. balanced - purely from the STARTING lineup's own
    `tackle_technique`/`positioning` sub-ratings. Same formula
    `MatchEngine._defensive_style` already applies live, mid-match (see
    its own docstring and match-engine-depth Phase 12) - this is the same
    signal, computed from the pre-match team sheet."""
    technique = lineup.team_sub_rating("tackle_technique")
    positioning = lineup.team_sub_rating("positioning")
    style = max(-1.0, min(1.0, (technique - positioning) / 40))
    if style >= TACTICAL_IDENTITY_THRESHOLD:
        return "Blitz / rush defence"
    if style <= -TACTICAL_IDENTITY_THRESHOLD:
        return "Drift defence"
    return "Balanced"

# -- Injury severity (heuristic, documented honestly - not a medical model) -
# When an injury happens (see `_apply_injury`), one of these tiers is rolled
# (weighted, not uniform) to decide how many of that player's team's FUTURE
# matches they miss - real recovery time obviously varies continuously and
# by injury specifics, but a small, named, inspectable table beats inventing
# a continuous "days to heal" formula we have no data to back up. "knock"
# (a stinger/bruise/HIA-type knock) can mean going off for this match with
# no lingering layoff at all; the more severe tiers cost 1-3 further
# matches. Each tuple is (name, selection weight, matches missed
# afterwards - this match itself doesn't count). Tune the weights/layoffs
# here, nowhere else - `availability.py` just reads whatever is rolled.
INJURY_SEVERITY_TIERS: Tuple[Tuple[str, float, int], ...] = (
    ("knock", 0.45, 0),
    ("muscle strain", 0.30, 1),
    ("significant injury", 0.18, 2),
    ("serious injury", 0.07, 3),
)

# Named injury TYPE (match-engine-depth Phase 14) - a separate axis from
# severity above: "what got hurt", not "how bad". (name, selection weight).
# Rolled independently of severity (an ankle can be a minor knock or a
# serious injury) with ONE honest, well-known real-rugby exception:
# `_apply_injury` forces a concussion's severity to at least "muscle
# strain" (never a same-match "knock" with zero lay-off), reflecting the
# real graduated return-to-play/HIA protocol every major union actually
# follows - concussions are never waved off as a same-match non-issue.
INJURY_TYPES: Tuple[Tuple[str, float], ...] = (
    ("hamstring strain", 0.20),
    ("ankle sprain", 0.18),
    ("shoulder injury", 0.15),
    ("knee injury", 0.12),
    ("calf strain", 0.12),
    ("rib injury", 0.10),
    ("concussion", 0.08),
    ("groin strain", 0.05),
)


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
    # Emerge from the phase-by-phase drive loop (see `_resolve_phase`/
    # `MAX_PHASES_PER_DRIVE`), credited only on a "continue" phase (the
    # attack retains clean ball) - a real, simulated-from-within-the-model
    # byproduct, not a separately invented stat. `rucks_won` is team-level
    # only: this model has no real per-player "who won the ruck"
    # attribution to draw on, same honesty convention as everywhere else
    # in this file.
    carries: int = 0
    metres_gained: int = 0
    tackles_made: int = 0
    tackles_missed: int = 0
    rucks_won: int = 0
    # Only incremented on a drive whose "possession origin" roll actually
    # came up scrum/lineout (see `DRIVE_ORIGIN_SCRUM_PROB`/
    # `_resolve_scrum`/`_resolve_lineout`) - team-level only, same
    # "no real per-player attribution" convention as `rucks_won` (the
    # commentary still names a specific player for flavor/credit, the
    # counting stat just doesn't).
    scrums_won: int = 0
    lineouts_won: int = 0
    # Match stats/analysis system (match-engine-depth Phase 16): every
    # field below is credited at the EXACT SAME points the engine already
    # resolves these real outcomes - no new rolls, no new probabilities,
    # purely additional bookkeeping on events that already happen.
    # `scrums_contested`/`lineouts_contested` (every scrum-/lineout-origin
    # drive, win or lose) are what make a real success RATE possible
    # (`scrums_won/scrums_contested`), not just a raw count.
    scrums_contested: int = 0
    lineouts_contested: int = 0
    # Credited on the SAME "continue" phase as `carries`/`metres_gained` -
    # a carry that gains a real, meaningful chunk of ground (see
    # `_credit_phase_continue`'s own threshold comment) counts as beating
    # a defender, the same honest "derived from the real simulated edge,
    # not invented" convention every other phase-loop stat already uses.
    defenders_beaten: int = 0
    # The mirror of `turnovers_won`/`rucks_won`: credited to the ATTACKING
    # team on the exact same breakdown-turnover/handling-error outcomes
    # that already credit the defending team's `turnovers_won` - two sides
    # of the same real event, not a separately invented stat.
    turnovers_conceded: int = 0
    rucks_lost: int = 0
    # Territorial box kicks only (`_resolve_phase`'s kicking-system part 2 -
    # a cross-field kick is a try-scoring play, not a territorial exchange,
    # so it's deliberately NOT counted here). `kicking_metres` estimates
    # real distance from the actual simulated zone step gained (see
    # `KICKING_METRES_PER_ZONE_STEP`), not an invented number.
    kicks_attempted: int = 0
    kicks_successful: int = 0
    kicking_metres: int = 0
    # A drive that reached the defending team's 22/tryline at least once
    # (the real rugby "red zone") vs. one that also finished with a try -
    # tracked at drive granularity (see `_resolve_drive`'s own flag), the
    # natural level "red zone efficiency" is actually talked about at in
    # real rugby (entries, not every individual phase already inside it).
    red_zone_possessions: int = 0
    red_zone_tries: int = 0


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
    drop_goals: int = 0
    carries: int = 0
    metres_gained: int = 0
    tackles_made: int = 0
    tackles_missed: int = 0
    defenders_beaten: int = 0
    turnovers_won: int = 0

    @property
    def performance_score(self) -> float:
        """A single, documented "match performance" number (match stats
        system, item 14) - a weighted blend of every REAL per-player stat
        already collected above, not a separate invented metric. Scoring
        is weighted heaviest (same relative weights as `pom_score`'s own
        tries/kicks split), with carrying/tackling/turnover involvement
        contributing a smaller, genuine amount - so a non-scoring prop who
        put in a heavy shift can still post a real, non-zero number,
        instead of "performance" meaning only "did you score"."""
        return (
            self.tries * 10 + self.conversions * 3 + self.penalty_goals * 5 + self.drop_goals * 5
            + self.carries * 0.5 + self.metres_gained * 0.2 + self.defenders_beaten * 1.0
            + self.tackles_made * 1.0 - self.tackles_missed * 0.5 + self.turnovers_won * 2.0
        )

    @property
    def points(self) -> int:
        return self.tries * 5 + self.conversions * 2 + self.penalty_goals * 3 + self.drop_goals * 3

    @property
    def pom_score(self) -> float:
        """Heuristic Player-of-the-Match score - points scored, weighted
        slightly in favour of tries over the boot. Not an official award,
        just a read of what already happened in the match."""
        return self.tries * 6 + self.conversions * 2 + self.penalty_goals * 3 + self.drop_goals * 3


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
    # Structured, display-ready detail for each injury in `injured_players`
    # (same events, just with the minute/position already pulled out instead
    # of making a caller re-parse the commentary text) - for the web UI's
    # "Injuries this match" / tournament-wide injury report (see README).
    injury_details: List[dict] = field(default_factory=list)
    # Same idea as `injury_details`, but for `carded_players` - minute/card
    # type plus whether this was a real law-19.2 "second yellow -> red"
    # escalation for this specific player in this match (see `_issue_card`),
    # not just a raw first-time red. For the web UI's "Cards this match" /
    # tournament-wide card report (see README).
    card_details: List[dict] = field(default_factory=list)
    # The genuine real-world home side's name, if this match had one, or
    # None at a neutral venue - mirrors `MatchEngine.home_advantage`
    # (always scoped to `home`, never `away`; see that flag's docstring).
    # Lets a frontend decide, e.g., which side's scoring sound effects
    # match real stadium atmosphere, without re-deriving it itself.
    home_advantage_for: Optional[str] = None
    # Set only when `decide_winner=True` (see `MatchEngine.__init__`) and the
    # match was still level after extra time + the sudden-death cap, so a
    # place-kick competition (`_run_kicking_competition`) decided it - the
    # team name that won the kicking competition. NEVER implies the
    # scoreline itself changed: `score_home`/`score_away` stay exactly as
    # tied as the real match law records them (a shootout-decided knockout
    # match is still officially a draw on the scoreboard). `winner` below is
    # the one place that should be read to find out who actually goes
    # through.
    shootout_winner: Optional[str] = None
    # Display-ready detail for the frontend ("decided by a kicking
    # competition") - kicks taken/made per side plus who kicked first (the
    # one coin-flip randomness the real rule specifies).
    shootout_detail: Optional[dict] = None

    @property
    def winner(self) -> Optional[Team]:
        # `shootout_winner` (if set) is checked first and is the single
        # source of truth every caller should use - see its field comment
        # above. Falls back to the plain score comparison otherwise, same
        # as before shootouts existed (so a legitimate pool-stage/friendly
        # draw, where `decide_winner` was never set, still correctly
        # returns None here).
        if self.shootout_winner is not None:
            return self.home if self.shootout_winner == self.home.name else self.away
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
                 weather: str = "dry", initial_condition: Optional[Dict[int, float]] = None,
                 home_advantage: bool = False, decide_winner: bool = False,
                 tactics: Optional[Dict[str, Dict[str, str]]] = None,
                 decision_teams: Optional[Iterable[str]] = None):
        """`tactics`, if given, lets a manager pick a real tactical stance
        for one or both sides instead of leaving it purely attribute-
        derived - keyed by team NAME, each a dict with up to 3 keys
        (`"attack_shape"`, `"defensive_style"`, `"kick_tendency"`), each a
        string from `TACTIC_CHOICES` (see that constant). A team/axis not
        present keeps today's exact behavior: the tendency stays fully
        derived live from the real lineup's own attributes
        (`_attack_shape_tendency`/`_defensive_style`/`_kick_tendency`), a
        substitution/injury still shifts it mid-match. A chosen tactic is a
        real override (not a nudge on top of the derived value) - the
        manager's explicit call replaces the auto-derived number for that
        axis for the rest of the match, same as a human coach's real
        pre-match gameplan overriding what the squad "naturally" would do.

        `decision_teams`, if given, names which team(s) (by real team NAME)
        get a genuine in-match decision point instead of the AI's usual
        auto-pick, for the one outcome this currently covers: what to do
        with a just-awarded penalty (kick for posts / kick to touch / a
        quick tap) - see `_pending_penalty`/`resolve_pending_decision`. A
        team not listed here (the default: no team at all) is completely
        unaffected, auto-deciding exactly as before this existed. This is
        the SAME single mechanism a live/pausable match's checkpoint system
        already uses to stop and wait for the caller - `advance_to`'s loop
        also stops the instant a decision is pending, even mid-checkpoint.
        `initial_condition`, if given, maps `id(player)` -> starting
        stamina (0-100) for any player who should NOT start this match at a
        fresh 100 - the hook tournament squads mode uses to carry a
        short-rest penalty into a player's next match (see
        `tournament/availability.py`). Omit it (the default) for a single
        friendly or draft-mode match: every player starts at 100, no
        exceptions, exactly as before stamina existed.

        `home_advantage`, if True, gives `home` (not `away` - this engine
        has no opinion on which side that actually is; the caller decides,
        based on real fixture data) a small, documented territory-roll
        bonus (see `HOME_ADVANTAGE_BONUS`/`_pick_attacking_team`) - a real,
        honestly-scoped home-field effect, not a blanket one. Defaults to
        False: every existing caller that doesn't explicitly opt in (a
        single friendly, draft mode, a fully custom/synthetic tournament)
        is completely unaffected. This is keyed ONLY to which side is the
        genuine real-world home side for a specific fixture - never to
        which side is human- vs AI-controlled (`Tournament.my_team`), so it
        can't introduce any human/AI asymmetry; see `tournament.py` for how
        each real competition decides this per fixture.

        `decide_winner`, if True, means this fixture is a real single-
        elimination/must-have-a-winner knockout match: a tie at full time
        triggers extra time -> sudden death -> a kicking competition (see
        the EXTRA_TIME_MINUTES/SUDDEN_DEATH_CAP_MINUTES constants and
        `_run_kicking_competition`) instead of just ending level. Defaults
        to False: every existing caller that doesn't explicitly opt in (a
        single friendly, draft mode, a round-robin/pool-stage fixture) is
        completely unaffected and can still end in a genuine draw exactly
        as before this flag existed."""
        self.home = home
        self.away = away
        self.home_advantage = home_advantage
        self.decide_winner = decide_winner
        # Knockout-tiebreak state machine (only ever used when
        # `decide_winner` is True) - see `is_finished`/`_update_knockout_stage`/
        # `_current_period_cap`. `None` means "still in normal time, or the
        # tiebreak already resolved via a score difference" - it only ever
        # holds "extra_time"/"sudden_death"/"shootout_done" while actually
        # inside that stage.
        self._knockout_stage: Optional[str] = None
        self.weather = weather  # "dry" | "wet" | "windy" - mild modifiers
        self.rng = random.Random(seed)
        self._carded: Dict[str, List[int]] = {home.name: [], away.name: []}  # expiry minutes
        # Per-player card history for THIS match only (law 19.2: a second
        # yellow card shown to the SAME player in the SAME match is a send-
        # off, i.e. treated as a red for the rest of the match) - see
        # `_issue_card`. Keyed by id(player), not by slot, so it survives a
        # positional swap. `_sent_off` excludes a player who's already off
        # (red, including an escalated one) from being picked for any
        # further card - they're off the field, not just "down a player".
        self._yellow_history: Dict[str, set] = {home.name: set(), away.name: set()}
        self._sent_off: Dict[str, set] = {home.name: set(), away.name: set()}
        # Match-engine depth, phase 14: which POSITIONS are currently
        # missing a real body (a genuine send-off, or an injury with no
        # bench cover left) - used by `_team_sub_rating` to apply an extra,
        # category-specific penalty (losing a prop hurts scrum/lineout
        # more than it hurts kicking) on top of the existing flat
        # `_active_card_penalty`, instead of one uniform team-wide number
        # regardless of which position actually left the field.
        self._sent_off_positions: Dict[str, List[Position]] = {home.name: [], away.name: []}
        self._active: Dict[str, Dict[Position, SquadSlot]] = {}
        self._bench: Dict[str, List] = {}
        self._subs_used: Dict[str, int] = {home.name: 0, away.name: 0}
        self._player_stats: Dict[tuple, PlayerMatchStats] = {}  # keyed by (team_name, id(player))
        self._minute = 0
        self._territory_ticks: Dict[str, int] = {}
        self.result: Optional[MatchResult] = None
        self._started = False
        self._finalized = False
        self._initial_condition = initial_condition or {}
        self._stamina: Dict[int, float] = {}  # keyed by id(player) - see STAMINA_* above
        # Resolve the manager's chosen tactics (if any) to numeric overrides
        # once, up front - `TACTIC_CHOICES` maps each real label to the same
        # [-1, 1] scale `_attack_shape_tendency`/`_defensive_style`/
        # `_kick_tendency` already use, so a chosen value slots in exactly
        # where a derived one would. An unrecognized/missing axis is simply
        # left out (falls through to the derived value), never an error -
        # a manager picking tactics for only one of the two teams, or only
        # one of the three axes, is a normal, fully-supported case.
        self._tactics_override: Dict[str, Dict[str, float]] = {}
        self._kick_style_preference: Dict[str, str] = {}
        for team_name, axes in (tactics or {}).items():
            resolved = {}
            for axis, choice in (axes or {}).items():
                if axis == "kick_style":
                    if choice in KICK_STYLE_CHOICES:
                        self._kick_style_preference[team_name] = choice
                    continue
                value = TACTIC_CHOICES.get(axis, {}).get(choice)
                if value is not None:
                    resolved[axis] = value
            if resolved:
                self._tactics_override[team_name] = resolved
        self._decision_teams = set(decision_teams or [])
        # Set only while a decision-team penalty is awaiting the manager's
        # choice (see `_score_penalty_chance`/`resolve_pending_decision`);
        # `advance_to`/`_advance_one_drive` stop the instant this is set,
        # even mid-checkpoint, exactly like reaching a normal pause point.
        self._pending_penalty: Optional[dict] = None

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

    def condition_for(self, player: Player) -> float:
        """A player's current in-match stamina/condition (0-100, see the
        STAMINA_* constants) - 100 if they haven't been tracked yet (not
        started, or this match predates stamina tracking for them)."""
        return self._stamina.get(id(player), 100.0)

    def _stamina_factor(self, player: Player) -> float:
        condition = self.condition_for(player)
        span = STAMINA_MAX_FACTOR - STAMINA_MIN_FACTOR
        return STAMINA_MIN_FACTOR + span * self._clamp(condition / 100.0, 0.0, 1.0)

    def _matchup_pressure_factor(self, team: Team, opponent: Team) -> float:
        """Team-level decay multiplier from how much defensive pressure
        `team` is plausibly under this drive: reuses the same `attack` (for
        `opponent`) and `tackling` (for `team`) team_sub_ratings
        `_resolve_drive` already computes for its try/penalty rolls - no new
        signal invented. A team facing a materially stronger attacking
        opponent than its own defense scrambles/chases more and tires a
        little faster; kept modest (+/-10%, not dramatic)."""
        opp_attack = self._team_sub_rating(opponent, "attack")
        own_defense = self._team_sub_rating(team, "tackling")
        edge = self._clamp((opp_attack - own_defense) / 100.0, -0.5, 0.5)
        return 1.0 + edge * 0.2  # 0.9x .. 1.1x

    def _decay_stamina(self, team: Team, opponent: Team, drive_minutes: int) -> None:
        pressure_factor = self._matchup_pressure_factor(team, opponent)
        for slot in self._active[team.name].values():
            attrs = slot.player.attributes
            # (1) fitness - the original, still-dominant term.
            fitness_factor = 1.5 - attrs.fitness / 100.0  # 0.5 (fitness=100) .. 1.5 (fitness=0)
            # (2) position workload - see POSITION_WORKLOAD above.
            workload = POSITION_WORKLOAD.get(slot.position, 0.0)
            workload_factor = 0.85 + workload * 0.35  # ~0.85 .. ~1.13
            # (3) strength - more contact/carrying load per minute.
            strength_term = (attrs.strength - 50) / 100.0 * 0.15  # +/-0.075
            # (4) pace - more ground covered per minute.
            pace_term = (attrs.pace - 50) / 100.0 * 0.10  # +/-0.05

            decay_rate = fitness_factor * workload_factor * pressure_factor + strength_term + pace_term
            decay_rate = self._clamp(decay_rate, STAMINA_RATE_MIN, STAMINA_RATE_MAX)

            key = id(slot.player)
            current = self._stamina.get(key, 100.0)
            current -= STAMINA_DECAY_PER_MINUTE * decay_rate * drive_minutes
            self._stamina[key] = max(STAMINA_FLOOR, current)

    def bench_for(self, team: Team) -> List[Player]:
        return list(self._bench.get(team.name, []))

    def is_finished(self) -> bool:
        if not self._started:
            return False
        if self._minute < MATCH_MINUTES:
            return False
        if self._has_live_advantage(self.result, self._minute):
            return False
        if not self.decide_winner or self.result is None:
            return True
        # `decide_winner=True`: a knockout fixture never just ends level -
        # see the module docstring/`_update_knockout_stage` for the real
        # extra-time -> sudden-death -> kicking-competition procedure this
        # implements.
        tied = self.result.score_home == self.result.score_away
        if self._knockout_stage is None:
            # Normal time just ended (or the tiebreak already resolved via
            # a real score difference, and the stage was reset to None by
            # `_update_knockout_stage`) - finished unless still tied, in
            # which case the NEXT drive's `_update_knockout_stage` call
            # moves us into extra time.
            return not tied
        if self._knockout_stage == "extra_time":
            # Plays to its FULL fixed length regardless of any scoring
            # during it - real law, no sudden-death behavior in normal
            # extra time.
            return False
        if self._knockout_stage == "sudden_death":
            # Stops the INSTANT the score changes - checked every drive.
            return not tied
        # "shootout_done" - `_run_kicking_competition` already ran and set
        # `result.shootout_winner`; the scoreline itself stays tied.
        return True

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
            for slot in team.lineup.starters.values():
                self._stamina[id(slot.player)] = self._initial_condition.get(id(slot.player), 100.0)
            for p in team.lineup.bench:
                self._stamina[id(p)] = self._initial_condition.get(id(p), 100.0)

        self.result = MatchResult(
            home=self.home, away=self.away,
            home_advantage_for=self.home.name if self.home_advantage else None,
        )
        self.result.stats[self.home.name] = TeamMatchStats()
        self.result.stats[self.away.name] = TeamMatchStats()
        self._minute = 0
        self._territory_ticks = {self.home.name: 0, self.away.name: 0}
        self._zone = Zone.MIDFIELD
        self._side = Side.MIDDLE
        self._started = True

    def _advance_one_drive(self) -> None:
        attacking, defending = self._pick_attacking_team(self._territory_ticks)
        self._territory_ticks[attacking.name] += 1

        period_cap = self._current_period_cap()
        drive_minutes = self.rng.randint(1, 4)
        self._minute = min(period_cap, self._minute + drive_minutes)

        self._expire_cards(attacking, self._minute)
        self._expire_cards(defending, self._minute)
        self._decay_stamina(attacking, defending, drive_minutes)
        self._decay_stamina(defending, attacking, drive_minutes)

        self._resolve_drive(attacking, defending, self._minute, self.result)
        if self._pending_penalty is not None:
            # A decision-team penalty just paused resolution mid-drive -
            # don't run anything else (an injury/sub roll, the knockout
            # state check) until the manager's choice comes back via
            # `resolve_pending_decision`; those still happen normally once
            # this drive's outcome is actually finalized.
            return
        self._maybe_personnel_change(self._minute, self.result)
        self._update_knockout_stage()

    def _current_period_cap(self) -> int:
        """How far (in match minutes) the current drive is allowed to push
        `_minute` to, before `is_finished`/`_update_knockout_stage` need to
        look at the clock again - MATCH_MINUTES in normal time (unchanged
        behavior for every `decide_winner=False` caller), extended while a
        knockout tiebreak is in progress."""
        if self._knockout_stage == "extra_time":
            return MATCH_MINUTES + EXTRA_TIME_MINUTES
        if self._knockout_stage == "sudden_death":
            return MATCH_MINUTES + EXTRA_TIME_MINUTES + SUDDEN_DEATH_CAP_MINUTES
        return MATCH_MINUTES

    def _update_knockout_stage(self) -> None:
        """Drives the small `_knockout_stage` state machine one step,
        called once per drive (right after that drive's score is resolved) -
        see `is_finished` for how each stage affects when the match is
        considered over. No-op whenever `decide_winner` is False (every
        existing round-robin/pool/friendly match is completely unaffected)
        or before normal time has actually finished."""
        if not self.decide_winner or self.result is None:
            return
        if self._minute < MATCH_MINUTES:
            return
        tied = self.result.score_home == self.result.score_away

        if self._knockout_stage is None:
            if tied:
                self._knockout_stage = "extra_time"
                self.result.events.append(CommentaryEvent(
                    minute=self._minute, team="",
                    text=(
                        f"Full time: scores level at {self.result.score_home}-"
                        f"{self.result.score_away} - the match goes to extra time."
                    ),
                    score_home=self.result.score_home, score_away=self.result.score_away,
                ))
            return

        if self._knockout_stage == "extra_time":
            if self._minute >= MATCH_MINUTES + EXTRA_TIME_MINUTES:
                if tied:
                    self._knockout_stage = "sudden_death"
                    self.result.events.append(CommentaryEvent(
                        minute=self._minute, team="",
                        text=(
                            f"Extra time ends level at {self.result.score_home}-"
                            f"{self.result.score_away} - sudden death: next score wins."
                        ),
                        score_home=self.result.score_home, score_away=self.result.score_away,
                    ))
                else:
                    # Extra time itself produced a real decisive winner -
                    # reset to None so `is_finished`'s None-branch (`not
                    # tied` -> True) ends the match here, no further stage
                    # transitions needed.
                    self._knockout_stage = None
            return

        if self._knockout_stage == "sudden_death":
            if tied and self._minute >= MATCH_MINUTES + EXTRA_TIME_MINUTES + SUDDEN_DEATH_CAP_MINUTES:
                self._run_kicking_competition()
                self._knockout_stage = "shootout_done"
            # If no longer tied, `is_finished` already ends the match on
            # its own (`not tied` -> True) - no stage change needed here.
            return

    def advance_to(self, minute: int) -> MatchResult:
        """Plays drives until at least `minute` has elapsed, or the match
        is already over - the building block for a pausable match: reach
        a checkpoint, optionally call `apply_substitution` (or make an
        injury/tactical change happen naturally), then call this again for
        the next checkpoint. `run()` is the backward-compatible one-shot
        version of this same machinery."""
        if not self._started:
            self.start()
        while self._minute < minute and not self.is_finished() and self._pending_penalty is None:
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
        while not self.is_finished() and self._pending_penalty is None:
            self._advance_one_drive()

        if self._pending_penalty is not None:
            # A decision-team penalty is awaiting the manager's choice -
            # don't finalize (Player of the Match, territory %) on a match
            # that isn't actually over yet; the caller resumes via
            # `resolve_pending_decision` and calls `finish()`/`advance_to`
            # again afterwards.
            return self.result

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
        separate play-by-play simulation either. Also biased by
        `self._side` (see `Side`/`_advance_side`): when play is out on the
        left or right, that side's winger gets a further weight bump - at
        `Side.MIDDLE` nobody gets this bump, so the distribution matches
        exactly what it was before `Side` existed."""
        side_bonus_position = {Side.LEFT: Position.LEFT_WING, Side.RIGHT: Position.RIGHT_WING}.get(self._side)
        slots = list(self._active[team.name].values())
        weights = []
        for slot in slots:
            attack = slot.player.sub_ratings(slot.position).get("attack", 50)
            weight = attack + (25 if slot.position in BACKS else 0)
            if slot.position == side_bonus_position:
                weight += 20
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
        self._stamina[id(replacement)] = self._initial_condition.get(id(replacement), 100.0)
        if self.result is not None:
            self.result.stats[team.name].substitutions += 1
            self.result.events.append(self._event(
                self._minute, team,
                f"Substitution: {replacement.name} replaces "
                f"{outgoing.player.name if outgoing else '(empty slot)'} ({team.name}, {position.value}).",
                self.result,
            ))
        return True

    def swap_positions(self, team: Team, position_a: Position, position_b: Position) -> bool:
        """Swaps two of a team's own currently-on-field players between
        their two positions (e.g. fly-half <-> fullback mid-match) - NOT a
        substitution: nobody leaves the field, so this doesn't touch
        `_subs_used`/the 8-replacement cap, and isn't logged as one. Each
        player keeps their own tracked stamina (keyed by player identity,
        not by slot), so a tired player is still tired after moving
        position. Returns False if either position isn't currently filled
        for this team, or if the two positions are the same."""
        if position_a == position_b:
            return False
        active = self._active.get(team.name, {})
        slot_a = active.get(position_a)
        slot_b = active.get(position_b)
        if slot_a is None or slot_b is None:
            return False
        player_a, player_b = slot_a.player, slot_b.player
        active[position_a] = SquadSlot(position=position_a, player=player_b)
        active[position_b] = SquadSlot(position=position_b, player=player_a)
        if self.result is not None:
            self.result.events.append(self._event(
                self._minute, team,
                f"Positional swap: {player_a.name} and {player_b.name} swap "
                f"({position_a.value} <-> {position_b.value}) for {team.name}.",
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
        # Stamina softens every category's contribution a little (see
        # STAMINA_* above) - a tired team is a worse team at everything, not
        # just one stat, which is why this is applied here rather than
        # singled out to e.g. just tackling or handling.
        values = [
            slot.player.sub_ratings(slot.position).get(category, 50) * self._stamina_factor(slot.player)
            for slot in slots
        ]
        base = sum(values) / len(values) if values else 50.0

        # Position-specific card/injury impact (match-engine-depth Phase
        # 14): a flat team-wide `_active_card_penalty` already applies
        # everywhere a man is down, but losing a specific position hurts
        # the categories THAT position actually contributes to more than
        # it hurts an unrelated one (losing a prop should hurt scrum/
        # lineout harder than it hurts kicking) - an extra, targeted
        # penalty layered on top, only for the category group(s) a
        # genuinely missing position belongs to.
        if group and any(pos in group for pos in self._sent_off_positions.get(team.name, [])):
            base *= 0.85
        return base

    def _team_fatigue_factor(self, team: Team) -> float:
        """0 (fully fresh) to 1 (exhausted) - the team's current starting
        XV's average REAL tracked condition (`_stamina`), not a separate
        invented number. Feeds `_maybe_personnel_change`'s injury-risk
        scaling (match-engine-depth Phase 14) - a genuinely tired team
        should get hurt more often, which the old flat-probability model
        had no way to express at all."""
        slots = list(self._active[team.name].values())
        if not slots:
            return 0.0
        avg_condition = sum(self._stamina.get(id(s.player), 100.0) for s in slots) / len(slots)
        return self._clamp((100.0 - avg_condition) / 80.0, 0.0, 1.0)

    def _maybe_personnel_change(self, minute: int, result: MatchResult) -> None:
        """Rolls for an injury (any time) and, inside a mid-match window,
        a tactical/fatigue substitution - for each team, once per drive."""
        for team in (self.home, self.away):
            # Injury risk scaled by real match fatigue (match-engine-depth
            # Phase 14): `P_INJURY_PER_DRIVE` is still the baseline, but a
            # team playing at genuine fatigue (low average `_stamina`) now
            # carries up to `INJURY_FATIGUE_MULTIPLIER`x that baseline risk -
            # a real, modest, bounded link between tiredness and injury,
            # not a flat per-drive constant blind to how the match has
            # actually gone.
            fatigue = self._team_fatigue_factor(team)
            injury_prob = P_INJURY_PER_DRIVE * (1.0 + fatigue * INJURY_FATIGUE_MULTIPLIER)
            if self.rng.random() < injury_prob:
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
        # Fatigue-weighted victim pick (match-engine-depth Phase 14): a
        # more tired player is more likely to be the one who gets hurt,
        # not a uniform coin-flip among all 15 - reuses the SAME tracked
        # `_stamina` condition `_team_fatigue_factor` already reads, no new
        # signal invented. Floored at 1.0 so even a fully fresh player
        # keeps some (just much smaller) chance.
        weights = [max(1.0, 100.0 - self._stamina.get(id(slot.player), 100.0)) for _, slot in slots]
        position, slot = self.rng.choices(slots, weights=weights, k=1)[0]
        injured = slot.player
        result.stats[team.name].injuries += 1
        result.injured_players.append((team.name, injured))
        severity, _weight, layoff_matches = self.rng.choices(
            INJURY_SEVERITY_TIERS, weights=[t[1] for t in INJURY_SEVERITY_TIERS],
        )[0]
        injury_type = self.rng.choices(
            INJURY_TYPES, weights=[t[1] for t in INJURY_TYPES],
        )[0][0]
        if injury_type == "concussion" and layoff_matches == 0:
            # Real graduated return-to-play protocol - see `INJURY_TYPES`'
            # own comment. Re-roll severity from the tiers that actually
            # carry a lay-off, rather than hand-picking one tier (keeps
            # the real relative weights between "muscle strain"/
            # "significant"/"serious" intact).
            non_zero_tiers = [t for t in INJURY_SEVERITY_TIERS if t[2] > 0]
            severity, _weight, layoff_matches = self.rng.choices(
                non_zero_tiers, weights=[t[1] for t in non_zero_tiers],
            )[0]
        result.injury_details.append({
            "minute": minute, "team": team.name, "player": injured.name,
            "position": position.value, "type": injury_type,
            # See `INJURY_SEVERITY_TIERS` above - `layoff_matches` is this
            # specific injury's roll, read by `availability.record_match`
            # instead of a single flat constant.
            "severity": severity, "layoff_matches": layoff_matches,
        })

        bench = self._bench[team.name]
        if bench and self._subs_used[team.name] < MAX_SUBSTITUTIONS:
            replacement = max(bench, key=lambda p: p.rating_at(position))
            bench.remove(replacement)
            self._subs_used[team.name] += 1
            self._active[team.name][position] = SquadSlot(position=position, player=replacement)
            self._stamina[id(replacement)] = self._initial_condition.get(id(replacement), 100.0)
            result.stats[team.name].substitutions += 1
            result.events.append(self._event(
                minute, team,
                f"Injury: {injured.name} ({team.name}) goes off at {position.value} with a {injury_type} - "
                f"{replacement.name} comes on.",
                result,
            ))
        else:
            # No cover left - the team plays the rest of the match a player
            # short, using the same rating-penalty machinery as a red card.
            self._carded[team.name].append(MATCH_MINUTES)
            self._sent_off_positions[team.name].append(position)
            result.events.append(self._event(
                minute, team,
                f"Injury: {injured.name} ({team.name}) goes off at {position.value} with a {injury_type} - "
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
        # legs for a tiring starter" rather than a specific injury. The
        # starter's side of the comparison uses their *current* (stamina-
        # adjusted) rating, not their fresh one - this is the literal "why"
        # a tactical sub happens: a tired starter's effective rating has
        # dropped, making them look like a bigger upgrade target than an
        # equally-rated-on-paper but fresher teammate.
        position, slot = max(
            slots,
            key=lambda item: (
                max(p.rating_at(item[0]) for p in bench)
                - item[1].player.rating_at(item[0]) * self._stamina_factor(item[1].player)
            ),
        )
        replacement = max(bench, key=lambda p: p.rating_at(position))
        outgoing = slot.player
        bench.remove(replacement)
        self._subs_used[team.name] += 1
        self._active[team.name][position] = SquadSlot(position=position, player=replacement)
        self._stamina[id(replacement)] = self._initial_condition.get(id(replacement), 100.0)
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
        if self.home_advantage:
            # Small, real, scoped home-field nudge (see `HOME_ADVANTAGE_BONUS`
            # above) - added here, not blended into `_territory_strength`
            # itself, so it only ever affects the single territory roll this
            # method already makes, and never the kicking/aerial/handling
            # sub-ratings other code paths (e.g. tournament reports) read.
            home_terr += HOME_ADVANTAGE_BONUS
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

    def _kick_style_boost(self, team: Team, style: str) -> float:
        """A manager's pre-match `"kick_style"` preference (see
        `KICK_STYLE_CHOICES`/`KICK_STYLE_BOOST`) applied as a real, bounded
        probability multiplier - `KICK_STYLE_BOOST` for whichever kick type
        the manager actually picked, `1.0` (unchanged) for every other kick
        type and for a team with no preference at all. Never overrides the
        underlying skill/zone/defensive-style gates each kick type already
        has - a preference nudges the odds, it can't force an outcome."""
        return KICK_STYLE_BOOST if self._kick_style_preference.get(team.name) == style else 1.0

    def _kick_tendency(self, team: Team) -> float:
        """How much a team favours territorial kicking over ball-in-hand
        play, derived purely from the lineup's own existing attribute
        averages (no new manual data, no new per-team setting to invent) -
        roughly [-1, 1], positive = kicks more, negative = carries more.
        Read live every drive (like every other `_team_sub_rating` call in
        this file), so a substitution mid-match shifts it naturally. Used
        only to nudge `_advance_zone`'s advance probability (a kicking-
        heavy team gains territory faster) - a deliberately small, single-
        purpose use of this number, NOT a full tactical model (it doesn't
        yet model the extra turnover/counterattack risk a loose territorial
        kick concedes in real rugby - a natural candidate for a later pass,
        not bundled into this one). A manager-chosen "kick_tendency" tactic
        (see `TACTIC_CHOICES`) overrides this entirely for the rest of the
        match, same as a real coach's pre-match gameplan would."""
        override = self._tactics_override.get(team.name, {}).get("kick_tendency")
        if override is not None:
            return override
        kicking = self._team_sub_rating(team, "kicking")
        handling = self._team_sub_rating(team, "handling")
        return self._clamp((kicking - handling) / 40, -1.0, 1.0)

    def _defensive_style(self, team: Team) -> float:
        """Defensive organization (match-engine-depth Phase 12): [-1, 1],
        positive = blitz-leaning (a fast, aggressive rush defence - real
        rugby's "hard and fast" line that meets each attacker 1-on-1,
        strong against an overlap but risks a missed tackle/infringement
        if a defender mistimes the rush), negative = drift-leaning (a
        patient line that shifts across to cover the ball once it's
        passed, rarely beaten wide but gives up some central ground) - see
        rugbyslate.com's own "the drift defence"/"the blitz defence"
        articles, cross-checked earlier in this project's research.
        Derived purely from the team's own `tackle_technique` (aggressive
        technique) vs `positioning` (patient, structured defense)
        sub-ratings - no new manual per-team setting, same convention as
        `_kick_tendency`. Read live every drive, so a substitution shifts
        it naturally. A manager-chosen "defensive_style" tactic (see
        `TACTIC_CHOICES`) overrides this entirely for the rest of the
        match."""
        override = self._tactics_override.get(team.name, {}).get("defensive_style")
        if override is not None:
            return override
        technique = self._team_sub_rating(team, "tackle_technique")
        positioning = self._team_sub_rating(team, "positioning")
        return self._clamp((technique - positioning) / 40, -1.0, 1.0)

    def _attack_shape_tendency(self, team: Team) -> float:
        """Tactics/strategy system (match-engine-depth Phase 15): [-1, 1],
        positive = forward-heavy (favors going through the pack - the
        pick-and-go/driving-maul sub-scenarios), negative = backs-heavy
        (favors spreading it wide - the wing-break/cross-field/snipe
        individual tries). Derived purely from comparing the current
        starting XV's forwards' own `attack` sub-rating average against
        the backs' own (reusing `models.position.FORWARDS`/`BACKS`, no new
        manual per-team setting) - two squads with the same OVERALL
        strength but a different shape (a dominant pack vs. a dangerous
        backline) genuinely produce different, measurable tactical
        outcomes, which a single flat team-wide rating couldn't express.
        Read live every drive, so an injury/substitution shifts it
        naturally (e.g. losing a back for a forward on the bench pushes a
        team more forward-heavy for the rest of the match). A manager-
        chosen "attack_shape" tactic (see `TACTIC_CHOICES`) overrides this
        entirely for the rest of the match."""
        override = self._tactics_override.get(team.name, {}).get("attack_shape")
        if override is not None:
            return override
        slots = list(self._active[team.name].values())
        fwd_vals = [s.player.sub_ratings(s.position).get("attack", 50) for s in slots if s.position in FORWARDS]
        back_vals = [s.player.sub_ratings(s.position).get("attack", 50) for s in slots if s.position in BACKS]
        fwd_rating = sum(fwd_vals) / len(fwd_vals) if fwd_vals else 50.0
        back_rating = sum(back_vals) / len(back_vals) if back_vals else 50.0
        return self._clamp((fwd_rating - back_rating) / 25, -1.0, 1.0)

    def _score_pressure(self, team: Team, minute: int, result: MatchResult) -> float:
        """Tactics/strategy system, part 2: [-1, 1], positive = this team
        is chasing the game (behind on the scoreboard, genuinely more
        incentive to play attacking rugby and keep the ball alive -
        "backs to the wall"), negative = this team is closing it out
        (ahead late, genuinely more incentive to play conservative,
        territorial rugby and not gift the ball back). Derived purely
        from the REAL live scoreline (`result.score_home`/`score_away`)
        and `minute` - no new manual setting, and deliberately only
        meaningful in the second half (a 7-point gap at minute 10 means
        little; the same gap at minute 70 is a real in-game factor) - a
        flat `0.0` for the whole first half and for a close scoreline at
        any point, by design."""
        if minute < 40:
            return 0.0
        own_score = result.score_home if team is self.home else result.score_away
        opp_score = result.score_away if team is self.home else result.score_home
        diff = own_score - opp_score
        # Scaled so a 2-score game (14 points) at full time is close to the
        # extreme (+/-1), a one-score game (7) is a modest nudge - real
        # "game state" rugby commentary already talks about in these terms.
        # `urgency` itself rises through the second half (a given gap
        # matters more with 5 minutes left than with 35 left).
        urgency = self._clamp((minute - 40) / 40, 0.3, 1.0)
        return self._clamp(-diff / 14.0, -1.0, 1.0) * urgency

    # Opening-minutes "cagey start" window for each half - a real, if
    # informal, rugby convention rather than a law; chosen to be a small,
    # honest band, not tuned to hit a target number.
    PERIOD_CAUTION_WINDOW = 8
    PERIOD_CAUTION_FLOOR = 0.6

    def _period_caution_factor(self, minute: int) -> float:
        """1.0 (no change) outside the opening `PERIOD_CAUTION_WINDOW`
        minutes of either half; ramps down to `PERIOD_CAUTION_FLOOR` right
        at kickoff/the second-half restart, linearly back up to 1.0 by the
        end of the window - independent of the scoreline (see
        `_score_pressure` for the scoreline-driven tier; this is the purely
        clock-driven one)."""
        minute_in_half = minute if minute < 40 else minute - 40
        if minute_in_half >= self.PERIOD_CAUTION_WINDOW:
            return 1.0
        progress = minute_in_half / self.PERIOD_CAUTION_WINDOW
        return self.PERIOD_CAUTION_FLOOR + (1.0 - self.PERIOD_CAUTION_FLOOR) * progress

    # Fixed left-to-right ordering of the 5 zones (index 0 = home's own
    # line, index 4 = away's own line) - the single place every zone/index
    # translation below reads from, so adding/reordering a zone only ever
    # needs to change this one tuple.
    _ZONES = (Zone.HOME_TRYLINE, Zone.HOME_22, Zone.MIDFIELD, Zone.AWAY_22, Zone.AWAY_TRYLINE)

    def _advance_zone(self, attacking: Team, defending: Team, edge: float) -> None:
        """Moves `self._zone` one step toward the DEFENDING team's try line
        (advance), leaves it unchanged (hold), or moves it one step toward
        the ATTACKING team's own try line (retreat) - a single three-way
        weighted roll per drive, reusing `edge` (the attack-vs-tackling
        edge `_resolve_drive` already computed, no new attribute reads).
        Clamped at both ends: `HOME_TRYLINE`/`AWAY_TRYLINE` is as far as the
        ball can go in either direction. 5 zones (not 3) means it now takes
        longer, on average, to travel all the way from midfield to a
        tryline zone than the original 3-zone version did - a deliberate,
        more realistic side effect, not an oversight."""
        tendency = self._kick_tendency(attacking)
        # A blitz-leaning defence compresses the attacking team's space
        # (real rugby: a fast, aggressive rush line shuts down an overlap
        # before it can develop) - reduces the advance chance; a
        # drift-leaning defence doesn't get this bonus (drift's own
        # strength shows up elsewhere, in the individual break
        # probabilities below, not in raw territory).
        defensive_style = self._defensive_style(defending)
        p_advance = self._clamp(0.35 + edge * 0.15 + tendency * 0.05 - max(0.0, defensive_style) * 0.06, 0.1, 0.65)
        p_retreat = self._clamp(0.15 - edge * 0.10, 0.05, 0.3)
        toward_away = attacking is self.home  # home attacking -> ball moves toward AWAY_TRYLINE
        roll = self.rng.random()
        if roll < p_advance:
            step = 1 if toward_away else -1
        elif roll < p_advance + p_retreat:
            step = -1 if toward_away else 1
        else:
            return
        new_index = self._clamp(self._ZONES.index(self._zone) + step, 0, len(self._ZONES) - 1)
        self._zone = self._ZONES[int(new_index)]

    def _advance_side(self) -> None:
        """A simple, independent-of-`Zone` per-drive random walk for
        `self._side` (`Side.LEFT`/`MIDDLE`/`RIGHT`) - deliberately NOT yet
        weighted by either team's actual wing attributes (a plain,
        symmetric walk this pass - see `Side`'s own docstring). Used only
        to bias `_pick_try_scorer`'s wing weighting and to flavor try
        commentary."""
        sides = (Side.LEFT, Side.MIDDLE, Side.RIGHT)
        roll = self.rng.random()
        idx = sides.index(self._side)
        if roll < 0.3:
            step = -1
        elif roll < 0.6:
            step = 1
        else:
            return
        new_index = self._clamp(idx + step, 0, len(sides) - 1)
        self._side = sides[int(new_index)]

    def _zone_relative_to(self, attacking: Team) -> str:
        """Translates the absolute `self._zone` into one of 5 relative
        buckets ("attacking_tryline"/"attacking_22"/"midfield"/"own_22"/
        "own_tryline") from `attacking`'s own point of view, for
        `ZONE_TRY_MULTIPLIER`/`ZONE_GO_FOR_POSTS_BASE`/`ZONE_PEN_PROB_ADJUST`
        to key off."""
        idx = self._ZONES.index(self._zone)
        # From home's perspective, index 4 (AWAY_TRYLINE) is the most
        # advanced/attacking position; from away's perspective it's the
        # mirror image (index 0). `distance_from_attacking_end` is always
        # 0 at the zone nearest the DEFENDING team's own line (full
        # attacking danger) and 4 at the zone nearest the ATTACKING team's
        # own line (pinned deep in their own territory).
        distance_from_attacking_end = (len(self._ZONES) - 1 - idx) if attacking is self.home else idx
        return {
            0: "attacking_tryline",
            1: "attacking_22",
            2: "midfield",
            3: "own_22",
            4: "own_tryline",
        }[distance_from_attacking_end]

    def _resolve_drive(self, attacking: Team, defending: Team, minute: int, result: MatchResult):
        """Drive-level setup, done ONCE per possession (ratings don't
        meaningfully change within the few minutes a drive takes, and
        stamina is still only decayed once per drive - see the match-
        engine-depth plan's explicitly deferred "per-phase stamina" item):
        computes every team sub-rating, resolves the one-off set-piece/
        card checks that genuinely only happen once per possession (you
        don't re-contest the scrum or get carded twice for the same
        drive), then hands off to `_resolve_phase` - a bounded loop of
        individual ruck/tackle/carry exchanges - for the open-play part of
        the drive. See `MAX_PHASES_PER_DRIVE`'s comment for why this
        replaced the old "one roll decides the whole drive" model."""
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

        # Breakdown contest, kept separate from both the scrum penalty and
        # the lineout turnover above: driven by the defense's
        # tackle_technique (dominant hits + jackal/turnover threat, see
        # `attribute_mapping.py`) against the attack's handling, so a
        # jackal-heavy back row genuinely creates breakdown turnovers
        # independent of whether either side's scrum or lineout is strong.
        breakdown_def = self._team_sub_rating(defending, "tackle_technique") * def_card_pen
        breakdown_atk = self._team_sub_rating(attacking, "handling") * atk_card_pen

        # Base probabilities, tuned so an evenly matched drive yields a try
        # roughly 1 time in 7-8, consistent with real Test rugby try counts.
        edge = (attack_rating - tackling_def) / 100  # roughly [-1, 1]

        discipline_edge = (70 - discipline_def) / 100
        p_pen_conceded_by_def = self._clamp(0.14 + discipline_edge * 0.12, 0.03, 0.35)

        discipline_edge_atk = (70 - discipline_atk) / 100
        p_pen_conceded_by_atk = self._clamp(0.08 + discipline_edge_atk * 0.10, 0.02, 0.30)

        # A blitz-leaning defence rushes up fast and risks mistiming it -
        # a real, modest extra card risk (see `_defensive_style`'s own
        # docstring); a drift-leaning defence gets no such penalty (its
        # own risk/reward shows up in the individual break probabilities
        # instead, not in cards).
        defensive_style_card = self._defensive_style(defending)
        p_card = 0.015 * self._clamp(1.4 - discipline_def / 70, 0.3, 2.0) * (1 + max(0.0, defensive_style_card) * 0.3)

        # Card check: once per DRIVE, not per phase (a cynical/foul-based
        # card is a whole-possession event, not something re-rolled on
        # every ruck) - checked first, mutually exclusive with everything
        # else this drive, matching the old single-roll model's own
        # effective behavior (a card drive produced no try/penalty that
        # same drive either).
        if self.rng.random() < p_card:
            is_red, carded_player = self._issue_card(defending, minute, result)
            detail = result.card_details[-1] if result.card_details else None
            if detail and detail.get("escalated_second_yellow"):
                card_word = "second yellow card - RED CARD"
            else:
                card_word = "red card" if is_red else "yellow card"
            who = f"{carded_player.name} ({defending.name})" if carded_player else defending.name
            result.events.append(self._event(minute, defending, f"{who} is shown a {card_word}.", result))
            return

        # Possession origin: once per drive, decide whether this one
        # actually started from a scrum, a lineout, or open play (a
        # turnover/kick return/continuation) - see `DRIVE_ORIGIN_SCRUM_PROB`'s
        # comment for why this replaced the old "every drive is a contested
        # set piece" behavior. `"open_play"` falls straight through to the
        # phase loop below, unchanged.
        origin_roll = self.rng.random()
        if origin_roll < DRIVE_ORIGIN_SCRUM_PROB:
            if self._resolve_scrum(attacking, defending, scrum_atk, scrum_def, minute, result) != "continue":
                return
        elif origin_roll < DRIVE_ORIGIN_SCRUM_PROB + DRIVE_ORIGIN_LINEOUT_PROB:
            if self._resolve_lineout(attacking, defending, minute, result) != "continue":
                return

        # Drop goal: a modest, attribute-driven alternative the attacking
        # side's kicker can land instead of forcing a try/penalty chance -
        # real rugby's version of "settle for three when the line isn't
        # breaking." Driven by the designated kicker's own
        # `place_kicking_range` (execution - drop goals are typically
        # struck from longer range than a routine penalty) and
        # `game_intelligence` (the decision to actually go for the drop
        # rather than keep playing), same per-player-attribute convention
        # as the conversion/penalty-goal rolls (not a team sub-rating
        # average). Calibrated to a handful of successful drop goals per
        # 100 simulated matches combined - rare, never guaranteed,
        # occasionally zero for an entire match either side. Evaluated
        # fresh each phase below (the kicker could drop a goal at any
        # point in open play, not just once per drive).
        dg_kicker = self._best_kicker(attacking)
        dg_skill = (dg_kicker.attributes.place_kicking_range + dg_kicker.attributes.game_intelligence) / 2
        p_drop_goal = self._clamp(0.004 + (dg_skill - 55) / 1500, 0.001, 0.01)

        breakdown_edge = (breakdown_def - breakdown_atk) / 100
        p_breakdown_turnover = self._clamp(0.06 + breakdown_edge * 0.08, 0.01, 0.18)

        # Defensive organization (match-engine-depth Phase 12): a
        # blitz-leaning defence's aggressive, fast line creates MORE
        # breakdown pressure than its raw tackle_technique rating alone
        # suggests (real rugby: rushing up fast wins more jackal contests,
        # at the cost of the extra card risk added above) - a drift-leaning
        # defence gets no such bonus here (its strength shows up in the
        # individual break probabilities in `_resolve_phase` instead).
        defensive_style_breakdown = self._defensive_style(defending)
        p_breakdown_turnover = self._clamp(
            p_breakdown_turnover + max(0.0, defensive_style_breakdown) * 0.03, 0.01, 0.20
        )

        # Second player-specific decision behavior (match-engine-depth
        # Phase 8, same pattern as the scrum-half snipe try above): a
        # standout openside flanker's OWN `tackle_technique`/
        # `game_intelligence` (not the team-wide `breakdown_def` average
        # above) can create a real, individually-attributed extra jackal
        # threat - a team with an elite fetcher at 7 should turn the ball
        # over more often than its team-wide breakdown rating alone
        # suggests, same real-world distinction the review's "Dupont" ask
        # was about, applied to a second position.
        jackal_flanker = None
        jackal_bonus = 0.0
        of_slot = self._active[defending.name].get(Position.OPENSIDE_FLANKER)
        if of_slot is not None:
            jackal_flanker = of_slot.player
            fetcher_skill = (jackal_flanker.attributes.tackle_technique + jackal_flanker.attributes.game_intelligence) / 2
            jackal_bonus = self._clamp((fetcher_skill - 60) / 300, 0.0, 0.04)
        p_breakdown_turnover = self._clamp(p_breakdown_turnover + jackal_bonus, 0.01, 0.22)

        # Red zone tracking (match stats system - item 12): "did this
        # drive ever reach the defending team's 22/tryline" (a real rugby
        # "red zone possession"), checked after each phase's own zone
        # advance. A scoped simplification, documented honestly: this
        # covers the common open-play phase loop (and the two zone-gated
        # set-piece-try sub-scenarios, credited directly where they
        # happen) - an early drive exit before reaching here (a card, a
        # scrum/lineout penalty/turnover) doesn't update it, since those
        # aren't really "red zone" possessions in the usual rugby sense.
        reached_red_zone = False
        for phase_num in range(1, MAX_PHASES_PER_DRIVE + 1):
            outcome = self._resolve_phase(
                attacking, defending, phase_num, minute, result,
                edge=edge, handling_rating=handling_rating,
                p_pen_conceded_by_def=p_pen_conceded_by_def,
                p_pen_conceded_by_atk=p_pen_conceded_by_atk,
                p_breakdown_turnover=p_breakdown_turnover, jackal_flanker=jackal_flanker,
                dg_kicker=dg_kicker, p_drop_goal=p_drop_goal,
            )
            if self._zone_relative_to(attacking) in ("attacking_tryline", "attacking_22"):
                reached_red_zone = True
            if outcome != "continue":
                if reached_red_zone:
                    stats_a.red_zone_possessions += 1
                    if outcome == "try":
                        stats_a.red_zone_tries += 1
                return

        if reached_red_zone:
            stats_a.red_zone_possessions += 1

        # Reached MAX_PHASES_PER_DRIVE still "continuing" - the attack
        # couldn't finish what it started; the defense eventually resets
        # it. A simulation safety valve (see `MAX_PHASES_PER_DRIVE`), not a
        # claimed real rugby law.
        result.events.append(self._event(minute, attacking, f"{attacking.name} work through the phases but {defending.name}'s defense holds firm.", result))

    def _resolve_phase(
        self, attacking: Team, defending: Team, phase_num: int, minute: int, result: MatchResult,
        *, edge: float, handling_rating: float,
        p_pen_conceded_by_def: float, p_pen_conceded_by_atk: float, p_breakdown_turnover: float,
        jackal_flanker: Optional[Player],
        dg_kicker: "Player", p_drop_goal: float,
    ) -> str:
        """One ruck/tackle/carry exchange within a drive - see
        `MAX_PHASES_PER_DRIVE`'s comment for why a drive is now a bounded
        loop of these instead of one roll. Returns `"continue"` if the
        attack retains clean, usable ball (the loop keeps going), or a
        short tag naming whatever decisive outcome ended the drive."""
        stats_a = result.stats[attacking.name]

        # Defensive organization (match-engine-depth Phase 12): a
        # drift-leaning defence's own strength is specifically shutting
        # down individual breaks out wide/through a gap (real rugby: the
        # whole line shifts across to cover the ball, rarely beaten by one
        # player's own skill) - so it damps the individual break
        # probabilities below (snipe/wing-break/cross-field), never the
        # team-wide ones. A blitz-leaning defence gets no bonus here (its
        # own edge already showed up in `_advance_zone`/breakdown turnover/
        # cards above) - drift_factor is 1.0 (no change) for a blitz or
        # balanced defence, down to 0.5 at full drift.
        drift_factor = 1.0 - max(0.0, -self._defensive_style(defending)) * 0.5

        # Tactics/strategy system (match-engine-depth Phase 15): a
        # backs-heavy team's individual break probabilities (snipe/
        # wing-break/cross-field, all below) get a real boost from their
        # own `_attack_shape_tendency`; a forward-heavy team gets none here
        # (its own edge shows up in the pick-and-go/driving-maul
        # sub-scenarios instead - see `_resolve_scrum`/`_resolve_lineout`).
        # A team chasing the game (`_score_pressure` > 0, genuinely behind
        # late) also gets a boost here - real "backs to the wall" rugby;
        # a team closing out a lead gets a reduction instead (plays it
        # safer, doesn't force a risky individual play it doesn't need).
        backs_heavy_factor = 1.0 + max(0.0, -self._attack_shape_tendency(attacking)) * 0.4
        score_pressure = self._score_pressure(attacking, minute, result)
        pressure_factor = 1.0 + score_pressure * 0.3
        # Period-based strategy tier, independent of the scoreline: real
        # rugby's opening minutes of EITHER half are genuinely more
        # cautious - both sides are "feeling each other out," reluctant to
        # force a high-risk individual play before settling into the game
        # (commentary clichés like "a cagey start" reflect this). Damps the
        # same individual-break probabilities `_score_pressure` already
        # nudges, purely by match clock - a flat 1.0 (no change) once past
        # the opening stretch of each half.
        period_factor = self._period_caution_factor(minute)
        individual_break_factor = backs_heavy_factor * pressure_factor * period_factor

        p_try = self._clamp(0.11 + edge * 0.10, 0.02, 0.45) * PHASE_TRY_RAMP.get(phase_num, 1.0)

        # Zone: advance/hold/retreat the ball one step along the pitch
        # (reusing the attack/tackling edge already computed for this
        # drive - no new attribute reads), once per PHASE now (a longer,
        # multi-phase drive genuinely advances further than a one-phase
        # one - the old once-per-drive version couldn't express this at
        # all), THEN gate this phase's try chance by where the ball ended
        # up - see `_advance_zone`/`ZONE_TRY_MULTIPLIER`.
        self._advance_zone(attacking, defending, edge)
        self._advance_side()
        zone_rel = self._zone_relative_to(attacking)
        p_try *= ZONE_TRY_MULTIPLIER[zone_rel]

        # Player-specific decision behavior (a real Dupont-vs-an-average-9
        # distinction, not just a team-wide average): close to the
        # defending team's line, a sharp, fast scrum-half can sniff out a
        # gap and snipe over themselves - a genuinely individual read of
        # the game, not a team-level outcome. Driven by THIS specific
        # player's own `pace`/`game_intelligence` (not a team sub-rating),
        # so a world-class 9 behind an otherwise-average team still
        # produces a measurably higher snipe-try rate than a mediocre 9
        # behind the exact same team - see `MATCH_ENGINE_MODEL.md`.
        p_snipe = 0.0
        snipe_scrum_half = None
        if zone_rel in ("attacking_tryline", "attacking_22"):
            sh_slot = self._active[attacking.name].get(Position.SCRUM_HALF)
            if sh_slot is not None:
                snipe_scrum_half = sh_slot.player
                skill = (snipe_scrum_half.attributes.pace + snipe_scrum_half.attributes.game_intelligence) / 2
                p_snipe = self._clamp((skill - 60) / 400, 0.0, 0.05) * drift_factor * individual_break_factor

        # A third player-specific decision behavior (match-engine-depth
        # Phase 9, same pattern as the scrum-half snipe and the openside
        # flanker's jackal threat): the NEAR wing (matching the ball's
        # current `Side` - the real winger the attack is actually using,
        # not the far/blindside one) can beat the last defender on their
        # own footwork/pace when the ball is already close to the line -
        # a real "stepped the fullback" moment, driven by that ONE
        # player's own attributes, not a team-wide average.
        p_wing_break = 0.0
        wing_breaker = None
        if zone_rel in ("attacking_tryline", "attacking_22"):
            wing_position = {Side.LEFT: Position.LEFT_WING, Side.RIGHT: Position.RIGHT_WING}.get(self._side)
            if wing_position is not None:
                wing_slot = self._active[attacking.name].get(wing_position)
                if wing_slot is not None:
                    wing_breaker = wing_slot.player
                    wing_skill = (wing_breaker.attributes.footwork + wing_breaker.attributes.pace) / 2
                    p_wing_break = self._clamp((wing_skill - 60) / 350, 0.0, 0.05) * drift_factor * individual_break_factor

        # Kicking system detail, part 1 (match-engine-depth Phase 11): a
        # cross-field kick, a real named tactical option distinct from
        # ball-in-hand phases - the FLY-HALF's own `kicking_game`/
        # `game_intelligence` decides to put it up for the FAR wing (the
        # blindside one, opposite `self._side` - same "far wing stays
        # wide" convention the pitch-diagram formation already uses), who
        # finishes it on their OWN `aerial`/`pace`. Two named individuals
        # combining for one outcome, not a team-wide average either side.
        p_cross_field = 0.0
        cross_field_wing = None
        cross_field_flyhalf = None
        if zone_rel in ("attacking_tryline", "attacking_22") and self._side in (Side.LEFT, Side.RIGHT):
            fh_slot = self._active[attacking.name].get(Position.FLY_HALF)
            far_wing_position = {Side.LEFT: Position.RIGHT_WING, Side.RIGHT: Position.LEFT_WING}[self._side]
            far_wing_slot = self._active[attacking.name].get(far_wing_position)
            if fh_slot is not None and far_wing_slot is not None:
                cross_field_flyhalf = fh_slot.player
                cross_field_wing = far_wing_slot.player
                kick_skill = (cross_field_flyhalf.attributes.kicking_game + cross_field_flyhalf.attributes.game_intelligence) / 2
                catch_skill = (cross_field_wing.attributes.aerial + cross_field_wing.attributes.pace) / 2
                combined_skill = (kick_skill + catch_skill) / 2
                # Tactical reaction to the opponent's defensive style
                # (match-engine-depth Phase 15): real rugby's own "attacking
                # the drift" counter is exactly this - a cross-field ball
                # goes OVER a drifting line rather than through it, so a
                # drift defence's general `drift_factor` damping (which
                # correctly suppresses ground-level individual breaks like
                # the snipe/wing-break above) is partly offset here, unlike
                # for those other two.
                drift_counter_bonus = 1.0 + max(0.0, -self._defensive_style(defending)) * 0.6
                p_cross_field = (
                    self._clamp((combined_skill - 62) / 320, 0.0, 0.045)
                    * drift_factor * individual_break_factor * drift_counter_bonus
                    * self._kick_style_boost(attacking, "cross_field")
                )

        # Kicking system detail, follow-up: two more REAL, distinct kick
        # types (the "grubber/chip kick" gap left open in
        # `MATCH_ENGINE_MODEL.md`'s kicking-system section), each gated to
        # its own real rugby situation rather than being generic flavor
        # text on the existing box/cross-field kicks:
        #
        # Grubber kick - a low kick ALONG THE GROUND, only realistic right
        # on the defending team's line (`"attacking_tryline"` only, tighter
        # than cross-field's two-zone gate) - driven by the SCRUM-HALF's
        # own `kicking_game`/`game_intelligence` (a real scrum-half's grubber
        # through a forwards-heavy defensive line is the classic case, not
        # the fly-half's long cross-field ball above), finished by the
        # chasing NEAR wing (matching `self._side`, not the far one - a
        # grubber is chased on the SAME side it's kicked, unlike the
        # cross-field ball which deliberately goes to the blind side).
        p_grubber = 0.0
        grubber_scrum_half = None
        grubber_wing = None
        if zone_rel == "attacking_tryline" and self._side in (Side.LEFT, Side.RIGHT):
            sh_slot_grub = self._active[attacking.name].get(Position.SCRUM_HALF)
            near_wing_position = {Side.LEFT: Position.LEFT_WING, Side.RIGHT: Position.RIGHT_WING}[self._side]
            near_wing_slot = self._active[attacking.name].get(near_wing_position)
            if sh_slot_grub is not None and near_wing_slot is not None:
                grubber_scrum_half = sh_slot_grub.player
                grubber_wing = near_wing_slot.player
                kick_skill = (grubber_scrum_half.attributes.kicking_game + grubber_scrum_half.attributes.game_intelligence) / 2
                chase_skill = (grubber_wing.attributes.pace + grubber_wing.attributes.footwork) / 2
                combined_skill = (kick_skill + chase_skill) / 2
                p_grubber = (
                    self._clamp((combined_skill - 62) / 340, 0.0, 0.04)
                    * individual_break_factor * self._kick_style_boost(attacking, "grubber")
                )

        # Chip kick - over an ONRUSHING defensive line, the real counter to
        # a blitz defence (the fast, flat rush line that "negates the
        # overlap" - see `_defensive_style`'s own docstring): only a live
        # option while facing a genuinely blitz-leaning defence, in
        # midfield/the attacking 22 (not right on the line, where there's
        # no onrushing line left to chip over). Driven by the FLY-HALF's
        # `kicking_game`/`game_intelligence` (the decision + execution),
        # finished by the chasing near wing's `pace`/`footwork` - same
        # named-individual convention as every other kick type here.
        p_chip = 0.0
        chip_flyhalf = None
        chip_wing = None
        blitz_level = self._defensive_style(defending)
        if zone_rel in ("attacking_22", "midfield") and blitz_level > 0.15 and self._side in (Side.LEFT, Side.RIGHT):
            fh_slot_chip = self._active[attacking.name].get(Position.FLY_HALF)
            near_wing_position_chip = {Side.LEFT: Position.LEFT_WING, Side.RIGHT: Position.RIGHT_WING}[self._side]
            near_wing_slot_chip = self._active[attacking.name].get(near_wing_position_chip)
            if fh_slot_chip is not None and near_wing_slot_chip is not None:
                chip_flyhalf = fh_slot_chip.player
                chip_wing = near_wing_slot_chip.player
                kick_skill = (chip_flyhalf.attributes.kicking_game + chip_flyhalf.attributes.game_intelligence) / 2
                chase_skill = (chip_wing.attributes.pace + chip_wing.attributes.footwork) / 2
                combined_skill = (kick_skill + chase_skill) / 2
                blitz_counter_bonus = 1.0 + blitz_level * 0.6
                p_chip = (
                    self._clamp((combined_skill - 64) / 360, 0.0, 0.035)
                    * individual_break_factor * blitz_counter_bonus
                    * self._kick_style_boost(attacking, "chip")
                )

        handling_edge = (handling_rating - 60) / 100
        p_error = self._clamp(0.16 - handling_edge * 0.10, 0.04, 0.35)

        # Wet weather: a slick ball genuinely makes handling errors more
        # common and tries harder to finish - real rugby's most obvious
        # weather effect. Small, flat adjustments to the two probabilities
        # most directly tied to handling a wet ball.
        if self.weather == "wet":
            p_error = self._clamp(p_error + 0.05, 0.04, 0.45)
            p_try = self._clamp(p_try - 0.02, 0.005, 0.45)

        roll = self.rng.random()
        cumulative = 0.0

        def take(p):
            nonlocal cumulative
            cumulative += p
            return roll < cumulative

        if take(p_try):
            self._score_try(attacking, minute, result)
            return "try"
        if take(p_snipe):
            self._score_try(attacking, minute, result, forced_scorer=snipe_scrum_half, snipe=True)
            return "try"
        if take(p_wing_break):
            self._score_try(
                attacking, minute, result, forced_scorer=wing_breaker,
                individual_flavor="steps the last defender and goes over in the corner - a brilliant individual finish.",
            )
            return "try"
        if take(p_cross_field):
            self._score_try(
                attacking, minute, result, forced_scorer=cross_field_wing,
                individual_flavor=(
                    f"gathers a raking cross-field kick from {cross_field_flyhalf.name} "
                    "and dives in at the corner."
                ),
            )
            return "try"
        if take(p_grubber):
            self._score_try(
                attacking, minute, result, forced_scorer=grubber_wing,
                individual_flavor=(
                    f"{grubber_scrum_half.name} grubbers it through the defensive line and "
                    f"{grubber_wing.name} wins the race to touch down."
                ),
            )
            return "try"
        if take(p_chip):
            self._score_try(
                attacking, minute, result, forced_scorer=chip_wing,
                individual_flavor=(
                    f"{chip_flyhalf.name} chips over the onrushing defence and {chip_wing.name} "
                    "regathers in space to score."
                ),
            )
            return "try"
        if take(p_drop_goal):
            stats_a.drop_goals += 1
            self._credit(attacking, dg_kicker, drop_goals=1)
            result.events.append(self._event(
                minute, attacking,
                f"DROP GOAL! {dg_kicker.name} ({attacking.name}) drops a goal.",
                result, add_score=(attacking, 3),
            ))
            return "drop_goal"
        if take(p_pen_conceded_by_def):
            # Referee system, part 1 (match-engine-depth Phase 13): named,
            # distinct infringement reasons instead of one generic
            # "at the breakdown" text for every general-play penalty -
            # picked from WHERE the already-rolled `roll` landed within
            # this outcome's own probability slice (no new RNG call, a
            # free byproduct of the existing cumulative-roll menu).
            slice_position = (roll - (cumulative - p_pen_conceded_by_def)) / p_pen_conceded_by_def
            via = "offside" if slice_position < 0.5 else "not_releasing"
            # Referee system, part 2: advantage. The referee doesn't blow
            # immediately - if the attack was ALREADY in a position to
            # score anyway (this phase's own zone-gated `p_try`, rolled
            # fresh), advantage is played and the try stands instead of
            # the penalty - a real, named rugby concept, not just
            # commentary flavor: it genuinely changes which outcome this
            # phase resolves to.
            if self.rng.random() < p_try:
                self._score_try(
                    attacking, minute, result,
                    individual_flavor="plays advantage and goes over - no need to bring it back for the penalty.",
                )
                return "try"
            self._score_penalty_chance(attacking, defending, minute, result, via=via)
            return "penalty"
        if take(p_breakdown_turnover):
            result.stats[defending.name].turnovers_won += 1
            result.stats[attacking.name].turnovers_conceded += 1
            result.stats[attacking.name].rucks_lost += 1
            if jackal_flanker is not None:
                self._apply_phase_involvement_stamina(jackal_flanker)
                self._credit(defending, jackal_flanker, turnovers_won=1)
                jackal_text = f"{jackal_flanker.name} jackals over the ball"
            else:
                jackal_text = f"{defending.name} jackal over the ball"
            result.events.append(self._event(
                minute, defending,
                f"{jackal_text} - turnover won at the breakdown against {attacking.name}.",
                result,
            ))
            self._credit_defensive_phase_win(defending, missed=True)
            return "turnover"
        if take(p_pen_conceded_by_atk):
            slice_position = (roll - (cumulative - p_pen_conceded_by_atk)) / p_pen_conceded_by_atk
            via = "offside" if slice_position < 0.5 else "not_releasing"
            self._score_penalty_chance(defending, attacking, minute, result, via=via)
            return "penalty"
        if take(p_error):
            # Referee system, part 3: a handling error isn't always the
            # same infringement - a knock-on (dropped forward off the
            # hands/arms, the common case) and a forward pass (thrown
            # forward, genuinely different) are both real, named law
            # breaches with the same practical result (scrum to the
            # defense) - picked the same free, no-extra-roll way as the
            # penalty reasons above.
            slice_position = (roll - (cumulative - p_error)) / p_error
            error_kind = "knock-on" if slice_position < 0.7 else "forward pass"
            stats_a.handling_errors += 1
            result.events.append(self._event(
                minute, attacking,
                f"{attacking.name} lose the ball - {error_kind}, scrum to {defending.name}.",
                result,
            ))
            result.stats[defending.name].turnovers_won += 1
            stats_a.turnovers_conceded += 1
            return "error"

        # Kicking system detail, part 2 (match-engine-depth Phase 11): a
        # territorial box kick, a real tactical choice distinct from
        # carrying it up - only available deep/midfield (not yet close
        # enough to carry for the line), driven by the SCRUM-HALF/FLY-HALF's
        # own `kicking_game` (not a team-wide average). A real trade,
        # possession for territory - it ends this team's drive outright
        # (a good box kick is deliberately given up to be chased/
        # contested), with zone advancing one extra step on a clean kick,
        # or a charge-down turnover if the defending fullback reads it
        # well. Checked AFTER the main outcome menu (only reached once the
        # phase would otherwise just "continue" as a carry) - a separate
        # decision tier, not competing with try/penalty/turnover odds.
        if zone_rel in ("own_tryline", "own_22", "midfield"):
            sh_slot_kick = self._active[attacking.name].get(Position.SCRUM_HALF)
            fh_slot_kick = self._active[attacking.name].get(Position.FLY_HALF)
            if sh_slot_kick is not None and fh_slot_kick is not None:
                box_kicker = (
                    fh_slot_kick.player if fh_slot_kick.player.attributes.kicking_game >= sh_slot_kick.player.attributes.kicking_game
                    else sh_slot_kick.player
                )
                kick_skill = (sh_slot_kick.player.attributes.kicking_game + fh_slot_kick.player.attributes.kicking_game) / 2
                # Tactics/strategy system (match-engine-depth Phase 15): a
                # team chasing the game (`_score_pressure` > 0) is LESS
                # willing to give up the ball on a territorial kick (real
                # "backs to the wall" rugby - keep it and attack); a team
                # closing out a lead is MORE willing (control territory,
                # don't gift a turnover chance). Facing a blitz-leaning
                # defence also raises this - the real counter to a fast
                # rush line is kicking in behind it, not carrying into it.
                # Player-role/tactic link, strengthened: a team's real
                # `kick_tendency` (attribute-derived, or a manager's own
                # "kick_heavy"/"ball_in_hand" choice - see
                # `TACTIC_CHOICES`) previously only nudged `_advance_zone`'s
                # abstract territory roll; it now ALSO raises or lowers
                # this specific scrum-half/fly-half decision's own odds -
                # so picking "kick_heavy" genuinely means more real box
                # kicks (and the matching `kicks_attempted` stat credit to
                # those two named players), not just a faster zone climb.
                kick_tendency_factor = 1.0 + max(0.0, self._kick_tendency(attacking)) * 0.5
                score_pressure = self._score_pressure(attacking, minute, result)
                pressure_factor = 1.0 - score_pressure * 0.35
                blitz_counter_bonus = 1.0 + max(0.0, self._defensive_style(defending)) * 0.4
                p_box_kick = self._clamp((kick_skill - 55) / 250, 0.0, 0.30) * pressure_factor * blitz_counter_bonus * kick_tendency_factor
                p_box_kick = self._clamp(p_box_kick, 0.0, 0.40) * self._kick_style_boost(attacking, "box_kick")
                if self.rng.random() < p_box_kick:
                    stats_a.kicks_attempted += 1
                    defender_slot = self._active[defending.name].get(Position.FULLBACK)
                    catcher_skill = defender_slot.player.attributes.aerial if defender_slot else 50.0
                    p_charge_down = self._clamp((catcher_skill - kick_skill) / 400 + 0.03, 0.01, 0.12)
                    if self.rng.random() < p_charge_down:
                        result.stats[defending.name].turnovers_won += 1
                        stats_a.turnovers_conceded += 1
                        result.events.append(self._event(
                            minute, attacking,
                            f"{box_kicker.name}'s box kick is charged down - loose ball recovered by {defending.name}.",
                            result,
                        ))
                        return "charge_down"
                    toward_away = attacking is self.home
                    step = 1 if toward_away else -1
                    new_index = self._clamp(self._ZONES.index(self._zone) + step, 0, len(self._ZONES) - 1)
                    self._zone = self._ZONES[int(new_index)]
                    stats_a.kicks_successful += 1
                    stats_a.kicking_metres += KICKING_METRES_PER_ZONE_STEP
                    result.events.append(self._event(
                        minute, attacking,
                        f"{box_kicker.name} pins {defending.name} back with a smart territorial kick.",
                        result,
                    ))
                    return "box_kick"

        # Clean continuation - no commentary line of its own (reserved for
        # the drive's eventual decisive outcome, same "one line per
        # meaningful event" convention the event log already followed
        # before phases existed) - but a real, phase-by-phase stats
        # byproduct: the attack carried it up, the defense made the
        # tackle, the attack won the ruck and keeps the ball.
        self._credit_phase_continue(attacking, defending, result, edge)
        return "continue"

    def _apply_phase_involvement_stamina(self, player: Player) -> None:
        """A small EXTRA stamina cost for one player's direct involvement
        in a single phase (a carry or a tackle attempt) - see
        `PHASE_INVOLVEMENT_STAMINA_COST`'s own comment for why this is
        separate from, and smaller than, the existing once-per-drive
        team-wide decay (`_decay_stamina`), not a replacement for it."""
        key = id(player)
        current = self._stamina.get(key, 100.0)
        self._stamina[key] = max(STAMINA_FLOOR, current - PHASE_INVOLVEMENT_STAMINA_COST)

    def _credit_phase_continue(self, attacking: Team, defending: Team, result: MatchResult, edge: float) -> None:
        """Stats credited on a "continue" phase only - see `TeamMatchStats`'
        own comment on these fields for why nothing is credited on a
        scoring/turnover/error phase instead (those already have their own,
        longer-standing stat fields)."""
        stats_a = result.stats[attacking.name]
        stats_d = result.stats[defending.name]
        carrier = self._pick_try_scorer(attacking)
        metres = round(self._clamp(4 + edge * 8, 1, 15))
        stats_a.carries += 1
        stats_a.metres_gained += metres
        stats_a.rucks_won += 1
        self._credit(attacking, carrier, carries=1, metres_gained=metres)
        self._apply_phase_involvement_stamina(carrier)

        # A carry that gains real, meaningful ground - DEFENDERS_BEATEN_METRES_THRESHOLD
        # (8 units) or more - counts as beating a defender, the same
        # documented-threshold convention this file already uses elsewhere
        # (e.g. the concussion severity re-roll) rather than a separate
        # invented roll.
        if metres >= DEFENDERS_BEATEN_METRES_THRESHOLD:
            stats_a.defenders_beaten += 1
            self._credit(attacking, carrier, defenders_beaten=1)

        stats_d.tackles_made += 1
        tackler = self._pick_defender(defending)
        if tackler is not None:
            self._credit(defending, tackler, tackles_made=1)
            self._apply_phase_involvement_stamina(tackler)

    def _credit_defensive_phase_win(self, defending: Team, missed: bool) -> None:
        """A broken-tackle/jackal-won-it phase (see the breakdown-turnover
        branch above): credits the tackle attempt as missed for a defender
        picked the same uniform way `_issue_card` picks a carded player -
        this model has no real per-defender skill differentiation to
        weight the pick by yet (see `MATCH_ENGINE_MODEL.md`'s own "Known
        limitations" on the card pick for the same reason)."""
        result = self.result
        if result is None:
            return
        stats_d = result.stats[defending.name]
        if missed:
            stats_d.tackles_missed += 1
        tackler = self._pick_defender(defending)
        if tackler is not None and missed:
            self._credit(defending, tackler, tackles_missed=1)
            self._apply_phase_involvement_stamina(tackler)

    def _pick_defender(self, team: Team) -> Optional[Player]:
        slots = list(self._active[team.name].values())
        return self.rng.choice(slots).player if slots else None

    _SCRUM_POSITIONS = (Position.LOOSEHEAD_PROP, Position.HOOKER, Position.TIGHTHEAD_PROP)

    def _weakest_scrum_player(self, team: Team) -> Optional[Player]:
        """The front-row player with the lowest `scrummaging` attribute -
        who "got outscrummaged" when a scrum is lost against the head (see
        `_resolve_scrum`). Same single-attribute-min pick style as
        `_best_kicker`'s max pick."""
        slots = [s for s in self._active[team.name].values() if s.position in self._SCRUM_POSITIONS]
        if not slots:
            return None
        return min(slots, key=lambda s: s.player.attributes.scrummaging).player

    def _strongest_scrum_player(self, team: Team) -> Optional[Player]:
        """The front-row player with the highest `scrummaging` attribute -
        who actually won a scrum against the head."""
        slots = [s for s in self._active[team.name].values() if s.position in self._SCRUM_POSITIONS]
        if not slots:
            return None
        return max(slots, key=lambda s: s.player.attributes.scrummaging).player

    def _best_lineout_jumper(self, team: Team) -> Optional[Player]:
        """The player with the highest `lineout_jumping` attribute among
        the real lineout-contesting positions (`CATEGORY_POSITION_GROUPS
        ["lineout"]` - hooker, locks, back row), for the lineout jumping
        contest in `_resolve_lineout`. Same `_best_kicker`-style single-
        attribute-max pick, just scoped to the positions that actually
        contest a lineout."""
        group = CATEGORY_POSITION_GROUPS.get("lineout")
        slots = [s for s in self._active[team.name].values() if group is None or s.position in group]
        if not slots:
            return None
        return max(slots, key=lambda s: s.player.attributes.lineout_jumping).player

    def _resolve_scrum(
        self, attacking: Team, defending: Team, scrum_atk: float, scrum_def: float, minute: int, result: MatchResult,
    ) -> str:
        """Resolves a drive whose possession-origin roll came up `"scrum"`
        (see `DRIVE_ORIGIN_SCRUM_PROB`) - reuses the EXISTING, already
        individually-scoped `scrum_atk`/`scrum_def` sub-ratings
        (`_resolve_drive` already computed them, no new attribute reads)
        for the penalty-conceded probability (same formula as the old
        unconditional-every-drive version), plus a new, small chance of a
        clean scrum turnover "against the head." Returns `"continue"` if
        the attacking team keeps the ball (the normal, common case - the
        phase loop runs as usual), or a short outcome tag otherwise."""
        scrum_edge = (scrum_atk - scrum_def) / 100
        p_scrum_penalty = self._clamp(0.04 + scrum_edge * 0.05, 0.0, 0.12)
        p_scrum_turnover = self._clamp(0.01 - scrum_edge * 0.02, 0.002, 0.05)

        # Credited once per scrum-origin drive regardless of outcome -
        # this is the attacking team's OWN put-in, so `scrums_contested`
        # (alongside `scrums_won`) is what makes a real success rate
        # possible: `scrums_won / scrums_contested`.
        result.stats[attacking.name].scrums_contested += 1

        roll = self.rng.random()
        if roll < p_scrum_penalty:
            self._score_penalty_chance(attacking, defending, minute, result, via="scrum")
            return "penalty"
        if roll < p_scrum_penalty + p_scrum_turnover:
            result.stats[defending.name].scrums_won += 1
            result.stats[defending.name].turnovers_won += 1
            result.stats[attacking.name].turnovers_conceded += 1
            loser = self._weakest_scrum_player(attacking)
            winner = self._strongest_scrum_player(defending)
            loser_text = f" - {loser.name} outscrummaged" if loser else ""
            winner_text = f" by {winner.name}" if winner else ""
            result.events.append(self._event(
                minute, defending,
                f"{defending.name} win the scrum against the head{winner_text}{loser_text} ({attacking.name}).",
                result,
            ))
            return "turnover"

        result.stats[attacking.name].scrums_won += 1

        # Set-piece sub-scenario (match-engine-depth Phase 10): a real,
        # recognizable rugby pattern - the number 8 picks up from the base
        # of a dominant scrum and drives over himself - distinct from the
        # phase loop's own generic try chance, only reachable right off a
        # clean scrum win close to the line, and driven by THIS specific
        # player's own `strength`/`game_intelligence`, not a team average.
        zone_rel = self._zone_relative_to(attacking)
        if zone_rel in ("attacking_tryline", "attacking_22"):
            no8_slot = self._active[attacking.name].get(Position.NUMBER_8)
            if no8_slot is not None:
                no8 = no8_slot.player
                skill = (no8.attributes.strength + no8.attributes.game_intelligence) / 2
                # A forward-heavy team's own tactical identity (match-
                # engine-depth Phase 15) leans on exactly this pattern more
                # - real rugby's "go through the pack" game plan.
                forward_heavy_bonus = 1.0 + max(0.0, self._attack_shape_tendency(attacking)) * 0.5
                p_pick_and_go = self._clamp((skill - 65) / 300, 0.0, 0.06) * forward_heavy_bonus
                if self.rng.random() < p_pick_and_go:
                    self._score_try(
                        attacking, minute, result, forced_scorer=no8,
                        individual_flavor="picks up from the base and drives over himself - a real number 8's try.",
                    )
                    result.stats[attacking.name].red_zone_possessions += 1
                    result.stats[attacking.name].red_zone_tries += 1
                    return "try"

        return "continue"

    def _resolve_lineout(self, attacking: Team, defending: Team, minute: int, result: MatchResult) -> str:
        """Resolves a drive whose possession-origin roll came up
        `"lineout"` (see `DRIVE_ORIGIN_LINEOUT_PROB`) - unlike the old
        team-sub-rating-average version, this genuinely picks two named
        individuals per side: the attacking HOOKER specifically (the real
        thrower - `lineout_throwing`) plus each side's best jumper
        (`_best_lineout_jumper`, `lineout_jumping`), not a whole-team
        average. Returns `"continue"` if the attack secures clean ball."""
        thrower_slot = self._active[attacking.name].get(Position.HOOKER)
        thrower_throwing = thrower_slot.player.attributes.lineout_throwing if thrower_slot else 50.0
        attacking_jumper = self._best_lineout_jumper(attacking)
        defending_jumper = self._best_lineout_jumper(defending)
        attacking_jumping = attacking_jumper.attributes.lineout_jumping if attacking_jumper else 50.0
        defending_jumping = defending_jumper.attributes.lineout_jumping if defending_jumper else 50.0

        atk_card_pen = self._active_card_penalty(attacking)
        def_card_pen = self._active_card_penalty(defending)
        lineout_edge = (
            ((thrower_throwing + attacking_jumping) / 2) * atk_card_pen
            - defending_jumping * def_card_pen
        ) / 100
        p_lineout_turnover = self._clamp(0.05 - lineout_edge * 0.06, 0.01, 0.14)

        # Same "contested regardless of outcome" convention as the scrum's
        # own `scrums_contested` - makes a real `lineouts_won/
        # lineouts_contested` success rate possible.
        result.stats[attacking.name].lineouts_contested += 1

        if self.rng.random() < p_lineout_turnover:
            result.stats[defending.name].lineouts_won += 1
            result.stats[defending.name].turnovers_won += 1
            result.stats[attacking.name].turnovers_conceded += 1
            jumper_text = f" - {defending_jumper.name} climbs above everyone" if defending_jumper else ""
            result.events.append(self._event(
                minute, defending,
                f"{defending.name} win the lineout{jumper_text} - overthrow/steal from {attacking.name}.",
                result,
            ))
            return "turnover"

        result.stats[attacking.name].lineouts_won += 1

        # Set-piece sub-scenario (match-engine-depth Phase 10, same idea
        # as the scrum's own pick-and-go): a catch-and-drive maul off a
        # clean lineout win, close to the line - the HOOKER peeling off
        # the back of the drive to finish it (a real, recognizable rugby
        # pattern), driven by THIS specific player's own `strength`/
        # `game_intelligence`, not a team average.
        zone_rel = self._zone_relative_to(attacking)
        if zone_rel in ("attacking_tryline", "attacking_22") and thrower_slot is not None:
            hooker = thrower_slot.player
            skill = (hooker.attributes.strength + hooker.attributes.game_intelligence) / 2
            forward_heavy_bonus = 1.0 + max(0.0, self._attack_shape_tendency(attacking)) * 0.5
            p_maul_try = self._clamp((skill - 65) / 300, 0.0, 0.06) * forward_heavy_bonus
            if self.rng.random() < p_maul_try:
                self._score_try(
                    attacking, minute, result, forced_scorer=hooker,
                    individual_flavor="peels off the back of a driving maul to finish it - a real catch-and-drive try.",
                )
                result.stats[attacking.name].red_zone_possessions += 1
                result.stats[attacking.name].red_zone_tries += 1
                return "try"

        return "continue"

    def _issue_card(self, team: Team, minute: int, result: MatchResult) -> Tuple[bool, Optional[Player]]:
        # A player already sent off this match can't be carded again - they're
        # off the field, not merely "a player down" (same reasoning as an
        # injured-off player not being eligible for the next injury roll).
        slots = [
            (pos, s) for pos, s in self._active[team.name].items()
            if id(s.player) not in self._sent_off[team.name]
        ]
        carded_position, carded_player = (None, None)
        if slots:
            carded_position, carded_slot = self.rng.choice(slots)
            carded_player = carded_slot.player

        is_red = self.rng.random() < 0.12
        escalated = False
        if (
            not is_red and carded_player is not None
            and id(carded_player) in self._yellow_history[team.name]
        ):
            # Law 19.2: a second yellow card for the SAME player in the SAME
            # match is a send-off - treated as a red for the rest of this
            # match (not the newer, still-trialled "20-minute red" variant -
            # see README). This project doesn't model the sin-bin clock at
            # all finely enough to distinguish "still in the bin" from
            # "already back on" when the second yellow is shown, so this
            # escalates regardless of whether the first yellow has expired -
            # which matches the real law: it's about the match, not the bin.
            is_red = True
            escalated = True

        duration = MATCH_MINUTES if is_red else 10
        self._carded[team.name].append(minute + duration)

        if is_red:
            result.stats[team.name].red_cards += 1
            if carded_player is not None:
                result.carded_players.append((team.name, carded_player, "red"))
                self._sent_off[team.name].add(id(carded_player))
                if carded_position is not None:
                    self._sent_off_positions[team.name].append(carded_position)
                result.card_details.append({
                    "minute": minute, "team": team.name, "player": carded_player.name,
                    "card_type": "red", "escalated_second_yellow": escalated,
                })
        else:
            result.stats[team.name].yellow_cards += 1
            if carded_player is not None:
                result.carded_players.append((team.name, carded_player, "yellow"))
                self._yellow_history[team.name].add(id(carded_player))
                result.card_details.append({
                    "minute": minute, "team": team.name, "player": carded_player.name,
                    "card_type": "yellow", "escalated_second_yellow": False,
                })
        return is_red, carded_player

    def _best_kicker(self, team: Team):
        best_slot = max(
            self._active[team.name].values(),
            key=lambda slot: slot.player.attributes.goal_kicking,
        )
        return best_slot.player

    def _kick_success_probability(self, goal_kicking: float) -> float:
        """Converts a goal-kicking attribute (1-100) into a single
        place-kick's success probability, for the kicking competition -
        same house style/convention as this module's other
        attribute-to-probability conversions (e.g. `_score_try`'s
        conversion/penalty-goal formulas just below: a baseline around an
        even-money kick, shifted by the rating's distance from the 50
        midpoint, clamped to a sane range)."""
        return self._clamp(0.5 + (goal_kicking - 50) / 150, 0.15, 0.95)

    def _run_kicking_competition(self) -> None:
        """Resolves a still-tied knockout match instantly (not drive-by-
        drive - there's no attack/defense contest left, just goal-kicking):
        5 kicks per side from the 22m line, alternating, then sudden-death
        kicks if still level after 5 (real World Rugby knockout-tournament
        tiebreak shape). A coin flip decides only who kicks first - the one
        real randomness the rule actually specifies; which two kickers take
        the kicks is each side's own best current goal-kicker, not random.
        Sets `result.shootout_winner`/`result.shootout_detail` - NEVER
        touches `score_home`/`score_away` (see `MatchResult.shootout_winner`'s
        field comment: a shootout-decided knockout match is still officially
        recorded with its tied scoreline)."""
        result = self.result
        assert result is not None

        home_kicker = self._best_kicker(self.home)
        away_kicker = self._best_kicker(self.away)
        probs = {
            self.home.name: self._kick_success_probability(home_kicker.attributes.goal_kicking),
            self.away.name: self._kick_success_probability(away_kicker.attributes.goal_kicking),
        }

        home_first = self.rng.random() < 0.5
        order = [self.home, self.away] if home_first else [self.away, self.home]

        taken = {self.home.name: 0, self.away.name: 0}
        made = {self.home.name: 0, self.away.name: 0}

        def _take_kick(team: Team) -> None:
            taken[team.name] += 1
            if self.rng.random() < probs[team.name]:
                made[team.name] += 1

        for _ in range(KICK_COMPETITION_ROUNDS):
            for team in order:
                _take_kick(team)

        extra_rounds = 0
        while made[self.home.name] == made[self.away.name] and extra_rounds < KICK_COMPETITION_SAFETY_CAP:
            for team in order:
                _take_kick(team)
            extra_rounds += 1

        if made[self.home.name] == made[self.away.name]:
            # Termination-guarantee fallback only - astronomically unlikely
            # in practice (both kickers landing in exact lockstep for
            # KICK_COMPETITION_SAFETY_CAP extra rounds running); one more
            # coin flip rather than looping forever.
            winner_team = self.home if self.rng.random() < 0.5 else self.away
        else:
            winner_team = self.home if made[self.home.name] > made[self.away.name] else self.away

        result.shootout_winner = winner_team.name
        result.shootout_detail = {
            "home": {"taken": taken[self.home.name], "made": made[self.home.name]},
            "away": {"taken": taken[self.away.name], "made": made[self.away.name]},
            "first_kicker": "home" if home_first else "away",
        }
        result.events.append(CommentaryEvent(
            minute=self._minute, team=winner_team.name,
            text=(
                f"Kicking competition: {winner_team.name} win it "
                f"{made[self.home.name]}-{made[self.away.name]}."
            ),
            score_home=result.score_home, score_away=result.score_away,
        ))

    def _score_try(
        self, team: Team, minute: int, result: MatchResult,
        forced_scorer: Optional[Player] = None, snipe: bool = False, individual_flavor: Optional[str] = None,
    ):
        """`forced_scorer`/`individual_flavor` (`snipe=True` is a thin,
        backward-compatible alias for the scrum-half's own flavor text):
        used by this engine's player-specific decision outcomes (see
        `_resolve_phase`'s `p_snipe` branch, and any later one following
        the same pattern) - a real, individually-attributed try a specific
        standout player can create, not just a team-wide average pick.
        Default behavior (no args) is unchanged from before any of these
        existed: `_pick_try_scorer`'s usual weighted pick, generic
        commentary."""
        stats = result.stats[team.name]
        stats.tries += 1
        scorer = forced_scorer if forced_scorer is not None else self._pick_try_scorer(team)
        self._credit(team, scorer, tries=1)
        if snipe:
            text = f"TRY! {scorer.name} ({team.name}) sniffs out a gap and snipes over from close range - a sharp individual read, not a team move."
        elif individual_flavor is not None:
            text = f"TRY! {scorer.name} ({team.name}) {individual_flavor}"
        else:
            # Honest flavor only - `self._side` is read here for commentary
            # text, it never changes who actually scored (that's already
            # decided above, by `_pick_try_scorer`); see `Side`'s own
            # docstring.
            side_flavor = {Side.LEFT: " down the left wing", Side.RIGHT: " down the right wing"}.get(self._side, "")
            text = f"TRY! {scorer.name} ({team.name}) crosses the whitewash{side_flavor} after a well-worked move."
        result.events.append(self._event(minute, team, text, result, add_score=(team, 5)))

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
        # Referee system (match-engine-depth Phase 13): named, distinct
        # infringement reasons - not every general-play penalty is the
        # same vague "at the breakdown" foul.
        reason = {
            "scrum": "at the scrum",
            "offside": "for offside",
            "not_releasing": "for not releasing the ball",
        }.get(via, "at the breakdown")
        result.events.append(self._event(minute, conceded_by, f"Penalty against {conceded_by.name} {reason}.", result))

        zone_rel = self._zone_relative_to(attacking)
        # Manager-controls pass: a decision-team's own penalty is a real
        # in-match choice (kick for posts / kick to touch / a quick tap),
        # not an auto-pick - pause resolution right here and let the
        # caller (`webapp.py`'s live-match flow) show the choice, instead
        # of rolling `go_for_posts` below. The penalty itself (and its
        # "Penalty against..." event, above) already happened - only what
        # to DO with it is deferred. See `resolve_pending_decision`.
        if attacking.name in self._decision_teams:
            self._pending_penalty = {
                "team": attacking.name, "minute": minute,
                "zone": zone_rel, "can_go_for_posts": zone_rel not in ("own_22", "own_tryline"),
            }
            return
        self._apply_penalty_decision(attacking, minute, result, zone_rel, choice=None)

    def _apply_penalty_decision(self, attacking: Team, minute: int, result: MatchResult, zone_rel: str, choice: Optional[str]):
        """Resolves what happens with an already-awarded penalty - either
        the AI's own auto-pick (`choice=None`, the exact pre-existing
        behavior) or a decision-team manager's explicit choice
        (`"posts"`/`"touch"`/`"quick_tap"`, see `TACTIC_CHOICES`'s sibling
        constant `PENALTY_CHOICES` and `resolve_pending_decision`)."""
        kicker = self._best_kicker(attacking)
        if choice == "quick_tap":
            result.events.append(self._event(
                minute, attacking,
                f"{attacking.name} take a quick tap penalty and keep the ball alive instead of kicking.", result,
            ))
            return
        # Zone-gated now (closes `MATCH_ENGINE_MODEL.md` item 3's previously
        # open "deep territory heuristics omitted for simplicity" gap, same
        # zone concept Phase 1 added for try probability): pinned in their
        # own 22 or own tryline, a kick is too far out to realistically go
        # for posts at all, whatever the kicker's skill - real rugby
        # essentially never attempts this range. In the defending team's
        # 22/tryline zone a side almost always takes the points; midfield
        # keeps the original baseline. A decision-team manager's explicit
        # "posts"/"touch" choice overrides the roll entirely (still subject
        # to the same own-22/own-tryline realism gate - "posts" isn't
        # offered as a choice there at all, see `can_go_for_posts` above).
        if zone_rel in ("own_22", "own_tryline"):
            go_for_posts = False
        elif choice == "posts":
            go_for_posts = True
        elif choice == "touch":
            go_for_posts = False
        else:
            go_for_posts = self.rng.random() < ZONE_GO_FOR_POSTS_BASE[zone_rel] or kicker.attributes.goal_kicking > 70
        if not go_for_posts:
            result.events.append(self._event(minute, attacking, f"{attacking.name} kick to the corner instead of taking the points.", result))
            return

        pen_prob = self._clamp(
            0.55 + kicker.attributes.goal_kicking / 200 + ZONE_PEN_PROB_ADJUST[zone_rel], 0.15, 0.97
        )
        stats_atk = result.stats[attacking.name]
        if self.rng.random() < pen_prob:
            stats_atk.penalty_goals += 1
            self._credit(attacking, kicker, penalty_goals=1)
            result.events.append(self._event(minute, attacking, f"{kicker.name} kicks the penalty.", result, add_score=(attacking, 3)))
        else:
            result.events.append(self._event(minute, attacking, f"{kicker.name}'s penalty attempt is off target.", result))

    def resolve_pending_decision(self, choice: str) -> None:
        """Applies a decision-team manager's choice for the currently
        pending penalty (`"posts"`/`"touch"`/`"quick_tap"` - see
        `_pending_penalty`/`_apply_penalty_decision`), then finishes this
        drive's remaining bookkeeping (injury/tactical-sub roll, the
        knockout-tiebreak check) exactly as an auto-decided drive already
        would have - deferred, not skipped, by `_advance_one_drive` while
        the decision was pending. No-op if nothing is actually pending (a
        defensive guard, not an expected call pattern)."""
        if self._pending_penalty is None or self.result is None:
            return
        pending = self._pending_penalty
        self._pending_penalty = None
        attacking = self.home if pending["team"] == self.home.name else self.away
        self._apply_penalty_decision(attacking, pending["minute"], self.result, pending["zone"], choice)
        self._maybe_personnel_change(self._minute, self.result)
        self._update_knockout_stage()

    def _event(self, minute, team, text, result, add_score=None) -> CommentaryEvent:
        if add_score:
            scoring_team, pts = add_score
            if scoring_team is self.home:
                result.score_home += pts
            else:
                result.score_away += pts
        return CommentaryEvent(
            minute=minute, team=team.name, text=text,
            score_home=result.score_home, score_away=result.score_away,
            zone=self._zone.value, side=self._side.value,
        )

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))
