# What If Rugby Edition

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](<https://img.shields.io/badge/tests-292%20passing-brightgreen.svg>)](tests/)

**What if you played Antoine Dupont at fullback? What if Jonah Lomu started
at tighthead?** Build real squads from real players, drop anyone into any
position, and simulate the match - a click-driven "what if" rugby lab, not
a scripted game.

This started from this week's actual international selection news - and it
wasn't just England. France named Dupont out of his usual scrum-half slot
for the first time; new Wallabies boss Les Kiss handed uncapped debuts to
scrum-half Teddy Wilson and prop Tom Lambert; and Eddie Jones went further
still for Japan, naming Meiji University fly-half Ryunosuke Ito - straight
out of university rugby, no caps - in his Nations Championship squad. Three
unions, three selection curveballs, all in the same week. That's exactly
the kind of question rugby fans ask constantly ("what if he played there
instead? what if they'd picked that uncapped kid?") but never get to
actually test. This repo is built so anyone can run that experiment in
under a minute: pick a real international pool, move a player wherever you
like, and watch a full match play out - no spreadsheets, no manual
stat-crunching.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m rugby_sim.webapp
```

Open `http://127.0.0.1:5000` - that's it. Pick a pool, click a position,
click a player, run the match.

## What you can do

- **Friendly match** - build two squads from real national-team pools (or
  Legends, or historical World Cup/Six Nations squads), draft any player
  into any position, and simulate.
- **Tournament mode** - replay a real Six Nations/Rugby Championship
  season, the real 2027 World Cup draw, any historical World Cup
  (1995-2023) or Six Nations (2009-2021), or build a fully custom
  tournament - then play your own matches while the rest auto-sims.
  Injuries/red cards sideline a player for their team's *next* match the
  same way whether that team is yours or fully AI-simulated, and a
  suspended/injured starter in a fixed lineup is swapped for the
  best-fitting available bench player rather than permanently altering the
  roster.
- **Draft mode** - merge pools into one shared player pool, alternate
  picks with an AI opponent, a PES21-style 3-round protect/poach phase,
  then build and play your drafted XV.
- **Live play** - pause mid-match to make a substitution or swap two of
  your own on-field players between positions, with a paced, spoiler-free
  event reveal and fast-forward controls. The bench picker shows each
  candidate's fit *at the slot you're filling*, using the same rating math
  as the rest of the app.
- **Stamina** - every player tires over 80 minutes. Decay rate blends their
  own fitness, a position-workload signal (forwards tire faster than
  backs), a small extra cost from strength/pace, and a modest penalty for
  facing a stronger attacking opponent (see `engine/match_engine.py`'s
  `_decay_stamina`). This "condition" score is always shown separately from
  position fit in the live lineup/bench views, even though the engine
  multiplies them together internally. Matches start everyone at full
  condition; in a tournament, a player who featured in the previous match
  starts the next one short of full condition, and the auto-draft AI
  weighs that when picking who starts.
- **Injury report** - every match screen lists who got hurt, for which
  team, at what minute, and how severe (a small, named table of injury
  types, each with its own chance and matches missed - a plausible
  heuristic, not a medical model; see `INJURY_SEVERITY_TIERS`). A
  tournament's report view aggregates every injury into a collapsible
  section with a live "out for N more matches" count tied to the
  tournament's current sidelining ledger.
- **Card report** - the same treatment for yellow/red cards, with real
  World Rugby rules: a yellow is a 10-minute sin-bin with no automatic
  future-match suspension; a red sits the player out for their team's next
  tournament match; a second yellow for the same player in the same match
  escalates to a red per law 19.2. The newer, still-trialled 20-minute red
  card variant is not modeled - every red card here plays the older way,
  the team finishes a player short.
- **Team rankings / "Team form" report** - a World-Rugby-style points
  ranking (`tournament/rankings.py`) that moves after every match, real or
  simulated, reimplementing World Rugby's own published formula (rating
  gap + home advantage -> expected result -> zero-sum swing, doubled for a
  World Cup match). Seeded from a hand-entered, dated snapshot of real
  World Rugby points (not a live feed), so ratings diverge from reality as
  "what if" matches get simulated.
- **Tier 2 rankings coverage** - Tier 2 unions (Georgia, Romania, Spain,
  Portugal, Samoa, Tonga, USA, Canada, Uruguay, Chile, Namibia) can now
  appear in simulated Tournament/Season runs instead of sitting frozen at
  their seed rating: the real Pacific Nations Cup and the real Rugby
  Europe Championship are both wired in as replayable real-fixture
  tournaments (current and recent historical seasons), and every union in
  the Rugby Europe Championship resolves a real, named, sourced roster -
  no invented players. See "Project history / build notes" below for how
  these were data-sourced and verified.
- **Season mode** - pick one real union and one real calendar year, and
  play through every real tournament that union actually played that year
  (Six Nations / Rugby Championship / Autumn Nations Series / a World Cup
  year, as detected from real fixture/squad data), chained back to back
  (`tournament/season.py`). Injuries, suspensions, short-rest condition,
  and Team rankings all carry over between tournaments in the season
  instead of resetting. v1 auto-sims every block (no in-season live-match
  pause yet), and the season roster defaults to every player actually
  capped for that union that year, not every eligible-but-uncapped player
  - a genuine data gap, partially closed by the opt-in feature below.
- **Uncapped/eligible players (Season mode, opt-in, ENG/FRA only)** - the
  real stat source has no nationality/eligibility field, so "capped for a
  union" and "eligible for a union" are genuinely different sets.
  `rugby_sim/data/sources/uncapped_pool.py` builds the eligible-but-uncapped
  half from domestic club squad pages on Wikipedia, for England (Leicester
  Tigers, Saracens) and France (Stade Toulousain, Racing 92) only - an
  honest proxy, not a verified legal-eligibility check, and every such
  player's `notes` field says so. Toggle with `include_uncapped: true` on
  `/api/season/start`, or the matching Season-mode UI checkbox; returned as
  a clearly separate `uncapped_pool` list, never silently merged into the
  capped roster.

Every rating comes from real player data (not invented stats), every
tournament/draw is the real thing where one exists, and every heuristic or
approximation is called out explicitly in the code rather than presented
as fact - see `rugby_sim/data/sources/attribute_mapping.py` and the
in-repo docstrings for the honest details. One honest gap: `Player` has no
age field at all - rugbydata (the real stat source this project pulls from)
doesn't track player age for rating purposes, and no other data source used
here provides it either, so nothing here is calibrated by, or claims
anything about, a player's age.

## Project layout

| Path                                         | What's there                                                            |
| -------------------------------------------- | ----------------------------------------------------------------------- |
| `rugby_sim/models/`                        | `Player`, `Position`, `Team`/`Lineup` - the squad-building core |
| `rugby_sim/engine/`                        | `MatchEngine` - the drive-by-drive match simulator                    |
| `rugby_sim/data/`                          | Real player pools, Legends, the rugbydata/Wikipedia data pipeline       |
| `rugby_sim/tournament/`                    | Real & synthetic tournament formats, standings, awards                  |
| `rugby_sim/webapp.py` + `rugby_sim/web/` | The Flask API + clickable web UI (no rugby logic in JS)                 |
| `rugby_sim/interactive_cli.py`             | A terminal-only alternative to the web UI                               |
| `tests/`                                   | 292 tests across data, tournaments, the engine, and the web API         |

Run the tests with `pip install pytest && pytest -q`.

## A quick taste of the API

```python
from rugby_sim.data import POOLS
from rugby_sim.models import Team, Lineup, Position
from rugby_sim.engine import MatchEngine

italy_pool = POOLS["ITA"]()  # real 2026-capped squad, cached after first pull
capuozzo = next(p for p in italy_pool if p.name == "Ange Capuozzo")
lineup = Lineup()
lineup.set_starter(Position.LEFT_WING, capuozzo)  # his real slot is fullback
# ... fill the other 14 positions, set lineup.captain, then:
team = Team(name="Italy (what if)", short_code="ITA", lineup=lineup)
# MatchEngine(team, some_other_team, seed=42).run()
```

For tournaments, awards, Legend mode, draft mode, historical squads, and
every other feature's full details, read the docstrings in the relevant
module - they're written to be the real documentation, not just comments.

## Calibration: does the engine pick real winners?

`scripts/calibrate_ratings.py` is a re-runnable sanity check, not a claim of
predictive accuracy: it auto-drafts all six 2024 Six Nations unions from
their real rugbydata stats, simulates every real fixture 11 times each, and
compares the modal winner against the real result. Current result:
**9/15 (60%) correct winners** - the misses are mostly narrow real
scorelines, exactly where a heuristic model should struggle. This number
exists to catch regressions when the model changes, not to be chased to
100% - real rugby has upsets on purpose.

Note that `calibrate_ratings.py`'s ratings and evaluation fixtures are both
drawn from the same 2024 season, so that 9/15 is a self-consistency check,
not an out-of-sample test. `scripts/calibrate_ratings_out_of_sample.py` is a
stricter, leakage-free version: it builds player ratings from the unions'
real **2023** stats only, then predicts the real **2024** Six Nations
results with those prior-season ratings - none of the 2024 outcomes being
predicted ever touch the 2023-derived ratings. That genuinely out-of-sample
run scores in the **7-8/15 (~47-53%) correct winners** range - re-running it
gives a slightly different pick each time, since the modal-vote simulation
is freshly seeded per run rather than pinned to one fixed result, and with
only 15 fixtures a single flipped pick moves the percentage by ~7 points,
so this is a range, not one precise number - lower either way than the
same-season check, which is expected: a roster's prior-year box-score stats
are a noisier proxy for its following year's real strength than that same
year's own stats are.

## Rating distribution sanity check

An external audit asked for a position-by-position breakdown of player
attribute ratings (mean/median/std-dev/outliers) to catch rating inflation
or compression, or arbitrary imbalances between positions, in the real
player pipeline (`rugby_sim/data/sources/attribute_mapping.py`'s heuristic
conversion from real rugbydata box-score stats). `scripts/analyze_rating_distributions.py`
answers this with real numbers: it pulls every Tier 1 union's real 2026
rugbydata pool (291 unique capped players across 12 unions), rates each
player at their own natural position (`Player.rating_at`), and groups by
position. Captured 2026-11-19:

| Position          | N  | Mean | Median | StdDev | Min  | Max  |
| ----------------- | -- | ---- | ------ | ------ | ---- | ---- |
| Loosehead Prop    | 26 | 70.2 | 70.2   | 4.8    | 58.2 | 79.2 |
| Hooker            | 21 | 71.3 | 72.7   | 4.9    | 63.7 | 81.7 |
| Tighthead Prop    | 19 | 73.2 | 73.0   | 6.4    | 63.0 | 84.8 |
| Lock (4)          | 38 | 67.5 | 67.7   | 8.6    | 50.1 | 83.7 |
| Blindside Flanker | 19 | 63.5 | 64.0   | 5.7    | 52.9 | 73.7 |
| Openside Flanker  | 21 | 65.4 | 67.3   | 7.5    | 52.5 | 76.5 |
| Number 8          | 16 | 62.6 | 62.3   | 5.7    | 51.6 | 71.7 |
| Scrum-half        | 20 | 66.4 | 67.0   | 10.7   | 47.2 | 84.2 |
| Fly-half          | 18 | 66.5 | 67.0   | 7.8    | 54.1 | 83.9 |
| Left Wing         | 19 | 69.1 | 70.2   | 9.8    | 46.2 | 83.4 |
| Inside Centre     | 22 | 65.5 | 66.4   | 8.8    | 48.8 | 79.6 |
| Outside Centre    | 17 | 67.4 | 68.1   | 6.1    | 56.8 | 77.3 |
| Right Wing        | 18 | 69.6 | 70.7   | 9.0    | 54.2 | 83.5 |
| Fullback          | 17 | 65.3 | 63.5   | 8.1    | 56.4 | 83.4 |

Overall: n=291, mean=67.5, median=68.1, stdev=8.0, min=46.2, max=84.8.

Honest read of these numbers: nothing here looks like a pipeline bug - every
position has a real, sensible spread (std-dev 4.8-10.7, not flat/collapsed
to one value) and every outlier top/bottom-3 name checked out as a real,
plausible pick (e.g. George Ford and Finn Russell near the top at fly-half;
Ben White near the top at scrum-half). There IS a mild, real **systematic
gap between the front row and everyone else**: props and hooker cluster
around 70-73 mean, while back row (Blindside/Openside/Number 8) and most
backs sit lower, around 63-67. This has a plausible rugby-shaped explanation
(front-row box-score proxies - scrummaging via `rucks_won`, tackle
success - compress into a tighter, higher band than the more spread-out
attacking stats used for backs and loose forwards) rather than looking
arbitrary, but it is a real, measurable imbalance worth knowing about if
attribute weights are ever retuned. Scrum-half has by far the widest spread
(std-dev 10.7) of any position, reflecting a genuinely bimodal real sample
(a few standout 80+ performers like Ben White and Tomos Williams alongside
several on the real depth-chart in the high-40s/low-50s), not a formula
defect. `tests/test_rating_distributions.py` pins down regression guards
(valid range, no suspiciously flat position, no individual rating wildly
outside its position's real observed spread) derived directly from this run
so a future formula change that actually breaks something gets caught.

## Where every attribute actually comes from

The same external audit also asked for a complete, inspectable map of the
real-data pipeline: which real rugbydata stat(s) feed each 1-100 attribute,
the exact formula, and an honest call on whether that attribute is
well-supported by multiple independent real signals or leaning on a single
weak proxy (or, for a few attributes, no real stat at all - a hardcoded
archetype value). `rugby_sim/data/sources/ATTRIBUTE_MAPPING.md` is that
reference, attribute by attribute, including the single-proxy cases beyond
the one the code already flags (`scrummaging`'s `rucks_won` stand-in).

## How a match is actually decided

The same audit also asked whether the engine's mechanics interact logically
or whether outcomes are primarily simplified random calculations.
`rugby_sim/engine/MATCH_ENGINE_MODEL.md` is the honest, per-outcome answer:
which attributes drive each drive's try/penalty/turnover/card probability,
the exact formulas, and a direct list of what isn't modeled (no phase-by-
phase tackle/ruck resolution, no drop-goal scoring despite the stat being
tracked, and more).

## Developing / verifying changes

If you're touching this repo later (including future-you), this is the
quick map of what to read first and what to run after, so a change doesn't
silently break something the test suite alone won't catch:

- **Run the suite**: `pytest -q` (see the badge above for the current
  count). This is the baseline check for any change, anywhere in the repo.
- **About to touch ratings, attribute formulas, or the data pipeline?**
  Read `rugby_sim/data/sources/ATTRIBUTE_MAPPING.md` first (what real stat
  feeds each attribute, and which ones are single-proxy/weak), then after
  your change re-run `python scripts/analyze_rating_distributions.py` (did
  the position-by-position spread stay sane - no collapsed std-dev, no
  position jumping wildly) and both calibration scripts:
  `python scripts/calibrate_ratings.py` (same-season sanity check) and
  `python scripts/calibrate_ratings_out_of_sample.py` (leakage-free,
  stricter check) - see "Calibration" and "Rating distribution sanity
  check" above for what healthy output looks like.
- **About to touch match resolution (drive outcomes, cards, injuries,
  stamina)?** Read `rugby_sim/engine/MATCH_ENGINE_MODEL.md` first - it's
  the honest per-outcome breakdown of what drives each probability and
  what isn't modeled at all, so a change doesn't contradict a mechanic
  that's already documented elsewhere.
- None of this is CI - it's just the lightweight, reproducible loop this
  project actually uses: read the relevant reference doc, make the change,
  run `pytest -q`, and re-run the calibration/distribution scripts if
  ratings or the engine were touched.

## Playing from your phone

The app only runs locally (`python -m rugby_sim.webapp`), so your phone
can't reach it directly unless you expose that local server to the
internet. The simplest free way is a
[Cloudflare Tunnel](https://github.com/cloudflare/cloudflared) - it opens a
temporary public HTTPS URL that forwards straight to your own PC, nothing
else:

```bash
# one-time install (Windows): winget install --id Cloudflare.cloudflared
# or download a binary for your OS from the cloudflared releases page

# terminal 1 - run the app as usual
python -m rugby_sim.webapp

# terminal 2 - open a tunnel to it
cloudflared tunnel --url http://localhost:5000
```

`cloudflared` prints a `https://random-words.trycloudflare.com` link -
open that on your phone (same link works from any network, not just your
home WiFi). The link only exists while both terminals stay running; close
either one and it stops working, and starting a new tunnel later gives you
a brand new random link (the free/quick tunnel mode doesn't support a
fixed address).

**What this does and doesn't expose**: Cloudflare's tunnel only forwards
requests to the one local port you pointed it at (`localhost:5000`) - nothing
else on your PC (files, other apps, other ports, your network) is reachable
through it. It's still a public link while it's running, though - anyone
who gets that exact URL can open your app and use it (it doesn't ask for a
password), so treat the link itself as something to only share with people
you actually want using it, and stop the tunnel (`Ctrl+C`) when you're
done. Mobile layout note: the UI is responsive down to phone widths
(~360px+), but it was built and most tested on desktop - if anything looks
cramped or a button's too small to tap, that's worth reporting back.

## Project history / build notes

Deeper narrative detail behind some of the features above - kept here so
the feature list stays skimmable while none of the underlying investigation
gets lost.

### Tournament mode: sidelining mechanics in detail

In "fresh squad every match" mode, every team gets a new auto-drafted
lineup before each fixture, and injuries/red cards sideline that player for
their team's *next* match - this applies the same way whether that team is
yours or fully AI-simulated, since there's no separate code path for
either. A fixed `teams=` lineup reused for the whole tournament respects
the same sidelining: a suspended/injured starter is swapped for the
best-fitting available bench player at that slot for the affected match(es)
(falling back to playing them anyway only if no eligible bench cover is
left), without permanently touching the original roster.

### Stamina: the four-input decay model

Decay rate is built from four small, documented inputs instead of just one:
their own `fitness` (the dominant term, as before), a position-workload
signal reused straight from `POSITION_PROFILES` (a prop/lock's profile
already leans on fitness/strength/scrummaging, so it decays faster than a
half-back or back three's), a small extra cost from `strength` (more
contact/carrying load) and from `pace` (more ground covered), and a modest
team-level matchup term - facing a stronger attacking opponent than your
own defense tires you a little faster, reusing the same attack/tackling
ratings the match engine already computes for its drive rolls. No new,
invented signal anywhere in that list - see `engine/match_engine.py`'s
`_decay_stamina`. This softens a player's rating late in a tight match and
feeds into why a tactical substitution happens. This "condition" (0-100) is
its own number, always shown separately from position fit (`natural_fit`)

- never folded into one combined figure - in the live lineup/bench views,
  even though the engine does multiply them together internally when it
  builds a team's actual rating. A single friendly or draft-mode match always
  starts everyone at full condition; in a tournament, a player picked into
  their team's last match's squad starts the next one short of full
  condition - this applies in BOTH "fresh squad every match" mode and a
  fixed lineup reused for the whole tournament, and the auto-draft AI (squads
  mode only) weighs it when picking who starts - see
  `engine/match_engine.py` and `tournament/availability.py` for the exact
  (frankly simple) heuristic.

### Injury and card reporting in detail

Every match screen lists who got hurt, for which team, at what minute, and
how severe it was (a small, named table of injury types - a "knock" through
a "serious injury" - each with its own chance and number of matches missed,
see `engine/match_engine.py`'s `INJURY_SEVERITY_TIERS`; this is a plausible
heuristic, not a medical model). A tournament's progress/report view
aggregates every injury across every match (auto-simmed or your own) into
its own collapsible section, linking back to the match it happened in, and
shows a LIVE "out for N more matches" for each one - a live lookup against
the tournament's current sidelining ledger, which only goes down as
further matches are actually played, not just the original injury's tier
length.

The same treatment applies to yellow/red cards: every match screen lists
who was carded, for which team, at what minute, and which colour, and a
tournament's progress/report view aggregates every card into its own
collapsible section with the same match-linking and a LIVE "out for N more
matches"/"available now" for anyone currently serving a red-card
suspension. The underlying rules (verified, not guessed): a yellow card is
a 10-minute sin-bin and carries NO suspension into a future match on its
own - only a real citation/disciplinary panel could do that, and
(consistent with this project's stance on not modeling injury tribunals)
that process isn't simulated here; a red card is off for the rest of that
match AND sits the player out for their team's next tournament match
(`tournament/availability.py`); and a second yellow card shown to the SAME
player in the SAME match is escalated to a red exactly as real World Rugby
law 19.2 requires, which the engine tracks per-player for the match's
duration (`engine/match_engine.py`'s `_issue_card`). This project does not
model the newer, still-trialled "20-minute red card" variant (a
like-for-like replacement after 20 minutes following a send-off) - every
red card here plays out the older, simpler way, the team simply finishes
the match a player short.

### Team rankings formula and snapshot

A World-Rugby-style points ranking (`tournament/rankings.py`) moves after
every match, real or simulated: rating gap + home advantage maps to an
expected result, the actual win/draw/loss swings both ratings zero-sum,
doubled for a Rugby World Cup match - this reimplements World Rugby's own
publicly documented formula (no third-party ranking API exposes a stable,
documented one to depend on instead). Seeded from a hand-entered,
clearly-dated **snapshot** of real World Rugby points (roughly
late-2025/2026) - a one-time starting point, not a live feed; ratings then
diverge from reality as "what if" matches are simulated. A tournament's
progress/final report gets its own "Team form / rankings" collapsible
section alongside the injury/card reports.

### Tier 2 rankings coverage: the Pacific Nations Cup and Rugby Europe Championship investigation

Tier 2 unions (Georgia, Romania, Spain, Portugal, Samoa, Tonga, USA,
Canada, Uruguay, Chile, Namibia) used to never appear in a simulated
Tournament/Season run, so their "Team form" rankings never moved off their
seed rating. The real Pacific Nations Cup (Fiji/Japan/Samoa/Tonga/
Canada/USA, Aug-Sep) is now a replayable `real_fixtures.py` tournament,
wired into both Tournament mode's real-fixture replay and Season mode's
block list - current (2025) AND historical (2023/2024) real seasons,
recovered the same team-set + month heuristic Six Nations already relies
on.

Re-investigated and now **added**: the Rugby Europe Championship. A first
pass (checking only the partial 2026 season) guessed the dataset's one
competition id conflated two separate real divisions, since the fixtures
split into two disjoint 4-team groups. A proper multi-season check
(2021-2026, connected-component analysis on the actual match graph) plus a
live web search disproved that: it's genuinely **one** real competition -
played as two 4-team pools (with real promotion/relegation between pools
year to year) feeding a crossover final weekend, confirmed against Rugby
Europe's own 2026 coverage.

A second pass then wrongly concluded Switzerland/Germany/Poland (3 of the 8
unions involved) had no usable roster source at all - re-checking live
found that wrong too: all three (plus Netherlands/Belgium/Russia, which a
prior report claimed worked but were never actually wired in) have a
standard, real, named `{{nat rs player}}` "Current squad" section on
Wikipedia; the earlier check's parser just didn't handle two page-specific
quirks (a plain `[[Name]]` wikilink instead of `{{sortname|First|Last}}` on
two of the pages, and a "==Squad==" heading instead of "==Current
squad==" on a third) - both are now handled by `wikipedia_squad.py`'s
parser.

Every one of the 8 unions in this competition now resolves a **real,
named, sourced roster** - no invented archetype players anywhere in this
block: Georgia/Portugal from rugbydata box scores (same as every other
Tier 1/2 union); Romania/Spain also have real rugbydata team ids but too
few capped names dataset-wide to field a full XV, so `build_union_pool` now
tops them up from their real Wikipedia squads too (a fix that also helps
any other union in the same situation, not just these two);
Switzerland/Germany/Poland/Netherlands/Belgium/Russia (no usable rugbydata
player-level data for any of the six - confirmed live, every one of their
matches has an empty `players` id list) resolve entirely from their real
Wikipedia squad listing, same `wikipedia_archetype`-on-no-match fallback
(clearly tagged, never a fabricated real name) every other
Wikipedia-sourced union already uses. Wired into both Tournament mode's
real-fixture replay and Season mode's block list (Jan-Mar, alongside Six
Nations); verified end to end for the 2023-2026 seasons (12 fixtures, 8
teams, each pool split per that year's real promotion/relegation).

### Season mode details

Pick one real union and one real calendar year, and play through every
real tournament that union actually played that year (whichever of Six
Nations / Rugby Championship / Autumn Nations Series / a Rugby World Cup
year it really appears in - detected from real fixture/squad data, never
fabricated), chained back to back (`tournament/season.py`). Injuries,
suspensions, short-rest condition, and the Team rankings above all carry
over BETWEEN tournaments within the season instead of resetting per
tournament. v1 plays every block fully auto-simmed (no interactive "my own
live match" pause yet within a season - that's real follow-up work, not
attempted in this pass), and the season roster is "every real player
capped for that union across the year's real tournaments", not every
eligible-but-uncapped player by default (a genuine data-source gap, called
out explicitly rather than faked) - see the uncapped/eligible players
write-up below for the opt-in follow-up that partially closes it.

### Uncapped/eligible players: why this is hard and how it's scoped

rugbydata has no nationality/eligibility field at all on club-match player
rows (only a `team` column, the club name), so "every real player capped
for a union" and "every real player *eligible* for a union" are genuinely
different, and the uncapped half can't be built from rugbydata alone. As a
scoped follow-up, `rugby_sim/data/sources/uncapped_pool.py` instead reads
domestic CLUB squad pages on Wikipedia (`{{RU squad player|NAT| Name|cap=y}}`

- confirmed live, same template, across every club checked) and takes
  "carries this union's nationality flag on a covered club's current squad
  listing, with no `cap=y` (bolded = capped international) marker" as an
  honest proxy for "eligible, never capped" - not a verified
  legal-eligibility check (residency/ancestry rules aren't visible from a
  squad list), and every such player's `notes` says so explicitly.

Covered today: **England** (Leicester Tigers, Saracens) and **France**
(Stade Toulousain, Racing 92) only - two Tier 1 unions, two top-flight
clubs each, deliberately small rather than guessed-at for the other ~18
unions. Real-stat cross-reference rate against rugbydata's player registry
is high for these clubs (34/37 for the England sample, i.e. most of these
"uncapped" players already have real rugbydata career stats from club
rugby - only a handful fall back to a generic position-archetype rating).
Toggle it on `/api/season/start` with `include_uncapped: true`, or the
"Include uncapped/eligible players (ENG, FRA only)" checkbox in Season
mode's web UI - it's returned as a clearly separate `uncapped_pool` list
(own `data_source` of `uncapped_wikipedia`/`uncapped_wikipedia_archetype`),
never silently merged into the main capped roster.

## License

[MIT](LICENSE).
