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

from .union_registry import UNION_REGISTRY
from .wikipedia_squad import USER_AGENT, fetch_wikitext

LOGO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "web", "logos")

# code -> Wikipedia page title for that union's national team article.
# Derived from `union_registry.UNION_REGISTRY` (the single source of truth
# for a union's Wikipedia page title, plus which unions this specific dict
# covers - 6 Rugby Europe Championship unions are deliberately excluded,
# `has_logo_page=False`, unverified whether their pages expose a `Badge=`
# field) - same contents as the hand-written dict this replaced. Mirrors
# `pool_builder.ALL_TEAM_IDS`/`NATION_DISPLAY` naming, plus the two
# Wikipedia-only 2027-draw unions and the Barbarians/Lions/Pacific
# Islanders (direct Commons files, not a national-team infobox, since
# they're invitational sides - see below).
TEAM_LOGO_PAGES: Dict[str, str] = {
    e.code: e.wiki_page_title for e in UNION_REGISTRY
    if e.wiki_page_title and e.has_logo_page
}

# A handful of historical nation names (pre-current naming/branding) that
# should visually fall back to today's equivalent union's crest.
HISTORICAL_NATION_ALIASES: Dict[str, str] = {
    "Western Samoa": "Samoa",
}

_BADGE_FIELD_RE = re.compile(r"\|\s*Badge\s*=\s*([^\n|]+)")

_BARBARIANS_FILE = "Barbarians.png"  # resolved directly via Commons, see fetch_team_logo("BAR")
# Same direct-Commons-file approach as the Barbarians - both the Lions and
# the Pacific Islanders use a different infobox template
# (`{{Infobox rugby team}}`'s `image=` field) than a national team's own
# `{{Infobox national rugby team}}`'s `Badge=` field, so these are pinned
# directly rather than parsed from the page (confirmed live - see
# `invitational_squads.py`'s own docstrings for the exact pages checked).
_LIONS_FILE = "British & Irish Lions logo (2023).svg"
_PACIFIC_ISLANDERS_FILE = "pacificislanderrugbylogo.JPG"


def _clean_filename(raw: str) -> str:
    name = raw.strip()
    name = re.sub(r"\{\{.*$", "", name).strip()  # drop any trailing template noise
    if name.lower().startswith("file:"):
        name = name[5:].strip()
    return name


def _extract_badge_filename(nation_code: str) -> Optional[str]:
    if nation_code == "BAR":
        return _BARBARIANS_FILE
    if nation_code == "LIO":
        return _LIONS_FILE
    if nation_code == "PAC":
        return _PACIFIC_ISLANDERS_FILE
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


#: `upload.wikimedia.org` (the raw image CDN, as opposed to the `api.php`
#: endpoints) was confirmed live to return a hard 429 specifically for the
#: plain `USER_AGENT` string every other fetch in this project uses
#: unmodified (even after waiting and retrying) - it wants something that
#: looks more like a normal browser/compliant client. This is used ONLY for
#: the raw image-byte download below, not for any `api.php`/wikitext call
#: (those keep using the shared `USER_AGENT` unchanged, since they were
#: never the problem).
_IMAGE_DOWNLOAD_USER_AGENT = (
    "Mozilla/5.0 (compatible; what-if-rugby-edition/0.1; "
    "+https://github.com/example/what-if-rugby-edition)"
)


def _request_with_backoff(url: str, as_json: bool):
    """Same 429-aware retry convention as `wikipedia_squad.fetch_wikitext` -
    this module hits the same API, so it's just as rate-limit-prone."""
    agent = USER_AGENT if as_json else _IMAGE_DOWNLOAD_USER_AGENT
    req = urllib.request.Request(url, headers={"User-Agent": agent})
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


def _ensure_png(content: bytes) -> bytes:
    """MediaWiki's `iiurlwidth` thumbnail API only ever RESIZES a raster
    image - it never changes format, so a source file that's already a
    JPEG (confirmed live for the Pacific Islanders' crest, a `.JPG` upload,
    unlike every other team's SVG badge) comes back as JPEG bytes even
    though this cache always saves to a `<code>.png` path. Re-encodes to a
    real PNG here (via Pillow, already a project dependency - see
    `favicon.py`) so the on-disk file's bytes actually match its
    extension; a no-op (bytes already real PNG, e.g. a rasterized SVG)
    just gets handed back unchanged."""
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return content
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(content)) as img:
        out = BytesIO()
        img.convert("RGBA").save(out, format="PNG")
        return out.getvalue()


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
                    return _ensure_png(content)
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
    for code in list(TEAM_LOGO_PAGES.keys()) + ["BAR", "LIO", "PAC"]:
        path = get_logo_path(code)
        results[code] = bool(path)
    return results


def resolve_logo_code(nation_name_or_code: str) -> Optional[str]:
    """Best-effort: given either a union code (already correct) or a real
    nation display name (as historical squads use, e.g. "South Africa",
    "Western Samoa"), returns the code to use for a logo lookup."""
    if nation_name_or_code in TEAM_LOGO_PAGES or nation_name_or_code in ("BAR", "LIO", "PAC"):
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
