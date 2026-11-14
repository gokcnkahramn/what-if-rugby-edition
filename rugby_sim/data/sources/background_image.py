"""Real, freely-licensed rugby stadium photos for the web UI's blurred
background (the "Rugby 08 / Football Manager menu" look the user asked
for) - not invented, not a stock-photo site, and not a real player's
likeness (every image here is a wide stadium/architecture shot, deliberately
chosen over any close-up action photo to sidestep any individual's image
rights - only the venue is depicted).

Each entry is a specific Wikimedia Commons file, picked by hand and checked
live for an actual free license (`CC BY`/`CC BY-SA`) via the same
`imageinfo` MediaWiki API `team_logos.py` already uses - never assumed.
Every one of these licenses requires attribution, so `BACKGROUND_IMAGES`
carries the real photographer/author and license name, and the web UI's
footer shows it (see `rugby_sim/web/app.js`'s `renderBackgroundAttribution`).

Results are cached to disk (`rugby_sim/web/backgrounds/<key>.jpg`) exactly
like `team_logos.py`'s crests - a one-time network cost, offline after.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional

from .wikipedia_squad import USER_AGENT
from .team_logos import _get_bytes, _get_json  # same 429-aware backoff request helpers

BACKGROUND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "web", "backgrounds")


@dataclass
class BackgroundImage:
    key: str
    commons_filename: str  # exact Commons "File:" title, without the "File:" prefix
    caption: str           # what the photo shows, for the attribution line
    license: str           # e.g. "CC BY-SA 2.0" - confirmed live, not assumed
    author: str            # photographer/uploader, as Commons' own metadata credits them


# Hand-picked, license-checked (see module docstring) - wide stadium shots
# only, no recognizable individual in a close-up. More can be added the same
# way: find a file in a stadium's Commons category, confirm its
# `extmetadata.LicenseShortName` is a real CC license before adding it here.
#
# This set is specifically each of the top-10 World Rugby-ranked unions'
# home stadium, picked by the user from a real ranking snapshot (Steady
# rankings: South Africa, New Zealand, Ireland, France, England, Scotland,
# Australia, Argentina, Fiji, Wales) - not an arbitrary pick of famous
# grounds, that specific top-10.
BACKGROUND_IMAGES: Dict[str, BackgroundImage] = {
    "ellis_park": BackgroundImage(
        key="ellis_park",
        commons_filename="Ellis Park Stadium.jpg",
        caption="Ellis Park Stadium, South Africa",
        license="CC BY-SA 2.0",
        author="Leglo09",
    ),
    "eden_park": BackgroundImage(
        key="eden_park",
        commons_filename="Aerial view of Eden Park, Auckland.jpg",
        caption="Eden Park, Auckland, New Zealand",
        license="CC BY 2.0",
        author="Archives New Zealand",
    ),
    "aviva_stadium": BackgroundImage(
        key="aviva_stadium",
        commons_filename="Avia Stadion Dublin Irland (126472271).jpeg",
        caption="Aviva Stadium, Dublin, Ireland",
        license="CC BY 3.0",
        author="Dronepicr",
    ),
    "stade_de_france": BackgroundImage(
        key="stade_de_france",
        commons_filename="DS051217164517 (80184068).jpg",
        caption="Stade de France, Saint-Denis, France",
        license="CC BY-SA 2.0",
        author="ketou-daisuki from Kyoto",
    ),
    "twickenham": BackgroundImage(
        key="twickenham",
        commons_filename="Twickenham Stadium - geograph.org.uk - 6461867.jpg",
        caption="Twickenham Stadium, England",
        license="CC BY-SA 2.0",
        author="N Chadwick, via Geograph Britain and Ireland",
    ),
    "murrayfield": BackgroundImage(
        key="murrayfield",
        commons_filename="A view of Murrayfield Stadium, Edinburgh.JPG",
        caption="Murrayfield Stadium, Edinburgh, Scotland",
        license="CC BY-SA 3.0",
        author="Northmetpit",
    ),
    "anz_stadium_australia": BackgroundImage(
        key="anz_stadium_australia",
        commons_filename="Clouds hovering over ANZ Stadium (6801238345).jpg",
        caption="Accor (ANZ) Stadium, Sydney, Australia",
        license="CC BY 2.0",
        author="vijay chennupati, Sydney",
    ),
    "velez_sarsfield": BackgroundImage(
        key="velez_sarsfield",
        commons_filename="Vélez Sarsfield Stadium (451476778).jpg",
        caption="Estadio José Amalfitani (Vélez Sarsfield), Buenos Aires, Argentina",
        license="CC BY-SA 2.0",
        author="Beatrice Murch",
    ),
    "anz_stadium_fiji": BackgroundImage(
        key="anz_stadium_fiji",
        commons_filename="ANZ Stadium Fiji.jpg",
        caption="HFC Bank (ANZ) Stadium, Suva, Fiji",
        license="CC BY-SA 3.0",
        author="Stemoc",
    ),
    "principality_stadium": BackgroundImage(
        key="principality_stadium",
        commons_filename='"Principality" Stadium, Cardiff, Wales - geograph.org.uk - 5895691.jpg',
        caption="Principality Stadium, Cardiff, Wales",
        license="CC BY-SA 2.0",
        author="David Hallam-Jones, via Geograph Britain and Ireland",
    ),
}


def _fetch_commons_jpeg(filename: str, width: int = 1600) -> Optional[bytes]:
    params = urllib.parse.urlencode({
        "action": "query", "titles": f"File:{filename}", "prop": "imageinfo",
        "iiprop": "url", "iiurlwidth": width, "format": "json",
    })
    data = _get_json(f"https://commons.wikimedia.org/w/api.php?{params}")
    if not data:
        return None
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
        return _get_bytes(url)
    return None


def get_background_path(key: str) -> Optional[str]:
    """Disk path to this background's cached JPEG, fetching it on first use.
    Returns None (never raises) if the key is unknown or the fetch failed -
    the web UI just falls back to no photo (plain gradient) in that case."""
    entry = BACKGROUND_IMAGES.get(key)
    if entry is None:
        return None
    os.makedirs(BACKGROUND_DIR, exist_ok=True)
    cache_path = os.path.join(BACKGROUND_DIR, f"{key}.jpg")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return cache_path
    content = _fetch_commons_jpeg(entry.commons_filename)
    if not content:
        return None
    with open(cache_path, "wb") as f:
        f.write(content)
    return cache_path


def fetch_all_backgrounds() -> Dict[str, bool]:
    """Pre-fetches every known background photo to disk - run once
    (`python -m rugby_sim.data.sources.background_image`)."""
    return {key: bool(get_background_path(key)) for key in BACKGROUND_IMAGES}


if __name__ == "__main__":
    results = fetch_all_backgrounds()
    ok = [k for k, found in results.items() if found]
    fail = [k for k, found in results.items() if not found]
    print(f"Backgrounds cached: {len(ok)}/{len(results)}")
    if fail:
        print(f"Failed (network issue or file moved - not expected): {', '.join(fail)}")
