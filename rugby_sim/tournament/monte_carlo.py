"""Monte Carlo "what-if" comparison: the SAME two lineups, run many times
with different random seeds, aggregated into real percentage distributions
instead of one single simulated result. Reuses `MatchEngine.run()` exactly
as-is (no new simulation logic, no new probabilities) - this module is
purely an aggregation layer over results the engine already produces.

Every distribution here is a real count of actual simulated outcomes
divided by the number of runs - never interpolated, smoothed, or assumed.
A player/stat that never showed up across all N runs simply doesn't appear
in its distribution, rather than being padded with a fabricated 0%% entry.
"""

from collections import Counter
from dataclasses import fields as dc_fields
from typing import Dict, List, Optional

from ..engine import MatchEngine
from ..engine.match_engine import MatchResult, TeamMatchStats
from ..models import Team

# A match run here is cheap (same cost as any other single `MatchEngine.run()`
# call this project already makes routinely), but this endpoint runs N of
# them synchronously inside one HTTP request - bounded so a request can't
# ask for an unreasonable number and block the server for a long time.
MAX_MONTE_CARLO_RUNS = 300
DEFAULT_MONTE_CARLO_RUNS = 100

# A stat's own real distinct values across all N runs, if there are few
# enough of them, are shown one by one (e.g. "2 tries: 41%%") - the most
# legible form for a typically-small counting stat. Above this many
# distinct real values, fall back to a bounded number of equal-width bins
# spanning the REAL observed min-max (never a fixed/assumed range).
MAX_DISCRETE_VALUES = 10
HISTOGRAM_BINS = 6


def run_monte_carlo_matches(
    home: Team, away: Team, n: int, seed_start: int = 0,
    tactics: Optional[Dict[str, Dict[str, str]]] = None, weather: str = "dry",
) -> List[MatchResult]:
    """Runs the SAME two lineups `n` times (clamped to `MAX_MONTE_CARLO_RUNS`),
    each with its own seed (`seed_start + i`) so every run is a genuinely
    different simulated match, not a repeat - `tactics`/`weather` (if given)
    apply identically to every run, since the "what if" being compared here
    is "how does this exact matchup/gameplan play out across many random
    outcomes," not a tactics sweep."""
    n = max(1, min(n, MAX_MONTE_CARLO_RUNS))
    results = []
    for i in range(n):
        engine = MatchEngine(home, away, seed=seed_start + i, tactics=tactics, weather=weather)
        results.append(engine.run())
    return results


def _fmt_num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def _distribution(values: List[float]) -> List[dict]:
    """See module docstring - a real percentage-of-runs distribution, never
    a single mean/median collapsing the spread away."""
    if not values:
        return []
    total = len(values)
    uniq = sorted(set(values))
    if len(uniq) <= MAX_DISCRETE_VALUES:
        counts = Counter(values)
        return [
            {"label": _fmt_num(v), "pct": round(100 * counts[v] / total, 1), "count": counts[v]}
            for v in uniq
        ]
    lo, hi = min(values), max(values)
    width = (hi - lo) / HISTOGRAM_BINS
    bucket_counts = [0] * HISTOGRAM_BINS
    for v in values:
        idx = int((v - lo) / width) if width > 0 else 0
        idx = min(HISTOGRAM_BINS - 1, max(0, idx))
        bucket_counts[idx] += 1
    out = []
    for i, count in enumerate(bucket_counts):
        lo_b, hi_b = lo + i * width, lo + (i + 1) * width
        out.append({
            "label": f"{_fmt_num(lo_b)}-{_fmt_num(hi_b)}",
            "pct": round(100 * count / total, 1),
            "count": count,
        })
    return out


def aggregate_monte_carlo(results: List[MatchResult], home_name: str, away_name: str) -> dict:
    """Turns a list of real `MatchResult`s into real percentage
    distributions: the match outcome (home/draw/away), each side's real
    scoreline distribution, who was Player of the Match and how often (a
    player who's never once POM across all N runs just doesn't appear -
    never padded to a fabricated entry), and - for every single real
    `TeamMatchStats` field that exists today, automatically, so a future
    new stat is covered for free - that stat's own real distribution for
    each team."""
    n = len(results)
    outcomes = Counter()
    home_scores: List[float] = []
    away_scores: List[float] = []
    pom_counts: Dict[str, dict] = {}
    team_stat_values: Dict[str, Dict[str, List[float]]] = {home_name: {}, away_name: {}}

    for r in results:
        home_scores.append(float(r.score_home))
        away_scores.append(float(r.score_away))
        if r.score_home > r.score_away:
            outcomes["home_win"] += 1
        elif r.score_away > r.score_home:
            outcomes["away_win"] += 1
        else:
            outcomes["draw"] += 1

        pom = r.player_of_the_match
        if pom is not None:
            pom_team = next((ps.team for ps in r.player_stats if ps.player is pom), "")
            entry = pom_counts.setdefault(pom.name, {"name": pom.name, "team": pom_team, "count": 0})
            entry["count"] += 1

        for team_name in (home_name, away_name):
            stats = r.stats.get(team_name)
            if stats is None:
                continue
            for f in dc_fields(TeamMatchStats):
                team_stat_values[team_name].setdefault(f.name, []).append(getattr(stats, f.name))

    outcome_pct = {k: round(100 * outcomes.get(k, 0) / n, 1) for k in ("home_win", "draw", "away_win")}

    pom_distribution = sorted(
        (
            {"name": e["name"], "team": e["team"], "pct": round(100 * e["count"] / n, 1)}
            for e in pom_counts.values()
        ),
        key=lambda e: -e["pct"],
    )

    team_stats_distribution = {
        team_name: {stat_name: _distribution(values) for stat_name, values in stats.items()}
        for team_name, stats in team_stat_values.items()
    }

    return {
        "runs": n,
        "outcome_pct": outcome_pct,
        "score_distribution": {
            home_name: _distribution(home_scores),
            away_name: _distribution(away_scores),
        },
        "player_of_the_match_distribution": pom_distribution,
        "team_stats_distribution": team_stats_distribution,
    }
