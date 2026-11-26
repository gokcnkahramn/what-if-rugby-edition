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

### Kicking system detail (match-engine-depth Phase 11)

Before this pass, "kicking" existed only as `_kick_tendency` (a single
team-wide number nudging `_advance_zone`'s odds) - no distinct kick TYPE,
no named decision, no event of its own. Two real tactical kick options
now exist, each a real risk/reward trade, not just flavor text:

**Cross-field kick** (`_resolve_phase`, a try-scoring slice in the same
cumulative menu as the snipe/jackal/wing-break tries): only reachable
close to the line with the ball on one side (`self._side` LEFT/RIGHT, not
MIDDLE). Combines TWO named individuals' own attributes, not team
averages - the attacking FLY-HALF's own `kicking_game`/`game_intelligence`
(the decision + execution) and the FAR wing's (opposite `self._side` - the
blindside winger, same "far wing stays wide" convention the pitch-diagram
formation tables already use) own `aerial`/`pace` (the finish):
`p = clamp((combined_skill-62)/320, 0.0, 0.045)`. Commentary names both
players ("gathers a raking cross-field kick from <fly-half> and dives in
at the corner"). Verified live: an elite fly-half (kicking_game/
game_intelligence both 99) set up 26 such tries across 60 simulated
matches vs. 4 for an average one.

**Territorial box kick** (`_resolve_phase`, checked AFTER the main
outcome menu - only reached once a phase would otherwise just "continue"
as a carry, and only deep/midfield, never close to the line): the
SCRUM-HALF/FLY-HALF's own `kicking_game` (whichever of the two is higher -
`box_kicker`) decides to trade possession for territory instead of
carrying it up - `p_box_kick = clamp((kick_skill-55)/250, 0.0, 0.30)`. A
real risk: the defending FULLBACK's own `aerial` can read it and force a
charge-down turnover (`p_charge_down`, scaled by the gap between the
kicker's and catcher's skill); otherwise the zone advances one extra step
beyond this phase's normal movement, and the drive ends (a deliberate,
honest trade - the ball is really given up to be chased/contested, not
kept). Verified live: an elite kicking fly-half produced 34 such box
kicks across 60 matches vs. 3 for an average one; a genuinely poor
kicker (kicking_game 70) facing an elite-aerial fullback (aerial 99) had
real, non-zero charge-downs across 60 seeds, confirming the risk side
isn't just text. New `tests/test_kicking_system.py` (4 tests).

### Manager controls: pre-match tactics, in-match penalty decisions, and two more real kick types

User-facing follow-up ("we're the manager, we should be able to play the
game"): every tendency this engine derives (attack shape, defensive style,
kick tendency) used to be purely attribute-derived, with zero way for the
person actually drafting a lineup to impose their own gameplan, and every
in-match decision (what to do with a penalty) was a silent AI auto-pick.

**Pre-match tactics** (`TACTIC_CHOICES`, `MatchEngine(tactics=...)`): a
manager can pick, per team, a real stance on 3 existing axes -
`attack_shape` (forward_heavy/balanced/backs_heavy), `defensive_style`
(blitz/balanced/drift), `kick_tendency` (kick_heavy/balanced/ball_in_hand) -
each a real REPLACEMENT of the attribute-derived number for that axis
(`_attack_shape_tendency`/`_defensive_style`/`_kick_tendency` check
`_tactics_override` first), not a blend. A team/axis left unset keeps
today's exact derived behavior. `kick_tendency`'s real effect was also
genuinely strengthened in this same pass - it used to only nudge
`_advance_zone`'s territory roll; it now ALSO raises the real box-kick
decision's own odds (`kick_tendency_factor` in the box-kick branch), so
"kick_heavy" means more real box kicks, not just faster territory gain.

**In-match penalty decision** (`decision_teams`, `_pending_penalty`,
`resolve_pending_decision`, `PENALTY_CHOICES`): for a listed team, a
just-awarded penalty pauses resolution (`advance_to`/`finish` stop the
instant `_pending_penalty` is set, exactly like reaching a checkpoint)
instead of auto-deciding `go_for_posts` - the manager picks `"posts"`
(only offered when `can_go_for_posts`, i.e. not pinned in their own 22),
`"touch"`, or `"quick_tap"` (keeps the ball alive immediately, no kick at
all). Wired into every match mode (Friendly, Draft, Tournament, Season) via
the same `_start_live_match`/pause-hook plumbing each mode already used for
live substitutions.

**Two more real kick types** (closing the "grubber/chip kick" gap the
original kicking-system pass left open): a **grubber kick**
(`attacking_tryline` only, the SCRUM-HALF's own `kicking_game`/
`game_intelligence` driving a low kick through the line, chased by the
NEAR wing - same side as `self._side`, unlike the cross-field kick's far
wing) and a **chip kick** (only reachable while facing a genuinely
blitz-leaning defence - the real counter to a fast rush line - the
FLY-HALF's own `kicking_game`/`game_intelligence` chipping over it, chased
by the near wing). A manager can also set a `kick_style` preference
(`grubber`/`chip`/`cross_field`/`box_kick`, a label, not a [-1,1]
override) giving that ONE kick type's own probability a real, bounded
`KICK_STYLE_BOOST` (1.6x) - never a guarantee, the underlying skill/zone/
defensive-style gates still apply.

**A new, purely clock-driven strategy tier**, independent of the
scoreline (`_score_pressure` already covers that): `_period_caution_factor`
damps individual-break probabilities during the opening
`PERIOD_CAUTION_WINDOW` (8) minutes of EACH half - a real "cagey start,"
both sides feeling each other out before committing to high-risk
individual plays, ramping linearly back to 1.0 (no change) by the end of
the window.

**Investigated, not changed - "antrenör etkisi" (coach influence)**: this
pass's own `tactics`/`decision_teams` mechanism genuinely IS the honest
version of a coach effect - a real human (or, for an AI-controlled team,
the lineup's own real attributes) decides the gameplan; there is no
separate, additional "coach" entity with its own invented skill number to
model on top of that without violating this project's own "never invent
data" stance (there is no real per-coach rating data anywhere in this
project's pipeline). Reported honestly as already satisfied by the above,
not left as a separate open item.

Verified live: `kick_heavy` raises real box-kick counts over 150 seeds (a
direct comparison against `ball_in_hand` is NOT clean, since a slower
`_advance_zone` tendency means more time spent in the own-half zones a box
kick is even possible from at all - documented in
`test_tactics_system.py`'s own test, not papered over); a decision-team's
penalty genuinely pauses `advance_to`/`finish` (confirmed: a quick-tap
choice never scores and is named in the event text, a touch choice never
attempts posts); grubber/chip kicks are each confirmed to exist (chip
confirmed zero against a neutral defence, non-zero against a blitz-leaning
one); `_period_caution_factor` confirmed monotonic and bounded. New
`tests/test_manager_penalty_decisions.py` (6 tests), `tests/
test_kicking_types.py` (5 tests), 3 new tests in `tests/
test_tactics_system.py`. Full suite: 361/361 passing before this
kicking-types/period-tier/role-link follow-up; re-verified green after.

### A real pre-existing bug found and fixed: `tackle_technique`/`positioning` never worked

While building defensive organization (next section), a real bug was
found in `Player.sub_ratings()` (`models/player.py`): the breakdown-
turnover formula has read `_team_sub_rating(defending, "tackle_technique")`
since it was first written (`MATCH_ENGINE_MODEL.md` has described this as
"driven by the defense's tackle_technique" the whole time), but
`sub_ratings()`'s returned dict never actually had a `"tackle_technique"`
key - every single lookup silently fell back to `_team_sub_rating`'s own
generic default (50) for every player, meaning this term NEVER actually
varied with real player attributes at all, for the entire time this
feature existed. Fixed by adding real `"tackle_technique"`/`"positioning"`
entries to `sub_ratings()` (the latter needed for the new defensive-
organization feature below, for the same reason). This is a genuine
correctness fix, not a tuning change - confirmed via
`tests/test_defensive_organization.py`'s own regression guard.

### Defensive organization: blitz vs. drift (match-engine-depth Phase 12)

New `MatchEngine._defensive_style(team) -> float` ([-1, 1], positive =
blitz-leaning, negative = drift-leaning), derived from the now-real
`tackle_technique` (aggressive technique) vs `positioning` (patient,
structured) sub-ratings - same `team_sub_rating`-based convention as
`_kick_tendency`, cross-checked against rugbyslate.com's own "the drift
defence"/"the blitz defence" articles (researched earlier in this
project): blitz is a fast, aggressive line that meets each attacker
1-on-1, strong against an overlap but risks a missed tackle/card if a
defender mistimes the rush; drift shifts the whole line across to cover
the ball, rarely beaten wide but gives up some central ground. Three real,
distinct effects, not one shared bonus:
- `_advance_zone`: a blitz-leaning DEFENDING team reduces the attacking
  team's advance probability (compresses space) - drift gets no such
  bonus here.
- `_resolve_drive`: a blitz-leaning defence gets a modest extra card risk
  AND a modest extra breakdown-turnover bonus (the real cost/benefit of
  rushing up fast) - drift gets neither.
- `_resolve_phase`: a drift-leaning defence specifically damps the
  ATTACKING team's individual break probabilities (the scrum-half snipe,
  wing break, and cross-field kick tries - Phases 6/9/11) via a shared
  `drift_factor` (1.0 at blitz/balanced, down to 0.5 at full drift) - a
  real defensive-organization distinction a flat team-wide rating alone
  couldn't express, since drift's whole point in real rugby is shutting
  down individual breaks specifically, not raw territory or cards.
New `team_defensive_identity(lineup) -> str` ("Blitz / rush defence" /
"Drift defence" / "Balanced"), same pre-match-team-sheet convention
`team_tactical_identity` already established - threaded into `webapp.py`'s
`_match_json` (new `defensive_identity` field) and shown in `app.js`
alongside the existing tactical-identity line. Verified live: a
blitz-leaning defence conceded more cards and forced more turnovers than
a drift-leaning one over 60 seeds (both directionally correct, modest
magnitudes); a drift-leaning defence suppressed the attacking team's
individual break tries meaningfully more than a blitz-leaning one over
150 seeds (136 vs 104 for this exact attribute pair - needed the larger
sample to separate reliably from noise, a smaller 60-seed check showed
the same direction but too close to call confidently on its own). New
`tests/test_defensive_organization.py` (4 tests).

### Referee system (match-engine-depth Phase 13)

Before this pass, every general-play defensive penalty wrote the same
generic "Penalty against X at the breakdown" text, and every handling
error wrote the same generic "handling error" text - no distinct knock-on
vs. forward pass, no offside, no advantage concept at all. Three real,
named additions, in `_resolve_phase`/`_score_penalty_chance`:

**Named infringements, at no extra RNG cost**: both the
`p_pen_conceded_by_def`/`p_pen_conceded_by_atk` penalty branches and the
`p_error` handling-error branch now pick a specific, real reason
("offside" / "for not releasing the ball" for a penalty; "knock-on" /
"forward pass" for an error) from WHERE the already-rolled `roll` landed
within that outcome's own slice of the cumulative menu (`slice_position =
(roll - slice_start) / slice_width`) - a free byproduct of the existing
single-roll-per-phase menu, not a new probability or a new RNG call.
Verified live over 60 seeds: both knock-on/forward-pass and offside/
not-releasing occurred with plausible, non-zero counts for each (knock-on
the more common of the two errors, as in real rugby).

**Advantage**: a real rugby concept, not just a label - when a general-
play defensive penalty fires, the referee doesn't blow immediately; if the
attack was ALREADY in a position to score anyway that same phase (rolled
fresh against this phase's own zone-gated `p_try`, already computed), the
try stands instead of the penalty ("plays advantage and goes over - no
need to bring it back for the penalty"). This genuinely changes which
outcome the phase resolves to, not just flavor text. Verified live: 10
advantage-tries occurred across 60 simulated matches - a real, non-zero,
occasional mechanic, as advantage should be in real rugby (not the common
case, but not never either). New `tests/test_referee_system.py` (4 tests).

### Condition/injury/card depth (match-engine-depth Phase 14)

Four real additions, closing the user's third checklist ("players
shouldn't perform the same for all 80 minutes"):

**Fatigue-linked injury risk**: new `MatchEngine._team_fatigue_factor(team)`
(0 fresh, 1 exhausted - the team's current starting XV's real average
tracked `_stamina` condition, no new signal) now scales
`P_INJURY_PER_DRIVE` up to `INJURY_FATIGUE_MULTIPLIER` (1.5) - a fully
exhausted team carries 2.5x the baseline per-drive injury risk, a fully
fresh team is unaffected. The VICTIM is also now picked weighted by
individual fatigue (`_apply_injury`'s `rng.choices` with a
`max(1.0, 100 - condition)` weight) instead of a uniform coin-flip among
all 15 - a more tired player is more likely to be the one who gets hurt.
Verified live: a team forced to start every drive at condition 15 racked
up more injuries over 60 seeds than one left at its normal fresh
condition.

**Named injury types**: new `INJURY_TYPES` table (hamstring strain, ankle
sprain, shoulder injury, knee injury, calf strain, rib injury, concussion,
groin strain) - a separate axis from the existing severity tiers ("what
got hurt", not "how bad"), rolled independently, with ONE honest,
well-known real-rugby exception: a concussion is re-rolled to a non-zero
severity tier if it would otherwise land on a same-match "knock" (0
lay-off) - reflecting the real graduated return-to-play/HIA protocol
every major union actually follows, not an invented medical rule.

**Position-specific card/injury impact**: `_team_sub_rating` now tracks
`_sent_off_positions` (populated on a genuine send-off or a no-cover
injury) and applies an EXTRA, targeted penalty (0.85x) only to the
category group(s) that missing position actually contributes to (losing a
prop hits `scrum`/`lineout`/`aerial` specifically, not `kicking`) - on top
of, not instead of, the existing flat `_active_card_penalty` that already
applies everywhere. Verified: a sent-off tighthead prop measurably lowers
`scrum` but leaves an unrelated category (`kicking`) completely
unaffected.

**Return-from-injury conditioning deficit** (`tournament/availability.py`):
a player's first match back after a REAL injury layoff (never a red-card
suspension - tracked separately via `_sidelined_reason`) now starts at a
harsher, fitness-modulated condition band
(`RETURN_FROM_INJURY_CONDITION_MIN/MAX`, 70-88) than the existing
quick-turnaround short-rest band (85-95) - consumed (popped) after exactly
one match, so a returning player isn't still "rusty" several games later.
Verified: the deficit applies to the match immediately after a tracked
injury layoff expires, and only to that one match; a red-card suspension
expiring the same way does NOT trigger it. New
`tests/test_injury_and_card_depth.py` (6 tests).

### Tactics/strategy system (match-engine-depth Phase 15)

The user's fourth checklist, headline goal: "two teams with the same
squad should get different results with different tactics." Since this
engine derives every tactical signal from real attributes rather than a
user-chosen setting (same philosophy as `_kick_tendency`/`_defensive_style`
before it), "different tactics" here means two squads with a genuinely
different SHAPE or GAME STATE produce measurably different outcomes - not
a menu the user picks from.

**`_attack_shape_tendency(team)`** ([-1, 1], positive = forward-heavy,
negative = backs-heavy): compares the current starting XV's forwards' own
`attack` sub-rating average against the backs' own
(`models.position.FORWARDS`/`BACKS`). A forward-heavy team's pick-and-go
(`_resolve_scrum`) and driving-maul (`_resolve_lineout`) probabilities get
a real boost (`forward_heavy_bonus`); a backs-heavy team's individual
break probabilities (snipe/wing-break/cross-field, all in `_resolve_phase`)
get one instead (`individual_break_factor`'s `backs_heavy_factor` term).
Verified live (direct formula calls, not full-match counts - see the test
file's own docstring for why a full-match count turned out to be
confounded by the generic `p_try` slice also shifting): boosting the
forwards' or the backs' pace/footwork/offload moves `_attack_shape_tendency`
in the correct direction and magnitude order.

**`_score_pressure(team, minute, result)`** ([-1, 1], positive = chasing
the game, negative = closing it out): built purely from the REAL live
scoreline and `minute`, deliberately `0.0` for the whole first half and
for any close scoreline (real "game state" only matters once there's
something to react to). Feeds `individual_break_factor`'s
`pressure_factor` (a chasing team takes more individual risks) and the
box-kick decision's `pressure_factor` (a chasing team is less willing to
give the ball away on a territorial kick; a team closing out a lead is
more willing). Verified: `0.0` in the first half regardless of score;
positive when down 14 at minute 70, negative when up 14; urgency rises
through the second half (a given gap matters more with 5 minutes left
than with 35).

**Tactical reaction to the opponent's defensive style**: a drift-leaning
defence's general `drift_factor` damping (section 12 - correctly
suppresses ground-level individual breaks) is partly offset specifically
for the cross-field kick (`drift_counter_bonus`) - real rugby's own
"attacking the drift" counter goes OVER a drifting line, not through it,
so this one mechanic shouldn't be damped the same way the snipe/wing-break
are. A blitz-leaning defence raises the box-kick decision's probability
(`blitz_counter_bonus`) - the real counter to a fast rush line is kicking
in behind it, not carrying into it.

New `tests/test_tactics_system.py` (4 tests, all deterministic formula
checks rather than full-match statistical counts - explained in the test
file's own docstring).

### Match stats/analysis system (match-engine-depth Phase 16)

The user's fifth checklist, closing note: "stats must be produced from
real engine events and stay internally consistent." Every field below is
credited at the EXACT point the engine already resolves that real
outcome - no new rolls, no new probabilities, purely additional
bookkeeping layered onto existing branches.

**New `TeamMatchStats` fields**: `scrums_contested`/`lineouts_contested`
(credited once per scrum-/lineout-origin drive regardless of outcome -
what makes a real success RATE possible, not just a raw won count);
`defenders_beaten` (a "continue" phase's own `metres` roll counts as
beating a defender once it clears `DEFENDERS_BEATEN_METRES_THRESHOLD` -
re-tuned from an initial draft value of 8, which turned out to NEVER fire
under this engine's real edge range, even for a heavily boosted attack,
down to 5, the value the engine's own distribution actually reaches -
verified live, not guessed); `turnovers_conceded`/`rucks_lost` (the
mirror of the existing `turnovers_won`/`rucks_won`, credited on the exact
same breakdown-turnover/handling-error/scrum-against-the-head/lineout-
steal/box-kick-charge-down branches that already credit the other side);
`kicks_attempted`/`kicks_successful`/`kicking_metres` (territorial box
kicks only - a cross-field kick is a try-scoring play, not a territorial
exchange, so it's deliberately excluded here; `kicking_metres` uses
`KICKING_METRES_PER_ZONE_STEP` (22), the real distance one zone-step
already implies given the 5-zone model's own real span, not an invented
number); `red_zone_possessions`/`red_zone_tries` (did this drive ever
reach the defending team's 22/tryline, and did it finish with a try -
tracked at drive granularity in the open-play phase loop, plus directly
in the two zone-gated set-piece-try sub-scenarios where it's always true
by construction; an early-exit drive outcome before reaching the phase
loop - a card, a scrum/lineout penalty/turnover - doesn't update it, a
documented, scoped simplification).

**New `PlayerMatchStats.performance_score`**: a single documented
weighted blend of every real per-player stat already collected (scoring
weighted heaviest, carrying/tackling/turnover involvement contributing a
smaller real amount) - so a non-scoring prop who put in a heavy shift can
post a real, non-zero number, not "performance" meaning only "did you
score." Verified live: a non-scoring player with real carries/tackles
posts a positive `performance_score`.

**Derived percentages** (`webapp.py`'s new `_team_stats_json`, computed
from the real counts above, never a separately invented number):
`possession_pct` (needs both teams' raw `possessions` at once - a team's
share of the match total), `scrum_success_rate`/`lineout_success_rate`
(won/contested), `kicking_accuracy` (successful/attempted box kicks),
`try_conversion_rate` (conversions/tries), `red_zone_efficiency`
(red_zone_tries/red_zone_possessions) - each `None` (shown as "-" in the
UI) rather than a divide-by-zero or a fabricated 0% when the denominator
is genuinely zero. New `tests/test_match_stats_system.py` (5 tests,
including a direct check that `turnovers_won`/`turnovers_conceded` match
EXACTLY between the two sides, not just "both non-zero").

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
