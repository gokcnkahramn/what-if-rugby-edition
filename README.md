# What If Rugby Edition

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](<https://img.shields.io/badge/tests-89%20passing-brightgreen.svg>)](tests/)

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
- **Draft mode** - merge pools into one shared player pool, alternate
  picks with an AI opponent, a PES21-style 3-round protect/poach phase,
  then build and play your drafted XV.
- **Live play** - pause mid-match to make a substitution, with a paced,
  spoiler-free event reveal and fast-forward controls.

Every rating comes from real player data (not invented stats), every
tournament/draw is the real thing where one exists, and every heuristic or
approximation is called out explicitly in the code rather than presented
as fact - see `rugby_sim/data/sources/attribute_mapping.py` and the
in-repo docstrings for the honest details.

## Project layout

| Path                                         | What's there                                                            |
| -------------------------------------------- | ----------------------------------------------------------------------- |
| `rugby_sim/models/`                        | `Player`, `Position`, `Team`/`Lineup` - the squad-building core |
| `rugby_sim/engine/`                        | `MatchEngine` - the drive-by-drive match simulator                    |
| `rugby_sim/data/`                          | Real player pools, Legends, the rugbydata/Wikipedia data pipeline       |
| `rugby_sim/tournament/`                    | Real & synthetic tournament formats, standings, awards                  |
| `rugby_sim/webapp.py` + `rugby_sim/web/` | The Flask API + clickable web UI (no rugby logic in JS)                 |
| `rugby_sim/interactive_cli.py`             | A terminal-only alternative to the web UI                               |
| `tests/`                                   | 89 tests across data, tournaments, the engine, and the web API          |

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

## License

[MIT](LICENSE).
