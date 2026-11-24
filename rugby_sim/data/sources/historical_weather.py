"""Real historical weather for a specific date + location, via Open-Meteo's
free Historical Weather API (`https://archive-api.open-meteo.com/v1/archive`)
- no API key/signup required for non-commercial use (confirmed live;
rate-limited to 10,000 calls/day on the free tier), covers 1940-present
(ERA5 model), comfortably covers every Classic Match this project has
(1995+). Attribution is required under Open-Meteo's CC BY 4.0 licence -
"Weather data by Open-Meteo.com" (linked to https://open-meteo.com/) must
be shown wherever this data is displayed (see `rugby_sim/web/index.html`).

Used only for the curated Classic Matches catalog (see
`rugby_sim.data.classic_match_objectives.ClassicMatch.venue` + `date`) -
NOT for procedural real-fixture replay modes (Six Nations/Rugby
Championship/Season mode), which have no real per-match venue data to key
a weather lookup off at all.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .rugby_data_client import CACHE_DIR
from .wikipedia_squad import USER_AGENT

ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_CACHE_DIR = CACHE_DIR / "weather"

DAILY_VARS = "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"


def _cache_path(latitude: float, longitude: float, date: str) -> Path:
    WEATHER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return WEATHER_CACHE_DIR / f"{latitude:.4f}_{longitude:.4f}_{date}.json"


def fetch_historical_weather(latitude: float, longitude: float, date: str) -> Optional[dict]:
    """Real daily weather for `date` ("YYYY-MM-DD") at `(latitude,
    longitude)` - `{temperature_2m_max, temperature_2m_min,
    precipitation_sum, wind_speed_10m_max}` (first/only entry of each
    `daily` array), disk-cached (one real network call per venue+date,
    ever). Returns `None` on any fetch/parse failure - a missing real
    weather fact should never crash the app, same "never block over a
    visual nicety" convention `team_logos.py`/`background_image.py` use."""
    cache_file = _cache_path(latitude, longitude, date)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    params = (
        f"latitude={latitude}&longitude={longitude}"
        f"&start_date={date}&end_date={date}&daily={DAILY_VARS}&timezone=auto"
    )
    url = f"{ARCHIVE_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                time.sleep(8 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    else:
        return None

    daily = raw.get("daily") or {}
    try:
        result = {
            "temperature_2m_max": daily["temperature_2m_max"][0],
            "temperature_2m_min": daily["temperature_2m_min"][0],
            "precipitation_sum": daily["precipitation_sum"][0],
            "wind_speed_10m_max": daily["wind_speed_10m_max"][0],
        }
    except (KeyError, IndexError):
        return None

    try:
        cache_file.write_text(json.dumps(result), encoding="utf-8")
    except OSError:
        pass
    return result


# Simple, honest thresholds mapping real weather numbers to
# `MatchEngine`'s existing 3-way category (`"dry"|"wet"|"windy"` - see
# `engine/match_engine.py`) - not reverse-engineered to hit a target
# distribution, just a plausible real-world read: any meaningful rain that
# day counts as "wet" (the engine's wet-weather effects are about ball
# handling, so even a modest amount of real rain qualifies); failing that,
# a notably windy day counts as "windy"; otherwise "dry".
WET_PRECIPITATION_MM_THRESHOLD = 1.0
WINDY_WIND_SPEED_KMH_THRESHOLD = 30.0


def classify_weather(weather_data: Optional[dict]) -> str:
    """Maps a real `fetch_historical_weather` result to `"dry"|"wet"|"windy"`
    for `MatchEngine(weather=...)`. `None` (no real data available) ->
    `"dry"`, the engine's own existing default - never invents a condition
    it couldn't actually confirm."""
    if not weather_data:
        return "dry"
    if (weather_data.get("precipitation_sum") or 0) > WET_PRECIPITATION_MM_THRESHOLD:
        return "wet"
    if (weather_data.get("wind_speed_10m_max") or 0) > WINDY_WIND_SPEED_KMH_THRESHOLD:
        return "windy"
    return "dry"
