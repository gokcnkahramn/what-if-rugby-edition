"""Out-of-sample calibration harness: a leakage-free variant of
`calibrate_ratings.py`.

Why this script exists: `calibrate_ratings.py` builds each union's player
ratings from the SAME season's real box-score stats as the fixtures it then
"predicts" - i.e. 2024 Six Nations player ratings are derived from full 2024
season stats, which already include the 15 fixtures being evaluated. That's
data leakage: the outcomes of the matches being "predicted" have already
informed the ratings used to predict them. An external audit flagged exactly
this concern (whether calibration and evaluation datasets overlap).

This script removes that overlap entirely:

  - Player ratings are built from `build_union_pool(code, season="2023")` -
    i.e. each union's real 2023 rugbydata box-score stats only.
  - Those 2023-derived ratings are then used to simulate the 15 REAL 2024
    Six Nations fixtures, compared against the same hardcoded real 2024
    results table `calibrate_ratings.py` already uses (reused verbatim here,
    not re-guessed).

The 2023 stats used to build the ratings have zero overlap with the 2024
results being predicted - no match played in 2024 ever contributes to a
2023-season aggregate. This is a genuine out-of-sample test: is a team
built from last year's real individual performances a predictor of this
year's real results? It is a harder and more honest test than the original
script's self-consistency check, and is expected to score lower - a team's
true current strength always drifts a year ahead of (and often quite far
from) its roster's prior-year individual stats (retirements, form changes,
injuries, new caps). A lower score here is not a model regression; it's
what an honest, leak-free measurement looks like.

Everything else - the match engine, the auto-draft, the modal-vote-over-N-
seeds simulation method, the real-results table - is intentionally kept
identical to `calibrate_ratings.py`. The ONLY methodological change is which
season's stats inform the ratings (2023) vs. which season's results get
predicted (2024).

Run: `python scripts/calibrate_ratings_out_of_sample.py`
"""

from __future__ import annotations

from collections import Counter

from rugby_sim.data.sources.auto_draft import auto_draft_lineup
from rugby_sim.data.sources.pool_builder import build_union_pool
from rugby_sim.engine.match_engine import MatchEngine
from rugby_sim.models.team import Team

RATINGS_SEASON = "2023"  # season whose real stats build the player ratings
EVAL_SEASON = "2024"  # season whose real results we predict (never touches ratings)
RUNS_PER_FIXTURE = 11  # odd, so the modal-vote tie-break below is rare

# Union short codes used by `build_union_pool`, mapped to the display name
# used in the real results table below.
UNIONS = {
    "ENG": "England", "FRA": "France", "IRE": "Ireland",
    "SCO": "Scotland", "WAL": "Wales", "ITA": "Italy",
}

# Real 2024 Six Nations Championship results - reused verbatim from
# `calibrate_ratings.py` (same source: Wikipedia, "2024 Six Nations
# Championship", checked 2026-11-14). Deliberately NOT re-entered by hand
# here to avoid a second, possibly-diverging copy of this table.
# (home, away, home_score, away_score)
REAL_RESULTS = [
    ("France", "Ireland", 17, 38),
    ("Italy", "England", 24, 27),
    ("Wales", "Scotland", 26, 27),
    ("Scotland", "France", 16, 20),
    ("England", "Wales", 16, 14),
    ("Ireland", "Italy", 36, 0),
    ("France", "Italy", 13, 13),
    ("England", "Ireland", 23, 22),
    ("Scotland", "England", 30, 21),
    ("Italy", "Scotland", 31, 29),
    ("Ireland", "Wales", 31, 7),
    ("Wales", "Italy", 21, 24),
    ("Ireland", "Scotland", 17, 13),
    ("France", "England", 33, 31),
    ("Wales", "France", 24, 45),
]


def real_winner(home_score: int, away_score: int, home: str, away: str) -> str:
    if home_score == away_score:
        return "draw"
    return home if home_score > away_score else away


def main() -> None:
    print(
        f"Building Six Nations squads from real rugbydata {RATINGS_SEASON} box "
        f"scores (out-of-sample vs. the {EVAL_SEASON} results below)..."
    )
    teams: dict[str, Team] = {}
    for code, nation in UNIONS.items():
        pool = build_union_pool(code, season=RATINGS_SEASON)
        lineup = auto_draft_lineup(pool)
        teams[nation] = Team(name=nation, short_code=code, lineup=lineup)
        print(f"  {nation}: {len(pool)} players in pool, lineup valid: {lineup.validate() == []}")

    correct = 0
    total = len(REAL_RESULTS)
    print(f"\nSimulating {total} real {EVAL_SEASON} fixtures x {RUNS_PER_FIXTURE} runs each...\n")

    for home, away, hs, as_ in REAL_RESULTS:
        actual = real_winner(hs, as_, home, away)
        outcomes = Counter()
        for run_i in range(RUNS_PER_FIXTURE):
            seed = hash((home, away, run_i)) & 0xFFFFFFFF
            result = MatchEngine(teams[home], teams[away], seed=seed).run()
            w = result.winner
            outcomes[w.name if w else "draw"] += 1
        predicted, votes = outcomes.most_common(1)[0]
        hit = predicted == actual
        correct += hit
        mark = "OK" if hit else "MISS"
        print(
            f"[{mark}] {home} vs {away}: real={actual} (real {hs}-{as_}), "
            f"predicted={predicted} ({votes}/{RUNS_PER_FIXTURE} runs) -> {dict(outcomes)}"
        )

    print(
        f"\nOut-of-sample calibration ({RATINGS_SEASON} ratings -> {EVAL_SEASON} real "
        f"results): {correct}/{total} correct winners picked ({100 * correct / total:.0f}%)."
    )
    print(
        "Unlike calibrate_ratings.py, this number is genuinely leakage-free: "
        f"none of the real {EVAL_SEASON} match outcomes being predicted contributed "
        f"to the {RATINGS_SEASON}-derived player ratings used to predict them. It is "
        "a directional sanity check on out-of-sample generalization, not a "
        "predictive-accuracy claim - real rugby has upsets, and a roster's "
        "prior-year box-score stats are an imperfect proxy for its following "
        "year's actual strength (retirements, form, injuries, new caps)."
    )


if __name__ == "__main__":
    main()
