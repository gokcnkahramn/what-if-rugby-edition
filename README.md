# what-if-rugby-edition

A national-team rugby union "what if" simulator: what happens if you put a
player in a position they never actually played (Jonah Lomu at fullback,
a hooker at tighthead, etc.)? Build your own squads and simulate the match.

## Layout

- `rugby_sim/models/` - `Attributes`, `Position`, `Player` (out-of-position
  "fit" rating), `Team`/`Lineup` (23-man squad builder).
- `rugby_sim/engine/` - `MatchEngine`, a phase-by-phase 80-minute simulator
  driven by the lineup's computed ratings (tries, conversions, penalties,
  cards, turnovers, territory, injuries, substitutions) + `CommentaryEvent`
  log.
- `rugby_sim/data/sample_players.py` - small hand-made seed roster, no
  network needed.
- `rugby_sim/data/legends.py` - Hall of Fame "legend" players, deliberately
  **not** in `POOLS` (only selectable via the interactive CLI/web UI's
  Legends option, never in "by nation" drafting or a real tournament's team
  list). `CURATED_LEGENDS` (~30 hand-tuned) + `get_all_legends()` (~100
  total, the rest scraped from Wikipedia's Hall of Fame category).
- `rugby_sim/data/sources/` - the real player-data pipeline: pulls
  international box-score stats from the `seanyboi/rugbydata` GitHub
  dataset (free, no API key) and converts them to `Attributes` via a
  documented heuristic (`attribute_mapping.py`). Disk-cached under
  `rugby_sim/data/cache/` (gitignored) - no network needed after first pull.
- `rugby_sim/data/national_teams/` - `POOLS["ENG"]()`, `POOLS["NZL"]()`, ...
  one lazy-loaded **player pool** per union: 12 Tier 1 + 11 Tier 2 unions
  (2027 World Cup picture) + `POOLS["BAR"]()` (Barbarians). Pools are flat
  lists, not preset XVs - you draft the lineup yourself.
- `rugby_sim/tournament/` - `Tournament`/`CustomTournament`: real-fixture
  replay, the 2027 World Cup draw, historical World Cups/Six Nations,
  synthetic round-robin/pool+knockout, `Standings` (bonus-point table).
- `rugby_sim/data/squad_repository.py` - `save_team`/`load_team`: a drafted
  squad round-trips to a `.json` file (CLI + web UI).
- `rugby_sim/cli.py` - runnable hardcoded demo.
- `rugby_sim/interactive_cli.py` - prompt-driven terminal builder, no code
  required: draft each team (by nation / free pool / legends), run a single
  match or any tournament format.
- `rugby_sim/webapp.py` + `rugby_sim/web/` - **clickable web UI**: the same
  flow as the CLI but click-driven in a browser. A thin Flask JSON API
  wraps the exact same `POOLS`/`MatchEngine`/`Tournament` calls - no rugby
  logic is reimplemented in JavaScript.
- `tests/` - sanity, data-pipeline, tournament, substitution, player-stats,
  squad-repository, auto-draft, and web-API tests.

## How to run

Requires Python 3.10+. From the project root:

```bash
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

**Interactive terminal builder** (pick pools, draft all 15 positions +
captain, then a single match / real tournament / custom tournament):

```bash
python -m rugby_sim.interactive_cli
```

**Or the clickable web UI**:

```bash
python -m rugby_sim.webapp
```

Then open `http://127.0.0.1:5000` (always port 5000, see below). Local-only,
single-user, no login.

**Or the hardcoded demo match** (standard England XV vs. a "what if" England
XV with Jonah Lomu at fullback):

```bash
python -m rugby_sim.cli
```

**Tests**: `pip install pytest` then `pytest -q`.

**Try your own lineup**, drafting from a real 2026-capped pool (first call
per union hits the network once and disk-caches the result):

```python
from rugby_sim.data import POOLS
from rugby_sim.models import Team, Lineup, Position
from rugby_sim.engine import MatchEngine

italy_pool = POOLS["ITA"]()
capuozzo = next(p for p in italy_pool if p.name == "Ange Capuozzo")
lineup = Lineup()
lineup.set_starter(Position.LEFT_WING, capuozzo)  # his real 2026 slot is fullback
# ... set_starter for the other 14 positions, then lineup.captain = <a Player>
team = Team(name="Italy (what if)", short_code="ITA", lineup=lineup)
# MatchEngine(team, some_other_team, seed=42).run()
```

`lineup.validate()` reports what's missing before you simulate -
`MatchEngine.run()` raises if either lineup isn't complete.

## Tournaments

`Tournament`/`CustomTournament` can replay a **real** competition's actual
fixture list, or a **synthetic** one:

```python
from rugby_sim.tournament import Tournament

teams = {"England": team_eng, "France": team_fra, ...}  # draft from POOLS[code](season="2026")
report = Tournament(teams).run_real("six_nations", season="2026")
report.print_report()
```

- `run_real(key, season)` - actual fixture order for `"six_nations"`,
  `"rugby_championship"`, or `"autumn_nations_series"` (dataset covers
  2022-2026), simulated into a real bonus-point table. No `"rugby_world_cup"`
  key - a real-fixture replay can't reliably tell a World Cup match apart
  from a Rugby Championship one in this dataset; use `run_world_cup_2027`
  or `run_historical_world_cup` instead. Fixture recovery is a documented
  team-set + month-window heuristic, not a guaranteed-exact replica (see
  `real_fixtures.py`).
- `run_round_robin(...)` / `run_pool_and_knockout(...)` / `CustomTournament(teams, format=...)` -
  synthetic fixtures for a tournament that never happened.

### 2027 Rugby World Cup (real draw)

The tournament hasn't been played, but the real pool draw has (3 Dec 2025):

```
Pool A: New Zealand, Australia, Chile, Hong Kong      Pool D: Ireland, Scotland, Uruguay, Portugal
Pool B: South Africa, Italy, Georgia, Romania         Pool E: France, Japan, USA, Samoa
Pool C: Argentina, Fiji, Spain, Canada                Pool F: England, Wales, Tonga, Zimbabwe
```

```python
from rugby_sim.tournament import ALL_TEAMS_2027, CODE_BY_NATION, Tournament
report = Tournament(teams).run_world_cup_2027(fixture_mode="specific", seed=42)
```

`fixture_mode`: `"specific"` (drawn order) or `"random"` (shuffled pool
order, same pools). Knockout qualification (top 2 per pool + best 4
third-placed) is the confirmed real format; the exact Round-of-16 pairing
rule hadn't been published at draw time, so a reasonable seeded bracket is
used instead of an official one. Hong Kong and Zimbabwe aren't in
`rugbydata` at all, so their pools come entirely from Wikipedia.

### Historical Rugby World Cups (1995-2023)

Every professional-era World Cup, with its **real pool draw and real
squads** (parsed from that edition's own Wikipedia squads page, not
hand-entered):

```python
from rugby_sim.data.sources.historical_rwc import get_rwc_year_data
pools, squads = get_rwc_year_data(2003)
report = Tournament(teams).run_historical_world_cup(2003, seed=7)
```

Years: 1995, 1999, 2003, 2007, 2011, 2015, 2019, 2023. Ratings are
archetype-based scaled by union strength (same convention as Legend mode),
*unless* a player's career overlaps `rugbydata`'s 2018+ coverage, in which
case real stats are used (`data_source` tags which). 1999's real format (5
pools, winners go straight to QF, runners-up + best third play a QF
play-off round) is reproduced exactly, not flattened into the generic
top-2-per-pool rule every other edition uses.

### Historical Six Nations (2009-2021)

Same idea for the Six Nations - real squads from each year's Wikipedia
squads page (earlier years list no position, so 2009 is the floor). 2022+
is already covered by `run_real`. Match order is a synthetic round-robin
(no real fixture list on the squads page), so the final table's shape is
real but who-played-whom-in-what-order isn't.

### Historical squads anywhere

Any historical World Cup/Six Nations squad can be mixed into a normal
single match or custom tournament too, not just the dedicated historical
modes - `HIST` in the CLI's free-pool drafting, or the "Historical squad"
button on any `TeamBuilder` panel in the web UI.

### Tournament awards

Every tournament mode computes, at the end: **team tournament stats**
(every box-score field, summed across all matches played), **tournament top
scorers**, **Team of the Tournament** (best average per-match performance -
`rating_at(position)` plus a scoring bonus - per starting slot, no
duplicate players), and **Player of the Tournament** (same pool, restricted
to players who started a semi-final/final if the tournament has one that
deep). `print_report()` / the web UI show all four.

## Legend mode

```python
from rugby_sim.data.legends import CURATED_LEGENDS, get_all_legends
get_all_legends()  # ~100 real Hall of Fame inductees
```

Every name is checked against Wikipedia's "Category:World Rugby Hall of
Fame inductees" (190 members) - never invented. `CURATED_LEGENDS` (~30) are
hand-tuned; the rest have position/nation/era parsed from their own
Wikipedia infobox but an archetype rating (`rugbydata` doesn't reach most of
these careers). Not all 190 resolve (teams, tours, non-playing
administrators are filtered out automatically). In the CLI, `LEG` in
free-pool mode pulls the full roster.

## How a drive's outcome and a team rating are decided

Each drive is one weighted dice roll across a fixed outcome menu (try,
defensive penalty at breakdown or scrum, a card, attacking penalty, lineout
turnover, handling error, nothing) - not an independent sim of every
ruck/scrum/lineout. Each probability is a baseline plus a swing term from
the edge between the two teams' relevant ratings (see
`MatchEngine._resolve_drive`).

`Player.rating_at(position)` is one player's 0-100 fit at a slot
(position-profile-weighted attributes, penalized off their natural
position - the "what if" lever). A *team* rating for a category averages
only the starters actually involved in it (`CATEGORY_POSITION_GROUPS`):
scrum = front row + locks, lineout = locks + back row, lineout throwing =
hooker alone, aerial = back three + locks, tactical kicking = 9/10/15.
Everything else (tackling, attack, handling, discipline) is a whole-team
average.

## Injuries, substitutions & interactive play

`MatchEngine` uses `Lineup.bench` (up to 8): every drive carries a small
injury chance to a random on-field player, and a 50th-75th minute window
has a smaller tactical-substitution chance - either brings on the
best-fitting bench player (real 8-sub cap), or the team plays a man down if
the bench is empty. None of this touches your original `Lineup` - the
engine works from a per-match copy.

**Manual substitutions**: `MatchEngine` can be paused mid-match
(`start()`/`advance_to(minute)`/`finish()`, or `run_interactive(checkpoints,
on_checkpoint)`) to make a substitution yourself
(`apply_substitution(team, position, bench_player=...)`) before resuming -
`run()` is unchanged, just `start()`+`finish()` back to back. Both the CLI
and web UI offer this as an opt-in checkbox for a single match.

**Interactive tournaments**: every tournament mode can be run with "play
your own matches, auto-sim the rest" - pick which team is yours
(`Tournament(..., my_team=..., pause_hook=...)`), and only that team's
fixtures pause for the manual flow above; everything else auto-sims
invisibly. `POST /api/tournament/start` (same body as `/run` plus
`my_team`) returns either a paused live match or a finished report;
`POST /api/tournament/<id>/resume` feeds the result back in and
auto-advances to the next pause point or the end. The web UI's tournament
screen has a "Which team is mine?" picker and a "Play my matches" button,
reusing the same live-match UI as a single friendly - only *your* side gets
a "Substitute..." control, never the auto-simmed opponent's.

## Tournament squads: a fresh lineup every match

By default a drafted team is one fixed `Lineup` reused every match. Pass
`squads={name: [Player, ...]}` instead of `teams={name: Team(...)}` (both
can be mixed in one tournament) to auto-draft a brand-new best-fit XV
before every match from that pool instead. Injuries/red cards then
actually carry over: a player hurt or sent off sits out their team's next
match (`rugby_sim/tournament/availability.py`, a documented 1-match
heuristic, not a medical model). Both the CLI and web UI ask "fixed lineup"
vs. "fresh squad every match" up front.

## Web UI

`python -m rugby_sim.webapp`, then `http://127.0.0.1:5000`. The page is a
clickable, drill-down flow, not one long scroll: a mode-select screen
(Friendly match / Tournament mode), a breadcrumb bar to navigate back, and
within Tournament mode each tournament type (real fixture replay, 2027
World Cup, historical modes, custom) is its own clickable card/screen. Real
fixture replay picks a real competition by name (card), not a raw key from
a dropdown. In-progress tournament data (current standings, pool tables,
knockout bracket, results so far) is shown as collapsible sections you
expand on click, rather than all dumped on screen at once.

Within either mode: pick a pool, click a position to see ranked candidates,
click one to assign, pick a captain and bench, save, then run the match.
For tournaments, "Auto-draft" instantly builds a team's real best XV, or
"Draft yourself" expands the normal builder - you don't have to draft every
team to play. Every scoreline anywhere (group tables, bracket, results
list) is clickable for that match's full commentary/box score.

### Team logos

Every union/Barbarians selector shows a real, transparent-background crest
pulled from that team's Wikipedia infobox `Badge` field
(`rugby_sim/data/sources/team_logos.py`), pre-fetched and disk-cached under
`rugby_sim/web/logos/`. Historical-year squads show the *current* crest,
not a period-accurate one (not verifiable at this scale). Tonga has no
`Badge` field on Wikipedia, so no logo shows for it. No official Hall of
Fame logo exists on Wikipedia, so Legend mode shows no crest.

### Always port 5000

Always serves on port 5000; a stale server already listening there is
stopped automatically (Windows only). Override with `WEBAPP_PORT` to run a
second instance.

## Data pipeline notes

- Tier 1 unions are pulled live from `rugbydata`'s box scores. Tier 2
  unions merge real `rugbydata` stats where they exist with that union's
  Wikipedia "Current squad" for everyone else (cross-referenced against
  rugbydata's global player registry for real stats where possible, else a
  generic archetype rating - `data_source` always says which). Hong Kong
  and Zimbabwe (2027 draw only, no `rugbydata` team_id) are Wikipedia-only.
- **Cross-union calibration**: percentile scaling ranks a player against a
  cross-union reference pool (not just their own union's roster, which has
  no absolute calibration), plus `UNION_STRENGTH` - a rough
  competitiveness multiplier per union - so genuine mismatches stay
  mismatched while a strong Tier 2 side can still occasionally upset a
  Tier 1 one.
- Attribute values are a heuristic approximation (no raw pace/strength
  numbers in the dataset), not a scouted rating - see `attribute_mapping.py`.
- The dataset doesn't distinguish Lock 4/5 or which wing/centre slot a
  player featured in - those entries share one representative position.
- The same real person can get two different `player_id`s in the dataset;
  `build_union_pool` dedupes by name, keeping whichever id has more caps.

## Roadmap

- Draft mode: a turn-based player draft (alternating picks with an
  opponent/CPU from a shared pool) as an alternative to freely choosing any
  player for any slot.
