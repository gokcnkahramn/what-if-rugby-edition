# What If Rugby Edition

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](<https://img.shields.io/badge/tests-398%20passing-brightgreen.svg>)](tests/)

**What if you played Antoine Dupont at fullback? What if Jonah Lomu started
at tighthead?** Build real squads from real players, drop anyone into any
position, and simulate the match - a click-driven "what if" rugby lab, not
a scripted game. Every rating comes from real player data (never invented
stats), every tournament/draw is the real thing where one exists, and
every heuristic is documented rather than presented as fact.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m rugby_sim.webapp
```

Open `http://127.0.0.1:5000` - pick a pool, click a position, click a
player, run the match.

## What you can do

- **Friendly match / Draft mode / Tournament mode / Season mode** - build
  squads from real national-team pools (or Legends, or historical World
  Cup/Six Nations squads), replay real competitions (Six Nations, Rugby
  Championship, Pacific Nations Cup, Rugby Europe Championship, the real
  2027 World Cup draw, historical World Cups (1995-2023), historical Six
  Nations (2000-2021, real fixture order for 2000-2008), historical Rugby
  Championship/Tri Nations (1996-2025, real fixture order throughout)), or merge pools
  into a shared draft-and-protect/poach mode. Season mode chains every
  real tournament a union played in a given year back to back, carrying
  injuries/suspensions/condition/rankings across tournament boundaries.
- **Manager controls** - pick real pre-match tactics (attack shape,
  defensive style, kick tendency/style) for your own team, and make real
  in-match decisions (what to do with a just-awarded penalty: kick for
  posts, touch, or a quick tap) - across every mode, not just a single
  friendly.
- **Live play** - pause mid-match to make a substitution, swap two
  on-field players, or resolve a pending manager decision, with a paced,
  spoiler-free event reveal, a live pitch diagram, and live-updating stats.
- **Stamina, injuries, cards** - a four-input fatigue model, named injury
  types with real matches-missed tiers, and real World Rugby card rules
  (yellow = 10-min sin bin, red = next-match suspension, a second yellow
  escalates per law 19.2).
- **Team rankings** - a real World-Rugby-formula ranking that moves after
  every match (seeded from a dated real snapshot, not a live feed), plus a
  squad-quality score kept separate from it so over/under-performance is
  visible.
- **Monte Carlo "what-if" comparison** - run the same two lineups many times
  (Friendly/Draft modes directly, or an opt-in "how would this likely end?"
  preview before a Tournament/Season live match) and see real percentage
  distributions - match outcome, each side's scoreline spread, Player of
  the Match, and every real per-team stat - never a single collapsed
  mean/median.
- **Real 2007 EA Sports Rugby 08 ratings** for pre-2018 historical players -
  sourced from the already-published `marnoux/rugby08-player-explorer`
  fan extraction of the game's own database (1,904 players, 23 real raw
  ratings each), overlaid on top of this project's own archetype baseline
  for every honest 1:1 attribute match (see
  `rugby_sim/data/sources/rugby08_dataset.py`) - a real individual game
  rating instead of a generic estimate wherever a historical player's own
  career overlaps that era. That source has no LICENSE file, so every
  player built from it is tagged `data_source="rugby08_dataset"`, same
  "no license, fan-sourced, use at own risk" transparency convention
  `EA_RATED_PLAYERS` already uses.

See the module docstrings (`rugby_sim/engine/MATCH_ENGINE_MODEL.md`,
`rugby_sim/data/sources/ATTRIBUTE_MAPPING.md`, and the code itself) for the
full, honest details on any feature above - they're written to be the real
documentation, not just comments.

## Project layout

| Path                         | What's there                                                     |
| ----------------------------- | ----------------------------------------------------------------- |
| `rugby_sim/models/`           | `Player`, `Position`, `Team`/`Lineup` - the squad-building core   |
| `rugby_sim/engine/`           | `MatchEngine` - the phase-by-phase match simulator                |
| `rugby_sim/data/`             | Real player pools, Legends, the rugbydata/Wikipedia data pipeline  |
| `rugby_sim/tournament/`       | Real & synthetic tournament formats, standings, rankings, season   |
| `rugby_sim/webapp.py` + `rugby_sim/web/` | The Flask API + clickable web UI (no rugby logic in JS) |
| `rugby_sim/interactive_cli.py` | A terminal-only alternative to the web UI                          |
| `tests/`                       | 398 tests across data, tournaments, the engine, and the web API    |

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

## Calibration and rating sanity checks

Two re-runnable scripts keep the rating pipeline honest:
`scripts/calibrate_ratings.py` (auto-drafts real 2024 Six Nations squads,
simulates every fixture, compares modal winner against the real result -
currently 9/15 same-season, 7-8/15 out-of-sample with
`calibrate_ratings_out_of_sample.py`'s leakage-free prior-season setup) and
`scripts/analyze_rating_distributions.py` (position-by-position
mean/median/std-dev across every Tier 1 union's real pool, with regression
guards in `tests/test_rating_distributions.py`). Neither is chased to a
perfect score - real rugby has upsets on purpose; they exist to catch
regressions when the model changes.

## Developing / verifying changes

- **Run the suite**: `pytest -q` (see the badge above for the current count).
- **Touching ratings/attributes/the data pipeline?** Read
  `rugby_sim/data/sources/ATTRIBUTE_MAPPING.md` first, then re-run the two
  calibration scripts above after your change.
- **Touching match resolution (drives, cards, injuries, stamina, tactics)?**
  Read `rugby_sim/engine/MATCH_ENGINE_MODEL.md` first - the honest,
  per-outcome breakdown of what drives each probability and what isn't
  modeled at all.

## Keeping real data fresh

Every real pull (rugbydata match logs, Wikipedia squad/historical pages)
is cached to disk forever - the simulator never needs the network once a
union's been pulled. For unions whose real roster can change between real
Test windows, force a refresh with `python scripts/refresh_cache.py
--unions ENG,FRA,NZL` (or `--all`) - restart the web app afterward to pick
it up. Historical sources (Classic Matches, historical World Cups/Six
Nations/Rugby Championship, Legends, venues, team crests) are real,
unchanging history and are deliberately never touched by this script.

## Playing from your phone

The app only runs locally, so expose it with a
[Cloudflare Tunnel](https://github.com/cloudflare/cloudflared):

```bash
python -m rugby_sim.webapp          # terminal 1
cloudflared tunnel --url http://localhost:5000   # terminal 2
```

`cloudflared` prints a public `https://*.trycloudflare.com` link - open
that on your phone. It only forwards to that one local port (nothing else
on your PC is reachable), but anyone with the link can use the app with no
password, so treat it as something to only share with people you trust,
and close the tunnel when you're done.

## License

[MIT](LICENSE).
