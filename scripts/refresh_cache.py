#!/usr/bin/env python
"""Force-refreshes the CACHEABLE REAL DATA that can actually go stale over
time - a union's real rugbydata match log (new caps/call-ups each real
Test window) and, for unions whose pipeline also reads a "Current squad"
Wikipedia page (Tier 2/wiki-only unions, or the 2026-specific top-up path -
see `pool_builder.build_union_pool_2026`), that page's own cache.

Deliberately out of scope, on purpose, never touched by this script:
- Every HISTORICAL source (Classic Matches, historical Rugby World Cup/
  Six Nations/Rugby Championship squads, Legends/Hall of Fame, venues,
  team colors) - that's real recorded history, it doesn't change, so
  "refreshing" it would just be a wasted network round-trip for an
  identical result.
- Team crest/logo images (`team_logos.py`) - national federation badges
  are stable for years/decades (see that module's own docstring); not
  worth the network cost of a routine refresh.

This only refreshes the ON-DISK cache (`rugby_sim/data/cache/`,
gitignored). A currently-running `python -m rugby_sim.webapp` process
keeps its own in-memory per-season pool cache until restarted - run this
script, then restart the web app, to actually see the refreshed data.

Usage:
    python scripts/refresh_cache.py --unions ENG,FRA,NZL
    python scripts/refresh_cache.py --unions ENG --season 2025
    python scripts/refresh_cache.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rugby_sim.data.sources import rugby_data_client, wikipedia_squad
from rugby_sim.data.sources.pool_builder import ALL_TEAM_IDS, DEFAULT_SEASON, build_union_pool


def _delete_team_cache(team_id: str) -> bool:
    """Deletes this union's cached rugbydata match-log parquet (if any) and
    clears the in-process `lru_cache` so the very next fetch in THIS run
    goes to the network, not a stale in-memory copy."""
    cache_file = rugby_data_client._cache_path(f"team/{team_id}.parquet")
    existed = cache_file.exists()
    if existed:
        cache_file.unlink()
    rugby_data_client.fetch_team_matches.cache_clear()
    return existed


def _delete_wiki_cache(title: str) -> bool:
    cache_file = wikipedia_squad._wiki_cache_path(title)
    existed = cache_file.exists()
    if existed:
        cache_file.unlink()
    return existed


def refresh_union(code: str, season: str) -> None:
    entry = ALL_TEAM_IDS.get(code)
    if entry is None:
        print(f"  {code}: unknown union code, skipping")
        return
    team_id, _dataset_name, nation = entry

    cleared = []
    if team_id and _delete_team_cache(team_id):
        cleared.append("rugbydata")
    wiki_title = wikipedia_squad.WIKI_UNION_PAGES.get(code)
    if wiki_title and _delete_wiki_cache(wiki_title):
        cleared.append("wikipedia current-squad page")

    try:
        pool = build_union_pool(code, season=season)
    except Exception as e:
        print(f"  {code} ({nation}): refresh FAILED - {e}")
        return

    cleared_note = f" (cleared: {', '.join(cleared)})" if cleared else " (nothing was cached yet)"
    print(f"  {code} ({nation}): {len(pool)} real players pulled for season {season}{cleared_note}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--unions", help="Comma-separated union codes, e.g. ENG,FRA,NZL")
    parser.add_argument("--all", action="store_true", help="Refresh every known union")
    parser.add_argument(
        "--season", default=DEFAULT_SEASON,
        help=f"Season to refresh (default: {DEFAULT_SEASON}, the project's current default)",
    )
    args = parser.parse_args()

    if args.all:
        codes = sorted(ALL_TEAM_IDS.keys())
    elif args.unions:
        codes = [c.strip().upper() for c in args.unions.split(",") if c.strip()]
    else:
        parser.error("Pass --unions CODE1,CODE2 or --all")
        return

    print(f"Refreshing {len(codes)} union(s) for season {args.season}...")
    for code in codes:
        refresh_union(code, args.season)
    print("Done. Restart the web app for a running server to pick up the refreshed data.")


if __name__ == "__main__":
    main()
