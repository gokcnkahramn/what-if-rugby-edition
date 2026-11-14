"""Calibration harness: how often does the engine pick the real winner?

This is a *sanity-check* tool, not a claim of predictive accuracy - a
heuristic "what if" rugby simulator built from box-score-derived ratings
will never match real rugby's upsets, injuries-on-the-day, weather, or
coaching, and isn't trying to. The point is a single, honest, re-runnable
number to judge whether a change to `attribute_mapping.py`, `position.py`
or `match_engine.py` moved the model in the right direction (more real
winners picked, more realistic score margins) or the wrong one - not to
chase 100%.

Method: build each 2024 Six Nations union's real squad from real rugbydata
2024 box-score stats (`build_union_pool`), auto-draft a starting XV per
union (`auto_draft_lineup` - the same greedy draft used elsewhere in this
project, not hand-picked), then simulate every one of the 15 real 2024
Six Nations fixtures `RUNS_PER_FIXTURE` times with different seeds. A
fixture's "simulated winner" is whichever side won the most of those
runs (the modal outcome) - since the engine is randomized, a single seed
would just be noise. Compare against the real final score (hardcoded
below from the public 2024 Six Nations record - this is NOT scraped or
guaranteed network-free, it's a small fixed table, see note there).

Run: `python scripts/calibrate_ratings.py`
"""

from __future__ import annotations

from collections import Counter

from rugby_sim.data.sources.auto_draft import auto_draft_lineup
from rugby_sim.data.sources.pool_builder import build_union_pool
from rugby_sim.engine.match_engine import MatchEngine
from rugby_sim.models.team import Team

SEASON = "2024"
RUNS_PER_FIXTURE = 11  # odd, so the modal-vote tie-break below is rare

# Union short codes used by `build_union_pool`, mapped to the display name
# used in the real results table below.
UNIONS = {
    "ENG": "England", "FRA": "France", "IRE": "Ireland",
    "SCO": "Scotland", "WAL": "Wales", "ITA": "Italy",
}

# Real 2024 Six Nations Championship results - every one of the 15 round-
# robin fixtures (6 choose 2), hardcoded from the public record (Wikipedia,
# "2024 Six Nations Championship", checked 2026-11-14). Not pulled from the
# rugbydata API (which has no score/result field in this project's client),
# and not re-fetched at run time - if a transcription error is ever found
# here, fix this table directly rather than adding a live fetch for it.
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
    print(f"Building {SEASON} Six Nations squads from real rugbydata box scores...")
    teams: dict[str, Team] = {}
    for code, nation in UNIONS.items():
        pool = build_union_pool(code, season=SEASON)
        lineup = auto_draft_lineup(pool)
        teams[nation] = Team(name=nation, short_code=code, lineup=lineup)
        print(f"  {nation}: {len(pool)} players in pool, lineup valid: {lineup.validate() == []}")

    correct = 0
    total = len(REAL_RESULTS)
    print(f"\nSimulating {total} fixtures x {RUNS_PER_FIXTURE} runs each...\n")

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

    print(f"\n{SEASON} Six Nations calibration: {correct}/{total} correct winners picked "
          f"({100 * correct / total:.0f}%).")
    print(
        "This is a directional sanity check, not a predictive-accuracy claim - "
        "real rugby has upsets a box-score-derived heuristic model cannot and "
        "should not try to fully reproduce."
    )


if __name__ == "__main__":
    main()
