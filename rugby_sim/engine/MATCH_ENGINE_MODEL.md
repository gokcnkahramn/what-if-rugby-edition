# How `MatchEngine` actually decides a match

This is the companion reference to `rugby_sim/data/sources/ATTRIBUTE_MAPPING.md`,
but for the other end of the pipeline: not "where does a 1-100 attribute come
from" but "once a lineup has those attributes, how does the engine turn them
into a scoreline." It was written in response to an external audit question:
*do these mechanics interact logically, or are match outcomes primarily
generated through simplified random calculations?* The honest answer is
"both, in a specific and inspectable way" - this document says exactly which
parts are which, attribute-by-attribute and outcome-by-outcome, so nobody has
to reverse-engineer `match_engine.py` from scratch to find out.

## What kind of simulation this is

**`MatchEngine` is a drive-by-drive, attribute-weighted-dice-roll
abstraction - but, since match-engine-depth Phase 4, each drive is now a
bounded sequence of explicit phases (one ruck/tackle/carry exchange each),
not one single roll for the whole possession.** It is still NOT a full
physical simulation with continuous player positions, individual ball-
carrier-vs-defender contact resolution, or a tracked ball/field beyond the
5-zone/3-side model (see "Field position" below). What changed: a drive
used to be decided by **one single weighted random roll** regardless of how
long a real possession like that would take; now `_resolve_drive` resolves
a few once-per-drive events (whether a card is shown; then, since
match-engine-depth Phase 5, an explicit "possession origin" roll decides
whether this drive is really a scrum, a lineout, or open play - see "Set
piece" below for why this replaced the old "every drive gets a scrum-
penalty/lineout-turnover check" behavior), then hands off to
`_resolve_phase`, called in a loop up to `MAX_PHASES_PER_DRIVE` (6) times,
each one its own independent weighted roll across the SAME outcome menu as
before (try / drop goal / penalty conceded / breakdown turnover / handling
error / continue). A phase that "continues" doesn't end the drive - the
loop keeps going, and the zone/side position keeps advancing one step per
phase (not once for the whole drive, as before) - so a longer, multi-phase
drive now genuinely covers more ground than a one-phase drive, and a try's
probability on the very first phase is deliberately damped
(`PHASE_TRY_RAMP`, reaching full strength by phase 3) UNLESS the zone is
already right on the defending team's line - letting a quick, high-"edge"
attack still score in very few phases (a real "quick pass, 1-on-1 overlap"
try) while a grinding, low-edge attack takes longer, which the old single-
roll model had no way to express at all. Each "continue" phase also credits
real carry/metres-gained/tackle/ruck-won stats (see "New per-phase stats"
below) - a genuine simulated byproduct, not separately invented numbers.

The module's own docstring used to call this "detailed phase-by-phase,"
which WAS a misleading description before this change (there was exactly
one resolution point per drive) - it's now an accurate one.

What IS genuine and attribute-driven: which team attacks on a given drive,
and the relative odds of try / penalty / turnover / card for each phase, are
all real functions of the two lineups' actual sub-ratings (which are in turn
built from real player attributes, fit-at-position, stamina, and card
penalties). Swap in a team of locks at scrum-half and the engine's
probabilities really do move. What is NOT genuine: there's still no
resolution of *why* a phase went the way it did beyond "the dice roll landed
in that slice" - no explicit breakout, no last-tackle-buster, no which-
defender-missed detail (the new per-phase tackle/carry stats name a
carrier/tackler for the stat line, picked by the same weighted-pick/uniform-
pick conventions the try-scorer/card-recipient picks already used - not a
contact-by-contact physical resolution). The commentary text ("crosses the
whitewash after a well-worked move") is flavour text generated after the
outcome is already decided, not a description of a sub-simulation that
produced it; a "continuing" phase deliberately gets NO commentary line of
its own (only the drive's eventual decisive outcome does), so the event log
still reads as one line per meaningful moment, not one line per phase roll.

### New per-phase stats (carries, metres gained, tackles, rucks won)

`TeamMatchStats`/`PlayerMatchStats` gained `carries`, `metres_gained`,
`tackles_made`, `tackles_missed` (plus team-level `rucks_won` - no single
real "who won the ruck" player attribution exists in this model, so that
one stays team-only, same honesty convention as everywhere else). Credited
ONLY on a "continue" phase (`_credit_phase_continue`): the ball-carrier is
picked the same attack-weighted-plus-`Side`-bonus way `_pick_try_scorer`
already picks a try scorer (reused as-is, not reinvented), `metres_gained`
is a direct, documented function of the same attack-vs-tackling `edge`
every other probability in the drive is built from
(`round(clamp(4 + edge*8, 1, 15))`), and the tackling defender is picked
uniformly among the defending team's on-field slots - same convention
`_issue_card` already used for picking a carded player, since this model
has no real per-defender skill differentiation to weight that pick by yet.
A broken-tackle phase (the breakdown-turnover outcome) credits
`tackles_missed` the same way. These are a real, simulated-from-within-the-
model byproduct of the phase loop, not a separately invented "stats layer"
bolted on afterward.

### Set piece (match-engine-depth Phase 5)

Before this pass, EVERY drive ran the same scrum-penalty/lineout-turnover
check, unconditionally - meaning a match's ~32 drives (see "How many
drives" below) were all implicitly treated as a contested set piece, when
a real Test match only has a fraction of that many actual scrums and
lineouts. `_resolve_drive` now rolls an explicit "possession origin" once
per drive (`DRIVE_ORIGIN_SCRUM_PROB = 0.35`, `DRIVE_ORIGIN_LINEOUT_PROB =
0.40`, remainder `"open_play"`) - tuned by running many seeds and counting
realized `scrums_won`/`lineouts_won` per match (landed around ~5 scrums and
~6 lineouts per team on average, verified live). **Honest caveat**: this
engine's drive count (~32/match) is itself lower than a real match's
combined scrum+lineout count (which can be 25-35 on its own), so these
probabilities can't literally reproduce real per-match set-piece counts
one-for-one without crowding out open play entirely - the chosen values
land in a modest, plausible single-digit-to-low-teens range per team
rather than forcing an exact real-world number this model's drive
granularity can't actually support. `"open_play"` skips the set-piece
check entirely and goes straight to the phase loop, unchanged from a
normal drive.

A scrum-origin drive calls `_resolve_scrum`, which reuses the EXISTING
`scrum_atk`/`scrum_def` sub-ratings (already individually scoped to the
front row + locks via `CATEGORY_POSITION_GROUPS` - not a flat whole-squad
average) for the same scrum-penalty probability the old unconditional
version used, plus a new, small chance of a clean turnover "against the
head" (`p = clamp(0.01 - edge*0.02, 0.002, 0.05)`) - naming the SPECIFIC
attacking front-row player with the lowest `scrummaging` attribute
(`_weakest_scrum_player`) and the defending player with the highest
(`_strongest_scrum_player`) in the commentary, not just the team name. A
clean win (the common case) credits `scrums_won` and falls through to the
normal phase loop.

A lineout-origin drive calls `_resolve_lineout`, which - unlike the old
team-sub-rating-average version - picks TWO named individuals per side:
the attacking team's HOOKER specifically (`lineout_throwing`, the real
thrower) plus each side's best jumper (`_best_lineout_jumper`, max
`lineout_jumping` among the real lineout-contesting positions - hooker,
locks, back row). A steal names the specific jumper who won it. A clean
take credits `lineouts_won` and falls through to the phase loop.

### Set-piece sub-scenarios: pick-and-go and the driving maul (match-engine-depth Phase 10)

A clean scrum/lineout win close to the defending team's line (`"attacking_
tryline"`/`"attacking_22"`) is no longer ALWAYS a generic fall-through to
the phase loop - it can now become one of two real, recognizable rugby
patterns, each driven by one specific player's own attributes:
- `_resolve_scrum`'s clean-win branch: the attacking NUMBER 8 can pick up
  from the base and drive over himself - `p = clamp((skill-65)/300, 0.0,
  0.06)`, `skill = (strength + game_intelligence)/2` for that exact
  player.
- `_resolve_lineout`'s clean-take branch: the attacking HOOKER (the same
  one who just threw it in) can peel off the back of a driving maul to
  finish it - same formula, same two attributes, this player instead.
Both reuse `_score_try`'s `forced_scorer`/`individual_flavor` parameters
(no new scoring machinery). Verified live: an elite number 8 (strength/
game_intelligence both 99) scored 9 pick-and-go tries across 60 simulated
matches vs. 0 for an average one; an elite hooker scored 6 driving-maul
tries vs. 0 for an average one. New `tests/test_set_piece_sub_scenarios.py`
(4 tests).

### Player-specific decision behavior (match-engine-depth Phase 6)

An external review's ask: "Dupont and an average scrum-half shouldn't make
the same decisions." Every outcome up to this point is still a TEAM-level
probability (team sub-ratings, not one player's own numbers) with
individual players only picked AFTER a team-level outcome is already
decided (who scored, who tackled). This phase adds the first outcome
that's driven by one specific player's OWN attributes, not a team average,
from the start: `_resolve_phase` computes a small "snipe try" chance
(`p_snipe`) whenever the zone is close to the defending team's line
(`"attacking_tryline"`/`"attacking_22"`), built from the ATTACKING team's
own scrum-half's `pace`/`game_intelligence`
(`p = clamp((skill-60)/400, 0.0, 0.05)`, `skill = (pace +
game_intelligence)/2`) - a sharp, fast 9 sniping over themselves from close
range, not a team-wide swing. Rolled as its own slice in the same
cumulative `take(p)` menu, right after the main try check - if it fires,
`_score_try(..., forced_scorer=scrum_half, snipe=True)` credits that exact
player (not `_pick_try_scorer`'s usual weighted pick) with distinct
commentary ("sniffs out a gap and snipes over... a sharp individual read,
not a team move"). Verified live: an elite scrum-half (pace/
game_intelligence both 99) produced 28 snipe tries across 60 simulated
matches; an average one (both 50) produced 0, with every other attribute
on both squads held identical - a genuinely individual, not team-level,
effect. Deliberately scoped to ONE position/decision for this pass (the
scrum-half's break near the line is a real, recognizable rugby moment,
and the position already has a clean "individual decision-making"
attribute pairing to draw on) - extending this same pattern to other
positions/decisions (a fly-half's individual kicking choice, a back-row's
individual jackal timing, etc.) is a natural later increment, not
attempted here, to keep this pass's surface area small and its effect
independently verifiable.

### Per-phase involvement stamina (match-engine-depth Phase 7)

`_decay_stamina` (see "Stamina/fatigue" below) already runs once per
DRIVE, scaled by `drive_minutes` - but `drive_minutes` is itself an
unrelated random roll (1-4, no attribute input at all), so a drive that
grinds through all `MAX_PHASES_PER_DRIVE` phases (lots of real carries/
tackles/rucks) could cost the exact same team-wide stamina as a drive that
scores clean on phase 1, as long as both happened to roll the same
`drive_minutes`. This adds a small, SEPARATE extra cost
(`PHASE_INVOLVEMENT_STAMINA_COST = 0.4`) on top of that unchanged
team-wide decay: only the specific player actually credited with a carry
or a tackle that phase (`_credit_phase_continue`/
`_credit_defensive_phase_win`, via the new `_apply_phase_involvement_
stamina`) pays it - so a team's go-to ball-carrier/go-to tackler genuinely
tires faster over a match than a teammate who's rarely involved, which the
old once-per-drive-only model had no way to express. Deliberately small
(a single phase's involvement costs far less than a whole drive's
team-wide decay) so it doesn't require re-tuning the existing
`STAMINA_DECAY_PER_MINUTE` calibration. Adds no new RNG consumption (no
extra `rng` calls - purely a deterministic bookkeeping addition), so
unlike every other pass in this arc, this one carries no RNG-shift risk to
existing fixed-seed tests. Verified via a controlled comparison
(`tests/test_phase_involvement_stamina.py`): running the SAME seed/squads
twice, forcing one specific player to receive every single phase's
carry/tackle credit in one run but not the other, shows that player's
final condition is measurably lower in the "forced busy" run - isolating
the mechanism directly, since nothing else differs between the two runs.

### A second player-specific decision behavior: the openside flanker's jackal threat (match-engine-depth Phase 8)

Extends Phase 6's scrum-half snipe-try pattern to a second position.
`p_breakdown_turnover` (computed once per drive, same as before) now gets
a small extra term built from the DEFENDING team's openside flanker's own
`tackle_technique`/`game_intelligence` (not the team-wide `breakdown_def`
average that formula already used) - `jackal_bonus = clamp((fetcher_skill
- 60)/300, 0.0, 0.04)`, added on top of the existing team-wide probability.
A standout individual fetcher should create more breakdown turnovers than
their team's average breakdown rating alone suggests, the same real-world
distinction the scrum-half snipe was about, applied to a second position.
When a breakdown turnover fires, the commentary now names that specific
flanker ("<name> jackals over the ball...") instead of just the team, and
they pay the same `_apply_phase_involvement_stamina` cost the ball-carrier/
tackler already do (a jackal effort is real physical involvement too).
Verified live: an elite fetcher (tackle_technique/game_intelligence both
99) produced 138 jackal turnovers across 60 simulated matches vs. 105 for
an average one (both 50), every other attribute on both squads held
identical. New `tests/test_player_specific_decisions_flanker.py` (2
tests, same pattern as the scrum-half's own test file).

### A third player-specific decision behavior: the near wing's footwork (match-engine-depth Phase 9)

Extends the same pattern to a third position. `_resolve_phase` computes a
small "wing break" try chance (`p_wing_break`) whenever the zone is close
to the line, built from the NEAR wing's (the real winger matching the
ball's current `Side` - see `Side`'s own docstring) own `footwork`/`pace`:
`p = clamp((skill-60)/350, 0.0, 0.05)`. `_score_try` gained a general
`individual_flavor` string parameter (the scrum-half's `snipe=True` stays
as a thin, backward-compatible alias for its own specific text) so each
player-specific outcome can carry its own distinct commentary without
growing a new boolean flag per position - a wing break reads "steps the
last defender and goes over in the corner - a brilliant individual
finish." Verified live: an elite-footwork/pace wing produced 21 such
tries across 60 simulated matches vs. 9 for an average one, every other
attribute held identical. New `tests/test_player_specific_decisions_wing.py`
(2 tests) - note the test had to check BOTH real wings by name, not just
the one whose attributes were boosted, since the mechanism correctly
fires for whichever wing matches `Side` that phase, not always the same
physical player.

## Per-drive flow (`_advance_one_drive`)

1. `_pick_attacking_team` runs one territory-weighted coin flip to decide who
   has this drive (see below).
2. `drive_minutes = rng.randint(1, 4)` - the minute clock advances by 1-4
   minutes per drive. **This jump size is pure chance, not attribute-driven
   at all** - no attribute or rating influences how big a jump is rolled.
   It only sets the pace at which drives (and therefore scoring
   opportunities) occur over 80 minutes; it has no bearing on which team
   is attacking or what the drive's outcome is.
3. Cards expire if their window has passed; stamina decays for both teams
   over the `drive_minutes` just elapsed (see Stamina section) - still once
   per DRIVE, not once per phase (see "Known limitations" below).
4. `_resolve_drive` checks the once-per-drive card/set-piece events, then
   loops `_resolve_phase` (up to `MAX_PHASES_PER_DRIVE` times) for the
   open-play part of the possession - see "What kind of simulation this is"
   above for the full phase-loop account.
5. `_maybe_personnel_change` separately rolls for an injury and (in a
   fixed minute window) a tactical substitution, each team, each drive.
6. `_update_knockout_stage` advances the knockout tiebreak state machine if
   relevant.

So a single call to `_resolve_drive` stands in for an entire possession
(however many real rucks/scrums/tackles that would involve); the number of
drives that occur in a match is itself a product of chance (step 2) rather
than anything the lineups control.

## Who attacks: `_pick_attacking_team` / `_territory_strength`

```
territory_strength(team) = kicking*0.5 + aerial*0.3 + handling*0.2   (team sub-ratings)
home_terr  = territory_strength(home) * card_penalty(home) [+ HOME_ADVANTAGE_BONUS if home_advantage]
away_terr  = territory_strength(away) * card_penalty(away)
home_prob  = home_terr / (home_terr + away_terr)             (weather="windy" flattens this toward 0.5)
```

One `rng.random() < home_prob` decides which team gets this drive. This is
attribute-driven (kicking/aerial/handling sub-ratings, softened by stamina
inside `_team_sub_rating`) plus the small, explicit home-field nudge
(`HOME_ADVANTAGE_BONUS = 3.0`, mirroring `tournament/rankings.HOME_ADVANTAGE`)
when `home_advantage=True` was passed to the constructor. There's no concept
of "momentum" or "previous drive's result" feeding into the next one - each
drive's attacking-team roll is independent given the two teams' current
(stamina/card-adjusted) sub-ratings.

## Per-outcome breakdown (`_resolve_drive`/`_resolve_phase`)

Since match-engine-depth Phases 4-5, this is no longer one single roll for
the whole drive. `_resolve_drive` checks a few once-per-drive events first
(card; then the possession-origin roll, which may hand off to
`_resolve_scrum`/`_resolve_lineout` - see "Set piece" above), then the
open-play part of the drive loops `_resolve_phase` (up to
`MAX_PHASES_PER_DRIVE` times), each call rolling ONE `roll = rng.random()`
walked through a cumulative sum (`take(p)` helper) in this fixed priority
order: try, drop goal, penalty-by-defense (open play), breakdown turnover,
penalty-by-attack, handling error, else "continue" (the drive stays alive,
credits carry/tackle/ruck stats - see "New per-phase stats" above). The
scrum-penalty and lineout-turnover outcomes that used to sit in this same
per-drive menu are now resolved separately, once per drive, only on a
scrum-/lineout-origin drive (see "Set piece" above) - they no longer
compete for probability mass against try/penalty/error on every phase.
Because `take(p)` only ever consumes from whatever probability mass is
still unclaimed by the time it runs, each new branch added over this
engine's history only ever shrunk the catch-all "continue" slice (the one
outcome with no formula of its own, defined as "whatever's left"), never
another outcome's own formula.

| Outcome | Formula (edge = attacking-relevant rating(s) − defending-relevant rating(s), /100) | Attributes/sub-ratings involved |
|---|---|---|
| **Try** | `p = clamp(0.11 + edge*0.10, 0.02, 0.45)`, `edge = (attack_rating − tackling_def)/100` | attacking team's `attack` sub-rating vs defending team's `tackling` sub-rating |
| **Drop goal** | `p = clamp(0.004 + (dg_skill − 55)/1500, 0.001, 0.01)`, `dg_skill = (place_kicking_range + game_intelligence)/2` for the attacking side's designated kicker (`_best_kicker`, same player used for conversions/penalties) | the attacking kicker's own `place_kicking_range` (execution/range) and `game_intelligence` (decision to go for it) attributes - a per-player read, like the conversion/penalty-goal rolls, not a team sub-rating average |
| **Penalty conceded by defense** (open play) | `p = clamp(0.14 + edge*0.12, 0.03, 0.35)`, `edge = (70 − discipline_def)/100` | defending team's `discipline` sub-rating only (not fit-scaled - see `ATTRIBUTE_MAPPING.md`/module docstring: discipline isn't treated as position-dependent) |
| **Scrum penalty** (`_resolve_scrum`, scrum-origin drives only) | `p = clamp(0.04 + edge*0.05, 0.0, 0.12)`, `edge = (scrum_atk − scrum_def)/100` | both teams' `scrum` sub-rating (front row + locks only, via `CATEGORY_POSITION_GROUPS`) |
| **Scrum turnover ("against the head")** (`_resolve_scrum`) | `p = clamp(0.01 − edge*0.02, 0.002, 0.05)`, same `edge` as the scrum penalty above | same scrum sub-ratings; names the specific weakest attacking front-row player and strongest defending one in commentary |
| **Lineout turnover** (`_resolve_lineout`, lineout-origin drives only) | `p = clamp(0.05 − edge*0.06, 0.01, 0.14)`, `edge = ((thrower_throwing + attacking_jumping)/2 − defending_jumping)/100` | the attacking HOOKER's `lineout_throwing` + each side's best jumper's `lineout_jumping` (`_best_lineout_jumper`) - two NAMED individuals per side, not a team-sub-rating average |
| **Breakdown turnover** | `p = clamp(0.06 + edge*0.08, 0.01, 0.18)`, `edge = (breakdown_def − breakdown_atk)/100` | defending team's `tackle_technique` sub-rating (dominant hits + jackal threat) vs attacking team's `handling` sub-rating - a deliberately separate swing term from both the scrum and lineout ones, so a jackal-heavy back row creates turnovers independent of set-piece strength |
| **Card (against the defending team)** | `p = 0.015 * clamp(1.4 − discipline_def/70, 0.3, 2.0)` | **fixed**: this now reads the *defending* team's discipline sub-rating, as the outcome name always said it should (a less-disciplined defense gives away more cards) - previously this line read `discipline_atk` (the attacking team's discipline) instead, a confirmed bug; see "Fixed in this pass" below |
| **Penalty conceded by attack** | `p = clamp(0.08 + edge*0.10, 0.02, 0.30)`, `edge = (70 − discipline_atk)/100` | attacking team's `discipline` sub-rating only |
| **Handling error** | `p = clamp(0.16 − edge*0.10, 0.04, 0.35)`, `edge = (handling_rating − 60)/100` | attacking team's `handling` sub-rating only (no defending-side pressure term) |
| **No outcome ("defense holds")** | whatever probability mass remains after all the above | implicitly whatever's left; not its own formula |

## Fixed in this pass

Two confirmed bugs from the prior (documentation-only) pass of this file
have now actually been fixed in `_resolve_drive`:

1. **Drop goals now simulate.** A real drop-goal branch exists in the
   outcome menu (see table above), worth 3 points, incrementing
   `TeamMatchStats.drop_goals` *and* `PlayerMatchStats.drop_goals` (the
   latter field is new - added so the scoring kicker gets individual
   credit, same as a conversion or penalty goal) for the scoring team, and
   generating a `DROP GOAL! <kicker> (<team>) drops a goal.` commentary
   event via the same `_event(..., add_score=...)` convention as
   try/penalty events. `web/app.js`'s `SCORE_EVENT_RE` (the crowd-cheer
   trigger) was updated to also match `^DROP GOAL!`, so a successful drop
   goal now cheers like any other score. Calibrated (see cross-checks
   below) to roughly 30-35 drop goals per 100 simulated matches combined
   across both teams (~30% of matches have at least one, most have zero) -
   deliberately rare, matching real Test rugby's modest drop-goal
   frequency, not bolted on at a rate that makes it a routine score.
2. **Card formula now reads the defending team's discipline.** `p_card`
   previously read `discipline_atk` despite being the *defending* team's
   card risk; it now reads `discipline_def`. Hand-traced: a defending team
   with poor discipline (sub-rating 30) now rolls `p_card ≈ 0.0146`,
   a defending team with good discipline (sub-rating 80) now rolls
   `p_card ≈ 0.0045` - the probability now correctly rises as the
   defending side's own discipline gets worse, not the attacking side's.

All of the attacking-side and defending-side sub-ratings above are run
through `_active_card_penalty` first (a team playing a player down from an
active card is scaled down, from 1.0 at full strength to a floor of 0.6 at
4+ cards: `max(0.6, 1.0 - 0.15*n_down)`) and, via `_team_sub_rating`, through
each player's live stamina factor (`_stamina_factor`, 0.7-1.0) before being
averaged across the relevant position group. So every one of these
probabilities is already a composite of: raw attributes -> position fit ->
team sub-rating -> stamina softening -> card penalty -> edge vs opponent ->
clamped probability. That's a real, inspectable attribute chain; it is not,
however, a simulation of the actual contest (no explicit "who wins this
specific scrum/ruck" resolution beyond the probability the roll already
encodes).

**Genuinely attribute-grounded**: every outcome above has at least one real
team sub-rating feeding its probability. There is no drive outcome in this
engine that is pure fixed-probability RNG with zero attribute input.

**Formerly a confirmed gap, now fixed - drop goals are simulated.**
`TeamMatchStats`/`PlayerMatchStats`-adjacent reporting code
(`tournament/tournament_stats.py`, `webapp.py`, `web/app.js`, and multiple
`data/classic_matches*.py` objective helpers like `team_drop_goals_at_least`)
read/display a `drop_goals` counter; `_resolve_drive`'s outcome menu now has
a real drop-goal branch (see table above) that increments it. Any
classic-match objective or tournament stat depending on a team scoring N
drop goals can now actually be satisfied, subject to the modest frequency
the new branch is calibrated to - see "Fixed in this pass" above.

## Try scoring detail (`_score_try`)

Once "try" is the rolled outcome, two further sub-steps run, each its own
small attribute-driven roll - not part of the single drive-outcome dice roll
above, but immediately afterward:

- **Scorer**: `_pick_try_scorer` picks among the attacking XV weighted by
  each player's `attack` sub-rating at their current slot, +25 flat bonus if
  their position is in `BACKS`. `rng.choices(..., weights=weights)`.
  Verified by tracing: a back with `attack=60` gets weight 85; a forward
  with `attack=60` gets weight 60 - genuinely attribute-driven, with a
  positional thumb on the scale that isn't itself derived from any attribute
  (the `+25` is a flat constant, not attribute-scaled).
- **Conversion**: the team's best `goal_kicking` player (`_best_kicker`)
  attempts it at `p = clamp(0.35 + goal_kicking/150, 0.15, 0.95)`. A
  `goal_kicking=100` kicker converts at clamp(1.017→0.95); a `goal_kicking=0`
  kicker at clamp(0.35→0.35). Attribute-driven, single player (not a team
  average).

## Penalty-shaped kicks (`_score_penalty_chance`)

This method handles open-play/scrum penalty chances and is the place a kick
at goal from a penalty is resolved. It is NOT where drop goals are
resolved - the real in-open-play drop-goal attempt is now its own separate
branch directly inside `_resolve_drive` (see the outcome table above), with
its own formula and its own kicker-attribute read; it does not call into
this method at all. Flow for a penalty chance: the attacking team's best
kicker decides to go for posts
(`rng.random() < 0.75` OR `goal_kicking > 70` - i.e. a weak kicker still
goes for posts 75% of the time; there is no territory/distance-from-posts
input at all, acknowledged in the code's own comment: "deep territory
heuristics omitted for simplicity"). If going for posts,
`p = clamp(0.55 + goal_kicking/200, 0.3, 0.95)`.

## Cards (`_issue_card`)

`is_red = rng.random() < 0.12` (a fixed 12% chance, independent of any
attribute - once the drive has already decided "a card happens," which
*color* it is is pure chance). Law 19.2 escalation (second yellow for the
same player, same match, -> red) is deterministic given that player's own
match history, not a further roll. Which player on the carded team gets
carded is a uniform `rng.choice` among currently-on-field, not-yet-sent-off
players - **uniform, not attribute-weighted at all** (unlike the try-scorer
pick, nothing about a player's own discipline, aggression, or any attribute
affects which specific player draws the card once "defense gets carded"
has already been decided at the team level by `p_card` above).

## Stamina / fatigue decay (`_decay_stamina`)

Every player decays every drive, condition 100 -> floor 20, at
`STAMINA_DECAY_PER_MINUTE (0.52) * decay_rate * drive_minutes`, where
`decay_rate` blends four terms and is clamped to [0.3, 2.2]:

1. `fitness_factor = 1.5 - fitness/100` (dominant term: higher fitness = slower decay)
2. `workload_factor = 0.85 + POSITION_WORKLOAD[position]*0.35` (reuses the
   existing `POSITION_PROFILES` attribute-weight table's fitness+strength+
   scrummaging share per position - not a new table)
3. `strength_term = (strength-50)/100 * 0.15` (bigger players tire slightly faster)
4. `pace_term = (pace-50)/100 * 0.10` (faster players tire slightly faster)

...multiplied by a team-level `pressure_factor` (`_matchup_pressure_factor`)
that reuses the SAME `attack`/`tackling` sub-ratings `_resolve_drive` already
computes: a team facing a stronger attacking opponent than its own defense
decays 0.9x-1.1x faster. Stamina then feeds back into every sub-rating via
`_stamina_factor` (0.7 at floor, 1.0 fresh) inside `_team_sub_rating` -
a tired team is a uniformly worse team at every category, not singled out to
one stat. This is explicitly documented in-code as a heuristic ("no real
sports-science fatigue model is being claimed here") and this doc affirms
that framing is accurate: it's a plausible, hand-tuned gradient, not a
physiological model.

## Home advantage

A single constant, `HOME_ADVANTAGE_BONUS = 3.0`, added directly to the home
side's `territory_strength` inside `_pick_attacking_team`, only when
`home_advantage=True` was passed to `MatchEngine.__init__`. It affects
nothing else (no sub-rating, no try/penalty/card probability directly) - its
entire effect is "home gets a few more drives than their territory strength
alone would earn them," which then compounds through whatever the normal
per-drive outcome odds already are. It deliberately mirrors
`tournament/rankings.HOME_ADVANTAGE` so the project isn't carrying two
independently-invented home-field magnitudes.

## Knockout decider: extra time / sudden death / shootout

Only active when `decide_winner=True`. A tie at 80 minutes triggers 20
minutes of extra time (played out in full via the normal drive loop -
same attribute-driven `_resolve_drive` as normal time, nothing different
here), then sudden death (same drive loop, but `is_finished` stops the
instant the score changes) capped at `SUDDEN_DEATH_CAP_MINUTES=20` (a
simulation safety valve, not a real rule), then, if still tied,
`_run_kicking_competition`: 5 rounds each side's best `goal_kicking` player
alternating kicks (`_kick_success_probability = clamp(0.5 + (goal_kicking-50)/150, 0.15, 0.95)`),
sudden-death kicking rounds after that if still level, capped at
`KICK_COMPETITION_SAFETY_CAP=50` extra rounds with a final coin-flip
fallback. Who kicks first is the one explicit coin flip the real rule
specifies; who kicks (each side's best current kicker) is not random.
**Extra time and sudden death are fully attribute-driven** (same engine as
normal time); **the shootout is attribute-driven only through each kicker's
`goal_kicking`** - no other attribute plays any role once it starts.
Crucially, the shootout never changes `score_home`/`score_away` - a
shootout-decided knockout match is still officially recorded as a tied
scoreline, with `shootout_winner` as the separate field a caller must check
to find out who actually advances.

## Cross-checks performed for this document

1. **Try formula**: traced `attack_rating=60, tackling_def=50` ->
   `edge=0.10` -> `p_try = clamp(0.11+0.01, ...) = 0.12`, confirmed against
   the literal arithmetic in `_resolve_drive` lines computing `p_try`.
2. **Breakdown turnover**: confirmed `breakdown_def` reads
   `tackle_technique` (not a generic "defense" category) and `breakdown_atk`
   reads `handling` (not "attack") - these are genuinely different sub-
   rating categories than the try/penalty terms use, matching the module
   docstring's claim of "separate swing terms with different inputs."
3. **Drop goals**: grepped the full `rugby_sim` tree for `drop_goal` -
   confirmed `TeamMatchStats.drop_goals` is declared and read by five+ other
   files; `_resolve_drive` now writes (`+=`'s) it for the scoring team, and
   a 300-seed synthetic-match run after the fix produced ~34 drop goals per
   100 matches (about 30% of matches with at least one), confirming the
   branch is genuinely reachable and not vanishingly rare or constant.
4. **Card color**: confirmed `is_red = rng.random() < 0.12` has literally no
   attribute term in it - re-read the full `_issue_card` body to make sure
   no earlier line modifies this threshold before the comparison; it
   doesn't.

## Known limitations

1. ~~No individual player-vs-player tackle, carry, or ruck resolution of
   any kind - every drive resolves as one team-level weighted dice roll,
   never a ball-carrier-vs-specific-defender contest.~~ **Partially fixed
   (match-engine-depth Phase 4)**: a drive is now a bounded loop of
   per-phase team-level rolls (`_resolve_phase`), each one crediting a
   named carrier and a named tackler - still not a true, independent
   player-skill-vs-player-skill contest (the carrier/tackler are picked by
   weighted/uniform selection AFTER the phase's team-level outcome is
   already decided, same as the existing try-scorer/card-recipient picks),
   but no longer a single opaque team-level roll for the whole possession
   either.
2. ~~No explicit possession-chain or phase count within a drive - a drive is
   an opaque unit; the engine has no notion of "3 phases into this
   possession."~~ **Fixed (match-engine-depth Phase 4)**: `_resolve_drive`
   now loops `_resolve_phase` up to `MAX_PHASES_PER_DRIVE` (6) times per
   possession, with the zone/side advancing once per phase (not once per
   drive) and try probability ramped up over the first few phases
   (`PHASE_TRY_RAMP`) rather than being phase-count-blind. Still a bounded,
   discrete loop (a simulation safety valve, not a claimed real rugby
   limit on how many phases a possession can run), not a continuous or
   unbounded phase count.
3. ~~No "attacking shape" or "defensive line" concept, no field position
   beyond the coarse territory-percentage tally (`_territory_ticks`), and no
   distance-to-try-line or distance-to-posts modeling at all (acknowledged
   directly in `_score_penalty_chance`'s own comment).~~ **Partially fixed
   in this pass**: a 3-zone field-position model now exists (`Zone`:
   `HOME_22`/`MIDFIELD`/`AWAY_22`, labelled relative to each team's own try
   line - see `MatchEngine._advance_zone`/`_zone_relative_to`). Every drive
   moves the ball one zone (advance/hold/retreat, reusing the existing
   attack-vs-tackling edge, no new attribute reads), and a drive's try
   probability is now gated by the resulting zone (`ZONE_TRY_MULTIPLIER`:
   1.0 in the defending team's 22, 0.4 at midfield, 0.08 pinned in the
   attacking team's own 22 - verified live: 117/158 simulated tries landed
   in the "attacking_22" bucket vs. 4/158 in "own_22"). Each
   `CommentaryEvent` now carries the zone it happened in. **Phase 2 (same
   pass as the weather fix below)**: `_score_penalty_chance`'s
   `go_for_posts`/`pen_prob` are now also zone-gated - pinned in their own
   22, a side never realistically goes for posts regardless of kicker
   skill (always kicks to the corner instead); in the defending team's 22
   it almost always takes the points; midfield keeps the original
   baseline. Verified live over 80 seeds: 230/230 own-22 penalties were
   kicked to the corner, 0 attempted at goal. **Phase 3 (a further later
   pass)**: `Zone` grew from 3 to 5 values (`HOME_TRYLINE`/`HOME_22`/
   `MIDFIELD`/`AWAY_22`/`AWAY_TRYLINE`) - a finer-grained stepping stone
   toward real spatial modeling, still discrete/coarse, not coordinates.
   `ZONE_TRY_MULTIPLIER`/`ZONE_GO_FOR_POSTS_BASE`/`ZONE_PEN_PROB_ADJUST`
   were re-tuned for the 2 new buckets (`attacking_tryline` highest of all,
   `own_tryline` lowest of all); `_score_penalty_chance` now also
   short-circuits `go_for_posts=False` at `own_tryline`, not just
   `own_22`. A new, independent lateral dimension was added alongside it -
   `Side` (`LEFT`/`MIDDLE`/`RIGHT`, see `_advance_side`, a plain per-drive
   random walk, NOT yet weighted by either team's actual wing attributes -
   a deliberately simple first cut) biases `_pick_try_scorer` toward the
   matching wing and adds a small, honest commentary flavor ("...down the
   left wing"). Verified live over 100-300 seeds: tries cluster even more
   heavily near the attacking line than the 3-zone version already showed,
   penalty kicks still never attempted from either deep zone, `Side`
   genuinely visits all 3 states over a match, and a try scored while
   `Side.LEFT` names the left wing as scorer meaningfully more often than
   at `Side.MIDDLE`. Still coarse (5 zones + 3 lateral positions, not a
   continuous distance-to-try-line/distance-to-posts/x-y model), and
   there's still no "attacking shape"/"defensive line" concept - true
   continuous player-position tracking remains a flagged, much later,
   far larger ambition, not attempted here.
4. Drop goals are now tracked in every reporting layer AND actually
   produced by the engine - see "Fixed in this pass" above. (This item is
   kept, renumbered-in-place, as a historical marker of what used to be a
   gap here; it is no longer true today.)
5. The `drive_minutes = randint(1, 4)` clock-advance roll is pure chance
   with zero attribute input; it controls match pacing (how many drives fit
   into 80 minutes) but nothing in the lineups can speed up or slow down
   the clock.
6. Which specific player receives a card, once "a card happens to this
   team" has been decided, is a uniform random choice among eligible
   on-field players - not weighted by that player's own discipline,
   aggression, or any other attribute.
7. The card-probability formula (`p_card`) was previously keyed off the
   attacking team's discipline to set the DEFENDING team's card chance -
   fixed in this pass to read the defending team's own discipline; see
   "Fixed in this pass" above for the hand-traced before/after numbers.
8. `_has_live_advantage` always returns `False` - a vestigial hook with no
   actual implementation; advantage law (letting a non-infringing team play
   on) is not modeled.
9. ~~Weather ("windy") only flattens the territory-roll home/away split
   toward 50/50; "wet" is accepted by the constructor but has no documented
   effect found anywhere in `_resolve_drive`, `_pick_attacking_team`, or
   anywhere else searched in this file - if "wet weather" is meant to do
   anything today, it isn't wired up in this module.~~ **Fixed in this
   pass**: `weather == "wet"` now adds a small flat bump to `p_error`
   (handling errors) and a small flat reduction to `p_try` inside
   `_resolve_drive` - a slick ball making handling harder and tries harder
   to finish is rugby's most obvious real weather effect. Verified live
   over 60 seeds: average handling errors per match rose from 6.6 (dry) to
   8.2 (wet), average tries fell from 1.8 to 1.3 - a modest, directionally
   correct shift, not a dramatic one. "Windy"'s existing territory-roll
   effect is unchanged.
10. A single `rng.choices` scorer pick and a single conversion/penalty kick
    roll are each their own tiny attribute-weighted step layered after the
    per-drive outcome roll - real, but still single dice rolls, not
    sub-simulations of a try celebration, a lineout drive, or a kicking
    routine.
11. The home-advantage bonus and card penalty are additive/multiplicative
    constants calibrated by inspection/feel, not fit to any real match
    dataset - same honesty standard as the stamina constants' own in-code
    commentary ("heuristic... no real sports-science model is being
    claimed").
