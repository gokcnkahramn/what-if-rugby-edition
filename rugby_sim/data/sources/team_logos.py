"""Real team crests (PNG, transparent background) for the web UI, pulled
straight from each national team's own Wikipedia infobox - not invented,
not a generic placeholder.

How: every national-team Wikipedia page's `{{Infobox national rugby team}}`
has a `Badge = <File name>.svg|png` field (confirmed live across Tier 1,
Tier 2, Hong Kong/Zimbabwe). Whatever that file is - usually an SVG - is
resolved to a transparent-background PNG thumbnail via MediaWiki's own
imageinfo API (`iiurlwidth=`), which rasterizes an SVG's alpha channel
faithfully; no re-encoding or background-fill is done on our side. Results
are cached to disk (`rugby_sim/web/logos/<code>.png`) so this is a one-time
network cost per team, same convention as every other Wikipedia-sourced
pipeline in this project.

Historical-year squads reuse the *current* crest for that union - most
federation logos have been stable for decades, and sourcing a specific
historical year's exact logo for 20+ teams across 8 World Cup editions
isn't something Wikipedia's current-squad infobox gives us for free (that
would need a dedicated per-year image search per team, undocumented and
unverifiable at this scale) - this is a known, intentional simplification,
not silently papered over.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Dict, Optional

from .wikipedia_squad import USER_AGENT, fetch_wikitext

LOGO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "web", "logos")

# code -> Wikipedia page title for that union's national team article.
# Mirrors `pool_builder.ALL_TEAM_IDS`/`NATION_DISPLAY` naming, plus the two
# Wikipedia-only 2027-draw unions and the Barbarians (a direct Commons file,
# not a national-team infobox, since they're an invitational club side).
TEAM_LOGO_PAGES: Dict[str, str] = {
    "ENG": "England national rugby union team",
    "FRA": "France national rugby union team",
    "IRE": "Ireland national rugby union team",
    "SCO": "Scotland national rugby union team",
    "WAL": "Wales national rugby union team",
    "ITA": "Italy national rugby union team",
    "NZL": "New Zealand national rugby union team",
    "AUS": "Australia national rugby union team",
    "RSA": "South Africa national rugby union team",
    "ARG": "Argentina national rugby union team",
    "JPN": "Japan national rugby union team",
    "FIJ": "Fiji national rugby union team",
    "GEO": "Georgia national rugby union team",
    "ROU": "Romania national rugby union team",
    "ESP": "Spain national rugby union team",
    "POR": "Portugal national rugby union team",
    "SAM": "Samoa national rugby union team",
    "TGA": "Tonga national rugby union team",
    "USA": "United States national rugby union team",
    "CAN": "Canada national rugby union team",
    "URU": "Uruguay national rugby union team",
    "CHI": "Chile national rugby union team",
    "NAM": "Namibia national rugby union team",
    "HKG": "Hong Kong national rugby union team",
    "ZIM": "Zimbabwe national rugby union team",
}

# A handful of historical nation names (pre-current naming/branding) that
# should visually fall back to today's equivalent union's crest.
HISTORICAL_NATION_ALIASES: Dict[str, str] = {
    "Western Samoa": "Samoa",
}

_BADGE_FIELD_RE = re.compile(r"\|\s*Badge\s*=\s*([^\n|]+)")

_BARBARIANS_FILE = "Barbarians.png"  # resolved directly via Commons, see fetch_team_logo("BAR")


def _clean_filename(raw: str) -> str:
    name = raw.strip()
    name = re.sub(r"\{\{.*$", "", name).strip()  # drop any trailing template noise
    if name.lower().startswith("file:"):
        name = name[5:].strip()
    return name


def _extract_badge_filename(nation_code: str) -> Optional[str]:
    if nation_code == "BAR":
        return _BARBARIANS_FILE
    title = TEAM_LOGO_PAGES.get(nation_code)
    if not title:
        return None
    wikitext = fetch_wikitext(title)
    if not wikitext:
        return None
    m = _BADGE_FIELD_RE.search(wikitext)
    if not m:
        return None
    return _clean_filename(m.group(1))


def _request_with_backoff(url: str, as_json: bool):
    """Same 429-aware retry convention as `wikipedia_squad.fetch_wikitext` -
    this module hits the same API, so it's just as rate-limit-prone."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
            time.sleep(1)  # politeness delay between live calls
            return json.loads(raw.decode("utf-8")) if as_json else raw
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                time.sleep(8 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    return None


def _get_json(url: str) -> Optional[dict]:
    return _request_with_backoff(url, as_json=True)


def _get_bytes(url: str) -> Optional[bytes]:
    return _request_with_backoff(url, as_json=False)


def _fetch_thumbnail_png(filename: str, width: int = 240) -> Optional[bytes]:
    """Resolves a Commons/enwiki file name to a rasterized PNG thumbnail
    (transparent where the source has alpha) via MediaWiki's own imageinfo
    API - tries Commons first (where most team badges actually live), then
    enwiki, since a `File:` reference is resolved per-wiki."""
    import urllib.parse

    for api_base in ("https://commons.wikimedia.org/w/api.php", "https://en.wikipedia.org/w/api.php"):
        params = urllib.parse.urlencode({
            "action": "query", "titles": f"File:{filename}", "prop": "imageinfo",
            "iiprop": "url", "iiurlwidth": width, "format": "json",
        })
        try:
            data = _get_json(f"{api_base}?{params}")
        except Exception:
            continue
        if not data:
            continue
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            if "missing" in page:
                continue
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            url = infos[0].get("thumburl") or infos[0].get("url")
            if not url:
                continue
            try:
                content = _get_bytes(url)
                if content:
                    return content
            except Exception:
                continue
    return None


def get_logo_path(nation_code: str) -> Optional[str]:
    """Returns the on-disk path to this union's cached PNG crest, fetching
    and rasterizing it on first use. Returns None if no badge could be
    resolved (never raises - a missing logo just means the UI falls back
    to no image, not a broken page)."""
    os.makedirs(LOGO_DIR, exist_ok=True)
    cache_path = os.path.join(LOGO_DIR, f"{nation_code}.png")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return cache_path

    filename = _extract_badge_filename(nation_code)
    if not filename:
        return None
    content = _fetch_thumbnail_png(filename)
    if not content:
        return None
    with open(cache_path, "wb") as f:
        f.write(content)
    return cache_path


def fetch_all_logos() -> Dict[str, bool]:
    """Pre-fetches every known union's crest to disk - run once
    (`python -m rugby_sim.data.sources.team_logos`) so the web UI never
    hits Wikipedia live on a page load; `/api/logos` only reports what's
    already cached. Safe to re-run - cached files are skipped."""
    results = {}
    for code in list(TEAM_LOGO_PAGES.keys()) + ["BAR"]:
        path = get_logo_path(code)
        results[code] = bool(path)
    return results


def resolve_logo_code(nation_name_or_code: str) -> Optional[str]:
    """Best-effort: given either a union code (already correct) or a real
    nation display name (as historical squads use, e.g. "South Africa",
    "Western Samoa"), returns the code to use for a logo lookup."""
    if nation_name_or_code in TEAM_LOGO_PAGES or nation_name_or_code in ("BAR",):
        return nation_name_or_code
    aliased = HISTORICAL_NATION_ALIASES.get(nation_name_or_code, nation_name_or_code)
    from .pool_builder import NATION_TO_CODE
    return NATION_TO_CODE.get(aliased)


if __name__ == "__main__":
    results = fetch_all_logos()
    ok = [c for c, found in results.items() if found]
    fail = [c for c, found in results.items() if not found]
    print(f"Logos cached: {len(ok)}/{len(results)}")
    if fail:
        print(f"No badge found (no logo for these - not an error): {', '.join(fail)}")
