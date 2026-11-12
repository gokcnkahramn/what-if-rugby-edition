"""Thin client over the `seanyboi/rugbydata` GitHub dataset (v3 schema).

The published `rugbypy` PyPI package (v2.0.0) still points at `data/v2/...`
URLs in that repo, which now 404 - the dataset moved to `data/v3/...` with a
different, richer layout (per-team match log with a `players` id list, and
per-player match-by-match box scores including `position`). This client
talks to the v3 layout directly instead of depending on the stale package.

Every fetch is cached to disk under `rugby_sim/data/cache/` (gitignored) so
the simulator never needs the network to run once a union has been pulled.
"""

from __future__ import annotations

import os
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

RAW_BASE = "https://raw.githubusercontent.com/seanyboi/rugbydata/main/data/v3"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"

# Competitions that count as a "national team" cap for pool-building purposes.
# (Club comps like Top 14 / URC / Super Rugby are deliberately excluded.)
INTERNATIONAL_COMPETITIONS = {
    "7a1361e7": "Six Nations",
    "423a2845": "Rugby Championship",
    "96c775f2": "International Test Match",
    "5a4d4920": "Rugby World Cup",
    "f44ef210": "Autumn Nations Series",
    "d1999468": "Pacific Nations Cup",
    "05d59524": "Rugby Europe Championship",
}


def _cache_path(relative: str) -> Path:
    path = CACHE_DIR / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _fetch_parquet(relative_url: str, use_cache: bool = True) -> Optional[pd.DataFrame]:
    """Fetch a parquet file from the dataset, caching the raw bytes locally."""
    cache_file = _cache_path(relative_url)
    if use_cache and cache_file.exists():
        return pd.read_parquet(cache_file, engine="pyarrow")

    url = f"{RAW_BASE}/{relative_url}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = resp.read()
    except Exception as e:
        print(f"[rugby_data_client] could not fetch {url}: {e}")
        return None

    cache_file.write_bytes(data)
    return pd.read_parquet(cache_file, engine="pyarrow")


@lru_cache(maxsize=None)
def fetch_team_matches(team_id: str) -> Optional[pd.DataFrame]:
    """One row per match this team played, including a `players` id list."""
    return _fetch_parquet(f"team/{team_id}.parquet")


@lru_cache(maxsize=None)
def fetch_player_history(player_id: str) -> Optional[pd.DataFrame]:
    """One row per match this player appeared in (club AND country)."""
    return _fetch_parquet(f"player/{player_id}.parquet")


@lru_cache(maxsize=None)
def fetch_player_registry() -> Optional[pd.DataFrame]:
    """The dataset's global `player_id -> player_name` index (~9,200 rows).

    This is what makes name-based cross-referencing possible: given a name
    scraped from elsewhere (e.g. Wikipedia), look it up here to find a
    `player_id` and pull that person's real stats from `fetch_player_history`,
    even if they have no caps recorded for the union/season you asked about.
    """
    return _fetch_parquet("player/player_registry.parquet")


@lru_cache(maxsize=None)
def _dataset_file_tree() -> list:
    """One GitHub API call listing every file in the dataset repo. Cached to
    disk (it's a ~5MB JSON) so later runs/processes don't need the network
    just to enumerate which `dates/*.parquet` files exist for a season."""
    cache_file = _cache_path("_file_tree.json")
    if cache_file.exists():
        import json
        return json.loads(cache_file.read_text(encoding="utf-8"))["tree"]

    import json
    url = "https://api.github.com/repos/seanyboi/rugbydata/git/trees/main?recursive=1"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"[rugby_data_client] could not list dataset file tree: {e}")
        return []

    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data["tree"]


def list_date_files(season: str) -> list[str]:
    """Every `data/v3/dates/<season>....parquet` path for a given season."""
    tree = _dataset_file_tree()
    prefix = f"data/v3/dates/{season}"
    return sorted(
        entry["path"][len("data/v3/"):]
        for entry in tree
        if entry.get("path", "").startswith(prefix)
    )


def fetch_season_fixture_index(season: str) -> Optional[pd.DataFrame]:
    """All fixtures (home/away team + id, competition_id, match_id) for a
    whole season, concatenated from the daily `dates/*.parquet` index files
    and cached as one combined file so repeat calls are instant."""
    combined_cache = _cache_path(f"dates_by_season/{season}.parquet")
    if combined_cache.exists():
        return pd.read_parquet(combined_cache, engine="pyarrow")

    relative_paths = list_date_files(season)
    frames = []
    for rel in relative_paths:
        df = _fetch_parquet(rel)
        if df is not None and not df.empty:
            date_str = rel.split("/")[-1].replace(".parquet", "")
            df = df.assign(game_date=date_str)
            frames.append(df)
    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    combined.to_parquet(combined_cache, engine="pyarrow")
    return combined


def refresh_cache_for(team_id: str, player_ids: list[str]) -> None:
    """Force a re-pull (bypassing the on-disk cache) for a union's data."""
    _fetch_parquet(f"team/{team_id}.parquet", use_cache=False)
    fetch_team_matches.cache_clear()
    for pid in player_ids:
        _fetch_parquet(f"player/{pid}.parquet", use_cache=False)
    fetch_player_history.cache_clear()
