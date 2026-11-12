# what-if-rugby-edition

A national-team rugby union "what if" simulator: what happens if you put a
player in a position they never actually played (Jonah Lomu at fullback,
a hooker at tighthead, etc.)? Build your own squads and simulate the match.

## Layout

- `rugby_sim/models/` - `Attributes`, `Position` (+ per-position attribute
  profiles), `Player` (computes an out-of-position "fit" rating), `Team`/
  `Lineup` (23-man squad builder).
- `rugby_sim/engine/` - `MatchEngine`, a phase-by-phase 80-minute simulator
  driven entirely by the lineup's computed ratings (tries, conversions,
  penalties, cards, turnovers, territory, injuries, substitutions), plus
  `CommentaryEvent` for the minute-by-minute log.
- `rugby_sim/data/sample_players.py` - a small hand-made seed roster for
  quick experiments (no network needed).
- `rugby_sim/data/legends.py` - Hall of Fame "legend" players, deliberately
  **not** part of `POOLS` (never show up in "by nation" drafting or a real
  tournament's team list, only when you build a free/custom-pool team via
  the interactive CLI's `LEG` option). Two tiers: `CURATED_LEGENDS` (~30
  hand-tuned profiles - Jonah Lomu, Richie McCaw, Dan Carter, Jonny
  Wilkinson, Serge Blanco, David Campese, ...) plus `get_all_legends()`,
  which adds every other resolvable member of Wikipedia's "Category:World
  Rugby Hall of Fame inductees" (~190 total) - around 100 players in all.
  See "Legend mode" below.
- `rugby_sim/data/sources/` - the real player-data pipeline: pulls 2026
  international box-score stats from the `seanyboi/rugbydata` GitHub
  dataset (free, no API key) and converts them into `Attributes` via a
  documented heuristic mapping (`attribute_mapping.py`). Raw pulls are
  disk-cached under `rugby_sim/data/cache/` (gitignored) so the simulator
  never needs the network once a union has been pulled.
- `rugby_sim/data/national_teams/` - `POOLS["ENG"]()`, `POOLS["NZL"]()`, ...
  one lazy-loaded **player pool** per union - 12 Tier 1 unions (England,
  France, Ireland, Scotland, Wales, Italy, New Zealand, Australia, South
  Africa, Argentina, Japan, Fiji) plus 11 Tier 2 unions relevant to the
  2027 Rugby World Cup picture (Georgia, Romania, Spain, Portugal, Samoa,
  Tonga, USA, Canada, Uruguay, Chile, Namibia), plus `POOLS["BAR"]()` for
  the Barbarians (invitational, not a union, entered manually since it
  isn't in the dataset at all). Pools are flat lists, not preset XVs - you
  still draft the lineup yourself via `Lineup.set_starter(position, player)`.
- `rugby_sim/tournament/` - `Tournament` (real-fixture replay via
  `real_fixtures.py`, the 2027 World Cup's real draw + official
  Round-of-16 pairing via `world_cup_2027.py`, or synthetic round-robin/
  pool+knockout via `fixtures.py`), `Standings` (bonus-point table),
  `CustomTournament` (thin builder for your own format).
- `rugby_sim/data/squad_repository.py` - `save_team`/`load_team`: a drafted
  squad (full lineup + bench + captain + every player's attributes)
  round-trips to a plain `.json` file - wired into both the CLI and web UI.
- `rugby_sim/cli.py` - runnable hardcoded demo (`python -m rugby_sim.cli`).
- `rugby_sim/interactive_cli.py` - **prompt-driven terminal builder**
  (`python -m rugby_sim.interactive_cli`): no code required. For each team,
  choose **by nation** (pick a union/Barbarians - its whole real pool loads
  automatically and becomes the team) or **free pool** (mix any pool(s)/
  season(s) yourself for a fantasy roster - this is also the only place
  `LEG` (the Hall of Fame legends) is selectable). Either way, draft all 15
  positions and a captain by number, then run a single match, a real
  tournament's actual fixture list, the 2027 Rugby World Cup's real draw,
  or a custom round-robin/pool+knockout.
- `rugby_sim/webapp.py` + `rugby_sim/web/` - **clickable web UI**
  (`python -m rugby_sim.webapp`, then open `http://127.0.0.1:5000`): the
  same team-building/match-simulation flow as the interactive CLI, but
  click-driven in a browser - pick a pool, click a position, click a
  player - instead of typing numbers at prompts - plus a tournament-mode
  section (real-fixture replay, the 2027 World Cup, custom formats) and
  save/load-to-file. A small Flask JSON API wraps the exact same
  `POOLS`/`get_all_legends`/`MatchEngine`/`Tournament` calls; no rugby
  logic is reimplemented in JavaScript.
- `tests/` - sanity, data-pipeline, tournament, substitution, player-stats,
  squad-repository, auto-draft, port-management, and web-API tests
  (48 total).

## How to run

Requires Python 3.10+. From the project root (`what-if-rugby-edition/`):

**1. (optional but recommended) create a virtual environment**

```powershell
# PowerShell / Windows
python -m venv .venv
.venv\Scripts\activate
```

```bash
# bash / macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

**2. install dependencies**

```bash
pip install -r requirements.txt
```

**3a. run the interactive builder** (no code - just answer prompts: pick a
team's player pool(s), draft all 15 positions + captain, pick an opponent
the same way, then a single match / real tournament / custom tournament):

```bash
python -m rugby_sim.interactive_cli
```

The first time you pull a union's pool it hits the network once and
disk-caches the result (`rugby_sim/data/cache/`, gitignored) - later runs
for that union/season are instant and work offline. You are never limited
to one union's own players for a "team" - add as many pools as you like to
the same side if you want a fantasy mix.

**3b. or open the clickable web UI** (pick pools and players by clicking
instead of typing):

```bash
python -m rugby_sim.webapp
```

Then open `http://127.0.0.1:5000` in a browser. Local-only, single-user,
no login - closing the terminal stops it.

**3c. or run the hardcoded demo match** (standard England XV vs. a "what if"
England XV with Jonah Lomu at fullback instead of the wing - useful as a
scripting reference, see `rugby_sim/cli.py`):

```bash
python -m rugby_sim.cli
```

Both print the lineups (including each player's out-of-position fit rating)
followed by a full minute-by-minute commentary log and final score.
Re-run for a different random result (unseeded); pass a fixed `seed=` to
`MatchEngine(...)` for a reproducible one.

**4. run the tests**

```bash
pip install pytest   # not in requirements.txt yet - only needed to run tests
pytest -q
```

(If you'd rather not install pytest, every test file can also be run
directly, e.g. `python -c "import tests.test_basic as t; t.test_match_runs_and_produces_a_result()"`.)

**5. try your own "what if" lineup**, drafting from a real 2026-capped
national player pool (first call per union hits the network once and
disk-caches the result under `rugby_sim/data/cache/` - later calls are
instant and work offline):

```python
from rugby_sim.data import POOLS
from rugby_sim.models import Team, Lineup, Position
from rugby_sim.engine import MatchEngine

italy_pool = POOLS["ITA"]()  # first call pulls + caches; later calls are instant
capuozzo = next(p for p in italy_pool if p.name == "Ange Capuozzo")
lineup = Lineup()
lineup.set_starter(Position.LEFT_WING, capuozzo)  # his real 2026 slot is fullback
# ... set_starter for the other 14 positions, then lineup.captain = <a Player>

team = Team(name="Italy (what if)", short_code="ITA", lineup=lineup)
# simulate: MatchEngine(team, some_other_team, seed=42).run()
```

`lineup.validate()` tells you what's still missing (empty slots, no
captain, a player named twice) before you try to simulate a match -
`MatchEngine.run()` raises if either lineup isn't complete.

## Tournaments

`rugby_sim/tournament/` can replay either a **real** competition's actual
fixture list, or a **synthetic** one you define yourself:

```python
from rugby_sim.data import POOLS
from rugby_sim.models import Team, Lineup, Position
from rugby_sim.tournament import Tournament

# ... draft a Lineup for each Six Nations side from its real pool, e.g.:
# POOLS["ENG"](season="2026"), POOLS["FRA"](season="2026"), ...
teams = {"England": team_eng, "France": team_fra, "Ireland": team_ire,
         "Scotland": team_sco, "Wales": team_wal, "Italy": team_ita}

report = Tournament(teams).run_real("six_nations", season="2026")
report.print_report()  # every real fixture, simulated, + the final table
```

- `Tournament.run_real(tournament_key, season)` - loads the **actual**
  fixture list (who played whom, in order) for a named competition
  (`"six_nations"`, `"rugby_championship"`, `"autumn_nations_series"`) and
  a given `season` (the dataset covers 2022-2026), then simulates each one
  with your lineups and produces the real bonus-point table.
  `POOLS[code](season=...)` takes the same `season` so you can pair e.g.
  2023 fixtures with 2023-capped players for a historical replay. There's
  no `"rugby_world_cup"` key here - a real-fixture replay can't reliably
  tell a World Cup match apart from a Rugby Championship one for this
  dataset (team-set/month overlap - a past entry here was removed for
  exactly this reason); use `run_world_cup_2027` (the real upcoming draw)
  or `run_historical_world_cup` (every real past edition, 1995-2023, real
  squads) instead - see below.
- `Tournament.run_round_robin(...)` / `.run_pool_and_knockout(...)`, or the
  `CustomTournament(teams, format=...)` wrapper - synthetic fixtures for a
  tournament that never happened, generated by `rugby_sim/tournament/fixtures.py`.
- Real-fixture recovery is a documented heuristic, not a guaranteed-exact
  replica: the dataset tags most 2026 Six Nations matches with a generic
  "International Test Match" id rather than the dedicated Six Nations one,
  so fixtures are matched by team-set + month window instead - see the
  docstring in `rugby_sim/tournament/real_fixtures.py`.

### 2027 Rugby World Cup (real draw, no fixtures exist yet)

The tournament hasn't been played (kicks off 1 Oct 2027), so there's no
fixture list in `rugbydata` to replay - but the real pool draw **has**
happened (3 Dec 2025, Sydney), so that part isn't guessed:

```
Pool A: New Zealand, Australia, Chile, Hong Kong
Pool B: South Africa, Italy, Georgia, Romania
Pool C: Argentina, Fiji, Spain, Canada
Pool D: Ireland, Scotland, Uruguay, Portugal
Pool E: France, Japan, USA, Samoa
Pool F: England, Wales, Tonga, Zimbabwe
```

```python
from rugby_sim.tournament import ALL_TEAMS_2027, CODE_BY_NATION, Tournament

# ... draft a Team for all 24 sides (POOLS[CODE_BY_NATION[name]]), then:
report = Tournament(teams).run_world_cup_2027(fixture_mode="specific", seed=42)
report.print_report()  # 6 pools -> top 2 + best 4 thirds -> 16-team knockout
```

Since pool *play itself* hasn't happened, `fixture_mode` lets you choose:
`"specific"` plays each pool in the drawn order; `"random"` shuffles each
pool's match order first (same teams, same pools, different order). The
interactive CLI and web UI both ask this up front when you pick the 2027
World Cup. Knockout qualification (top 2 per pool + best 4 third-placed)
is the confirmed real format; the exact Round-of-16 pairing rule hadn't
been published by World Rugby as of the draw, so a reasonable seeded
bracket is used instead of an official one - see
`rugby_sim/tournament/world_cup_2027.py`. Hong Kong and Zimbabwe (needed
for Pools A and F) aren't in rugbydata at all, so their pools are built
entirely from Wikipedia's "Current squad" pipeline.

A custom tournament (`CustomTournament`) now asks the same "specific vs.
random" question for its own team order, before generating fixtures.

### Historical Rugby World Cups (1995-2023, professional era)

Every Rugby World Cup since rugby union turned professional is playable
with its **real pool draw and real squads**, not a guess:

```python
from rugby_sim.data.sources.historical_rwc import get_rwc_year_data
from rugby_sim.tournament import Tournament

pools, squads = get_rwc_year_data(2003)  # pools: {"Pool A": [...], ...}
                                          # squads: {team_name: [Player, ...]}
# ... draft/auto-draft a Team per squad, then:
report = Tournament(teams).run_historical_world_cup(2003, seed=7)
report.print_report()  # same real pool groupings England actually won in
```

Available years: 1995, 1999, 2003, 2007, 2011, 2015, 2019, 2023 (every
edition before 2027's new format). Both the pool draw and every squad are
read straight off that edition's own `"<year> Rugby World Cup squads"`
Wikipedia page - not hand-entered - using the exact same
`{{nat rs player|pos=...|name=...|caps=...}}` template the current-season
Wikipedia pipeline already parses, just organized as `Pool` -> `Team`
subsections for ~20 teams on one page. Pre-2027 knockout format was always
plain top-2-per-pool -> straight to quarter-finals (no third-place
wildcards), so this reuses the same pool+knockout machinery, not the 2027
permutation table.

**Ratings for this era are honestly archetype-based, not scouted**:
`rugbydata` (the real box-score source everything else uses) only covers
2018-2026, nowhere near 1995-2017. Every historical player gets the same
treatment "Legend mode" uses - a position-archetype baseline, scaled by
that union's `UNION_STRENGTH` - *unless* their career happens to overlap
rugbydata's coverage (real for a 2019/2023 squad member whose name
cross-references into real stats), in which case real stats are used
instead. `data_source` is tagged `"historical_wikipedia"` (real stats
found) or `"historical_archetype"` (position estimate) so this is always
visible, not papered over.

Both the interactive CLI (`Historical Rugby World Cup`, under "Real
tournament") and the web UI (`Historical Rugby World Cup (1995-2023)`
tournament-mode button) support this: pick a year, see the real pools, then
auto-draft or draft-yourself each participant exactly like the 2027 World
Cup flow.

**1999's unique format is reproduced, not flattened into the generic
rule**: every other edition is a plain top-2-per-pool, but 1999 was 5
pools of 4, where only the 5 pool *winners* went straight to the
quarter-finals - the 5 runners-up plus the single best third-placed team
played a quarter-final **play-off** round (3 knockout matches) for the
remaining 3 quarter-final spots. `run_historical_world_cup` detects
`year == 1999` and runs that extra round automatically; every other year
is unaffected.

### Historical Six Nations Championship (2009-2021)

Same approach, for the Six Nations: real squads for each of the 6 teams,
read off that edition's own `"<year> Six Nations Championship squads"`
Wikipedia page (verified live for 2009 through 2021 - earlier pages list
players with no position at all, which can't be drafted). 2022 onward is
already covered by the regular real-fixture pipeline (`run_real`, real
rugbydata stats), so this is specifically the pre-rugbydata gap.

```python
from rugby_sim.data.sources.historical_six_nations import get_six_nations_year_data
from rugby_sim.tournament import Tournament

squads = get_six_nations_year_data(2012)  # {"England": [...], "France": [...], ...}
report = Tournament(teams).run_historical_six_nations(2012, seed=3)
report.print_report()  # 15-match round-robin + bonus-point table
```

Honest caveat: the squads page has no fixture list, so match **order** is
a synthetic round-robin, not the real historical sequence (everyone plays
everyone once either way, so the final table's shape is correct - who
played whom isn't in the real order). Ratings follow the same
archetype/union-strength convention as the historical World Cups.

### Historical squads in a single friendly or a custom tournament

Any historical World Cup or Six Nations squad can also be pulled into a
normal single match or a custom tournament - not just the dedicated
historical-tournament modes above. In the interactive CLI's free-pool
drafting, add the `HIST` pool code (alongside a union code or `LEG`) to
pick a competition, year and team and mix that exact historical squad
into whatever team you're building. In the web UI, every `TeamBuilder`
panel (single match, or a custom tournament's "Draft yourself" team) has
a "Historical squad" button doing the same thing - pick competition, year,
team, add, repeat to mix several historical squads into one fantasy
roster if you want to.

**Out of scope for now**: the pre-1995 amateur era, by design (see the
Roadmap section at the bottom for the Tri Nations/Rugby Championship gap).

### Tournament awards: team/player stats, Team of the Tournament, Player of the Tournament

Every tournament mode (real-fixture replay, both World Cups, both
historical modes, custom tournaments) now computes, at the end of the
whole thing (`rugby_sim/tournament/tournament_stats.py`):

- **Team tournament stats** - every `TeamMatchStats` field (tries, pens,
  drop goals, turnovers, errors, cards, injuries, substitutions), summed
  across every match that team played, plus an average territory %. Same
  fields as a single match's box score, just totalled up.
- **Tournament top scorers** - every player's tries/conversions/penalties/
  points, summed across every match they started (same convention as a
  single match's "Top scorers" - only players who actually scored show up
  here, same as the per-match report).
- **Team of the Tournament** - the best average-performing player at each
  of the 15 starting slots, across every team. Each player's per-match
  "performance score" is their real `rating_at(position)` for the slot
  they started in, plus a bonus for anything they personally scored that
  match - this is a documented heuristic (the engine only tracks who
  scored, not tackles/metres/etc. per player), chosen specifically so a
  prop or lock who never scores still ranks on their actual quality,
  instead of a pure-points ranking that would never pick a forward at all.
  No player is picked twice.
- **Player of the Tournament** - the single highest average-performance
  player from that same pool, with one restriction: if the tournament has
  a real knockout stage that deep, they must have started at least one
  semi-final or final. A tournament with no bracket at all (a plain
  round-robin, e.g. Six Nations or a real-fixture replay) has no such
  restriction - there's no semi-final to have played in.

`Tournament*.print_report()` prints all four sections; the web UI shows
them under a tournament's results (with each team/player's real crest next
to its name, see "Team logos" below).

## Legend mode

A dedicated roster of real Hall of Fame players, for building an all-time
XV or dropping a few legends into a fantasy side - kept out of `POOLS`
entirely so they never contaminate a real "by nation" draft:

```python
from rugby_sim.data.legends import CURATED_LEGENDS, get_all_legends

CURATED_LEGENDS        # ~30 hand-tuned profiles (Lomu, McCaw, Carter, ...)
get_all_legends()      # ~100 total - adds every other resolvable member of
                        # Wikipedia's World Rugby Hall of Fame category
```

- Every name is a genuine inductee - checked against Wikipedia's
  "Category:World Rugby Hall of Fame inductees" (190 members) before being
  included, never invented.
- `CURATED_LEGENDS` entries have a hand-tuned `Attributes` profile
  (`data_source="manual"`). `get_all_legends()`'s extra ~70 have their
  **position, nation and era parsed from that person's own Wikipedia
  infobox** (`rugby_sim/data/sources/hof_scraper.py`) - real - but a
  generic position-archetype rating, since rugbydata's box scores don't
  reach most of these careers (`data_source="hof_archetype"`). A curated
  entry always wins on a name collision.
- Not every one of the 190 category members resolves: some are teams,
  tours, clubs or non-playing administrators/commentators (filtered out
  automatically - no playing infobox), and a few historical bios don't have
  a cleanly parseable position or nation. ~100 real, usable legends is the
  actual yield, not a shortfall to "fix" by guessing the rest.
- In the interactive CLI, add `LEG` in free-pool mode to pull in the full
  `get_all_legends()` roster (first call is network-heavy - ~190 page
  fetches - but disk-cached, so it's instant afterwards).

## How a drive's outcome and a team rating are actually decided

**Decisions (try / penalty / card / turnover / nothing):** each drive is
one weighted dice roll across a fixed menu of outcomes - try, penalty
conceded by the defense (at the breakdown *or* the scrum, tracked
separately), a card, a penalty conceded by the attack, a lineout turnover,
a handling error, or no outcome - not an independent simulation of every
ruck/maul/scrum/lineout. Each outcome's probability is a baseline plus a
swing term from the *edge* between the two teams' relevant ratings (e.g.
the scrum-penalty chance swings with `scrum_atk - scrum_def`, the
try chance with `attack_rating - tackling_def`) - see
`MatchEngine._resolve_drive`. "Scrum penalty" and "breakdown penalty" are
genuinely driven by different inputs (scrum power vs team discipline), but
both still resolve through that same one per-drive roll.

**How a fit score becomes a team rating:** `Player.rating_at(position)` is
one player's 0-100 fit at one slot (position-profile-weighted attributes,
penalized if it's not their natural position - the whole "what if" lever).
`Player.sub_ratings` turns that into per-category numbers (scrum/lineout/
tackling/attack/kicking/goal_kicking/handling/aerial, each scaled by
`fit/100`; `discipline` is deliberately **not** fit-scaled, since
indiscipline isn't really position-dependent). A *team* rating for a
category is then the average of that category **only across the starters
actually involved in it** (`CATEGORY_POSITION_GROUPS` in
`models/position.py`): scrum = front row + locks; lineout = locks + back
row; lineout throwing = the hooker alone; aerial = back three + locks;
tactical kicking = scrum-half/fly-half/fullback. Categories not in that
map (tackling, attack, handling, discipline) are deliberately whole-team
averages - those really are universal involvements. Before this scoping
existed, every category averaged all 15 starters, which diluted a strong
front row's scrum rating with two wingers who barely scrummage, and gave
`lineout_jumping`/`lineout_throwing` no real effect on a match at all - a
lineout-turnover event now exists specifically so those two attributes
matter (see the event log: "`<team>` win the lineout - overthrow/steal
from `<opponent>`").

## Injuries & substitutions

`MatchEngine` now actually uses `Lineup.bench` (up to 8 players): every
drive carries a small chance of an injury to a random on-field player, and
in a 50th-75th minute window, a smaller chance of a fatigue-driven tactical
substitution. Either brings on whichever bench player fits that position
best (never more than the real 8-sub cap per team); if an injury happens
with no bench player left, the team plays the rest of the match a man
down (same rating penalty as a red card) instead of leaving an empty slot.
`TeamMatchStats` now tracks `injuries`/`substitutions`, and both the
commentary log and `print_report()`/web UI show them. None of this touches
your original `Lineup` - `MatchEngine` works from a per-match copy, so the
same `Team` can be reused for another simulation unaffected by what
happened in this one.

### Manual substitutions - pause a match, swap a player, resume

Beyond the automatic injury/tactical-sub rolls above, `MatchEngine` can
now be paused mid-match for a manual substitution, then resumed:

```python
engine = MatchEngine(home, away, seed=1)
engine.run_interactive([20, 40, 60, 70], on_checkpoint)  # pauses at each minute
# inside on_checkpoint(engine, minute):
#   engine.active_lineup(team)   # who's on, by position
#   engine.bench_for(team)       # who's left on the bench
#   engine.apply_substitution(team, position, bench_player=specific_player)
```

- `start()`/`advance_to(minute)`/`finish()` are the building blocks (play
  to a checkpoint, do something, continue); `run()` is unchanged - just
  `start()` then `finish()` back to back, so every existing single-shot
  caller keeps working exactly as before.
- `apply_substitution(team, position, bench_player=...)` now lets you pick
  **exactly who** comes on (it used to only auto-pick the best-fitting
  bench player) - omit `bench_player` to keep that old auto behavior.
- The interactive CLI asks up front, for a single match: "pause the match
  partway through to make substitutions yourself?" - if yes, it pauses at
  minutes 20/40/60/70 (`SUB_CHECKPOINTS`), shows the score and both
  benches, and lets you make as many subs as you want at each stop before
  resuming.
- The web UI has the same thing as a checkbox next to "Run match" -
  "Pause mid-match to make substitutions". A paused match shows both
  lineups with a "Substitute..." button per position; picking a bench
  player applies it immediately, and "Resume play" advances to the next
  checkpoint (or finishes and shows the full report, at the last one).

### Interactive tournaments - play your own matches, auto-sim the rest

Every tournament mode (real-fixture replay, both World Cups, both
historical modes, custom round-robin/pool+knockout - including the 1999
World Cup's own 5-pool + play-off format) can now be run interactively:
pick which team is yours, and only *your* matches pause for the manual
pause/substitute flow above; every other fixture auto-sims exactly as
before, invisibly, on the server.

```python
# webapp.py: POST /api/tournament/start with the usual /api/tournament/run
# body (type, team_ids/squad_player_ids, seed, ...) plus "my_team": "England"
#   -> {"status": "paused", "home": ..., "away": ..., "live_match": {...}}
#      (live_match is the same shape /api/match/live/start returns - drive
#       it with the existing /api/match/live/<id>/continue and
#       .../substitute endpoints)
#   -> once that live match is finished, POST /api/tournament/<id>/resume
#      to feed its result back into the standings/bracket and auto-advance
#      again until the next my_team fixture pauses it, or it's finished:
#      {"status": "finished", "report": {...}}   # same report /run returns
```

- Implemented with `Tournament`/`CustomTournament`'s new `my_team`/
  `pause_hook` constructor args (`rugby_sim/tournament/tournament.py`) - a
  fixture not involving `my_team` is untouched, one that does calls
  `pause_hook(...)` instead of simulating straight through, which the web
  layer uses to park the tournament (running on a background thread) on a
  normal pausable `MatchEngine` live match and block until it's finished.
  No tournament format had to be rewritten into a step-by-step generator to
  get this - the existing `run_real`/`run_world_cup_2027`/
  `run_historical_world_cup`/`_run_1999_world_cup`/etc. methods are
  unchanged other than reading `my_team`/`pause_hook` from `self`.
- `/api/tournament/run` (the original, fully-automatic endpoint) is
  unchanged - interactive play is opt-in via the new `/start`/`<id>/resume`
  endpoints, not a breaking change to the old one.
- The web UI's tournament panel has a "Which team is mine?" dropdown
  (populated from whichever teams you've already set up for that
  tournament) next to the existing "Run tournament" button; a "Play my
  matches" button drives the new interactive flow, reusing the exact same
  live-match rendering the single-friendly live match uses, then falls
  back to the normal tournament report view once the whole thing's done.

## Tournament squads: a fresh lineup every match (not one fixed XV)

By default, a team you draft for a tournament is one fixed `Lineup`,
reused unchanged for every match it plays - fine for a quick "what if",
but not how a real tournament squad works (a 30+ player squad, a
different starting XV most matches, injuries/suspensions forcing
changes). `Tournament`/`CustomTournament` now support a second mode for
exactly this:

```python
from rugby_sim.tournament import Tournament

squads = {"England": POOLS["ENG"](season="2026"), "France": POOLS["FRA"](season="2026")}
report = Tournament(squads=squads).run_round_robin(seed=1)
```

- Pass a team's full player **pool** via `squads={name: [Player, ...]}`
  instead of a drafted `Team` via `teams={name: Team(...)}` (both dicts
  can be used together in the same tournament - some teams fixed, others
  fresh-every-match). A name must be in exactly one of the two.
- For a `squads` team, `Tournament` auto-drafts a brand new best-fit XV
  (`auto_draft_team`, greedy best-fit - same algorithm as everywhere else
  in this project) from that pool **before every single match**.
- **Injuries and red cards now actually matter past the match they
  happened in** (`rugby_sim/tournament/availability.py`): a player hurt or
  sent off in one match sits out their team's *next* match entirely (not
  selectable for that next auto-draft), then is available again after
  that - a simplified, documented heuristic (1 match out either way, not
  a medical/disciplinary model), not something a fixed-lineup tournament
  could ever reflect, since it's the same 15 names regardless of what
  happened last match.
- Both the interactive CLI and the web UI ask this up front for every
  tournament-building flow: "Fixed lineup" (original behavior) or "Fresh
  squad every match". In the web UI, a squads-mode team panel just picks
  a union+season (or Legends) to source the pool from - no lineup
  drafting step, since a lineup is drafted for you before each match.

## Web UI

`python -m rugby_sim.webapp`, then open `http://127.0.0.1:5000` (it always
uses port 5000 - see "Always port 5000" below). A thin Flask JSON API
(`rugby_sim/webapp.py`) plus a static click-driven frontend
(`rugby_sim/web/`) - pick a pool, click a position to see ranked
candidates, click one to assign, pick a captain and optional bench, save,
then run the match and read the live commentary/stats/Player of the Match.

**Tournament mode** is in the same page, below the single-match builder.
Pick a format (real-fixture replay / the 2027 World Cup / a custom
tournament), and for **each team you get a choice**: "Auto-draft
(recommended)" instantly builds that team's real pool's best XV (greedy
best-fit, see `auto_draft.py`) with one click, or "Draft yourself" expands
the normal position-by-position builder for that one team. You don't have
to draft all 24 World Cup teams to play it - draft the one(s) you actually
care about and auto-draft the rest. A custom tournament asks "total teams"
and "how many will you draft yourself" up front, then auto-fills the
remainder from a fixed priority order of mostly strong unions
(`STRONG_UNIONS_FILL_ORDER` in `webapp.py`) - not literally "the best",
just a sensible default so you're not stuck naming every filler team.

**Every match played in a tournament is clickable** - every scoreline in
the group tables, the bracket, and the "All results" list is a button;
clicking it fetches that exact match's full minute-by-minute commentary,
box score, and Player of the Match (the same detailed report a single
friendly gets), not just the final score.

### Team logos

Every union/Barbarians selector in the web UI (by-nation/free-pool
drafting, the historical-squad picker, custom-tournament auto-drafted
team panels) shows that team's real crest - a transparent-background PNG,
pulled straight from that national team's own Wikipedia infobox `Badge`
field via `rugby_sim/data/sources/team_logos.py`, not invented or a
generic placeholder. An SVG badge is rasterized to PNG by MediaWiki's own
thumbnail service, which preserves the source's alpha channel (no
background fill added on our side).

- Logos are pre-fetched and disk-cached (`rugby_sim/web/logos/<code>.png`,
  served statically) rather than fetched live per page load - run
  `python -m rugby_sim.data.sources.team_logos` once to (re-)populate the
  cache for every known union; the web UI's `/api/logos` only reports
  what's already cached.
- **Historical-year squads show that union's *current* crest**, not a
  logo from that specific year - sourcing an exact historical-year badge
  for 20+ teams across 8 World Cup editions isn't something Wikipedia's
  infobox gives for free, and isn't verifiable at this scale. Most
  federation logos have been stable for decades anyway; this is a
  documented simplification, not a silent one.
- One known gap: Tonga's own Wikipedia infobox has no `Badge` field at
  all at time of writing, so no logo shows for Tonga - not a bug, there's
  simply nothing to pull.
- No official World Rugby Hall of Fame logo could be found on Wikipedia
  (the Hall of Fame's own article has no infobox/logo at all) - rather
  than fabricate one and risk misrepresenting an organization's real
  branding, Legend mode shows no crest instead.

### Always port 5000

`python -m rugby_sim.webapp` always serves on port 5000. If something
(almost always a stale run of this same server from before a code change)
is already listening there, it's stopped automatically first - Windows
only (`netstat`/`taskkill`); on other platforms you may need to close the
old one yourself if binding fails. Override the port with the
`WEBAPP_PORT` environment variable if you deliberately want a different
one (e.g. to run two instances side by side).

## Data pipeline notes

- Tier 1 unions are pulled live from rugbydata's 2026 test-match box scores.
- **Tier 2 unions all get a real, full-size 2026 squad** via
  `build_union_pool_2026` (`rugby_sim/data/sources/pool_builder.py`), which
  merges two sources:
  1. real rugbydata 2026 box-score stats, for whichever players have them
     (Georgia, Romania, Portugal have some real 2026 rows; most others
     currently don't);
  2. that union's actual 2026 "Current squad" as listed on its Wikipedia
     page (`rugby_sim/data/sources/wikipedia_squad.py`), for every player
     rugbydata doesn't cover. Wikipedia gives a name and position but no
     stats, so each scraped name is cross-referenced against rugbydata's
     *global* player registry (independent of nation/season - someone's
     club-rugby stats count too); if a real match is found, their
     attributes are stats-derived like everywhere else
     (`data_source="wikipedia"`); if not, they get a generic
     position-archetype rating, clearly **not** a scouted number
     (`data_source="wikipedia_archetype"`).
     A small manually-entered list (Spain, Namibia, Fiji) remains only as a
     last-resort safety net if this whole pipeline ever comes back empty.
     Hong Kong and Zimbabwe (added for the 2027 World Cup draw) have no
     rugbydata team_id at all, so they skip the merge and are built purely
     from their Wikipedia "Current squad" section.
- **Cross-union calibration** - two deliberate adjustments so match results
  stay realistic instead of treating every union as interchangeable:
  1. Percentile scaling (see "How a drive's outcome..." further down) now
     ranks a player against a **cross-union reference pool** built from
     every union's real rugbydata stats at that position
     (`pool_builder._global_reference_peer_proxies`), not just that one
     union's own (sometimes tiny, sometimes elite) pool. Ranking only
     within a union's own roster has no absolute calibration at all - the
     weakest player in a stacked All Blacks pool would get crushed toward
     the bottom of the scale even though they're still a fine
     international, while a mediocre player in a small union's pool could
     rank artificially high just for being that pool's best.
  2. `attribute_mapping.UNION_STRENGTH` - a rough, real-world-informed
     competitiveness multiplier per union (Tier 1 = 1.0, unchanged; weaker
     unions pulled toward 50/replacement-level in proportion to how far
     below Tier 1 they generally sit), applied as a final pass to every
     player regardless of data source. Before this, a flat archetype
     baseline (for Wikipedia-only entries with no findable rugbydata
     stats) made minnow unions look deceptively uniform/competitive -
     New Zealand could lose to Chile. Neither adjustment is a ranking
     claim; they're tuned to keep genuine mismatches mismatched while
     still letting a strong Tier 2 side (Fiji, Georgia, Samoa) upset a
     Tier 1 one occasionally, as happens in reality.
- Attribute values are a heuristic approximation (the dataset has no raw
  pace/strength numbers), not a scouted rating - see the docstring in
  `attribute_mapping.py` for exactly which proxies are used.
- The dataset doesn't distinguish Lock 4 vs Lock 5, or which wing/centre
  slot a player featured in, so those pool entries share one representative
  position - draft them into either slot freely.
- The same real person occasionally gets two different player_ids in the
  dataset (confirmed for Wales's Ellis Mee); `build_union_pool` dedupes by
  name, keeping whichever id has more caps, so a lineup never ends up with
  the same player in two slots.

## Roadmap
