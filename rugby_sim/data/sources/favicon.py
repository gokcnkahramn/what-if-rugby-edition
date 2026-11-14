"""The browser-tab favicon: a real illustration of the Webb Ellis Cup (the
Rugby World Cup trophy), transparent background - not a generic icon.

Source: Wikimedia Commons `File:Rugby World Trophy.svg` (CC BY-SA 2.5, by
"F l a n k e r"), resolved to a transparent PNG via MediaWiki's own
imageinfo API - the exact same rasterize-an-SVG-preserving-alpha approach
`team_logos.py` already uses. The source SVG has a lot of empty canvas
above the trophy (it's drawn low in its own viewbox), so this crops to the
alpha channel's real bounding box and pads back to a square before
generating the final `.ico`/`.png` - otherwise the trophy would render as
a near-invisible speck at 16x16.

Run once (`python -m rugby_sim.data.sources.favicon`) to (re-)generate
`rugby_sim/web/favicon.ico` and `rugby_sim/web/favicon-180.png` - both are
committed, ordinary static files, not fetched per request.
"""

from __future__ import annotations

import os

from .team_logos import _get_bytes, _get_json

WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "web")

SOURCE_FILENAME = "Rugby World Trophy.svg"
LICENSE = "CC BY-SA 2.5"
AUTHOR = "F l a n k e r"


def _fetch_trophy_png(width: int = 512) -> bytes:
    import urllib.parse

    params = urllib.parse.urlencode({
        "action": "query", "titles": f"File:{SOURCE_FILENAME}", "prop": "imageinfo",
        "iiprop": "url", "iiurlwidth": width, "format": "json",
    })
    data = _get_json(f"https://commons.wikimedia.org/w/api.php?{params}")
    if not data:
        raise RuntimeError("could not resolve the trophy SVG on Commons")
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        url = infos[0].get("thumburl") or infos[0].get("url")
        if url:
            content = _get_bytes(url)
            if content:
                return content
    raise RuntimeError("no thumbnail URL found for the trophy SVG")


def generate_favicon() -> None:
    from PIL import Image
    import io

    raw = _fetch_trophy_png(width=512)
    im = Image.open(io.BytesIO(raw)).convert("RGBA")

    alpha = im.split()[-1]
    bbox = alpha.getbbox()
    cropped = im.crop(bbox) if bbox else im

    w, h = cropped.size
    side = max(w, h)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(cropped, ((side - w) // 2, (side - h) // 2), cropped)

    os.makedirs(WEB_DIR, exist_ok=True)
    square.save(os.path.join(WEB_DIR, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    square.resize((180, 180), Image.LANCZOS).save(os.path.join(WEB_DIR, "favicon-180.png"))


if __name__ == "__main__":
    generate_favicon()
    print("favicon.ico + favicon-180.png written to rugby_sim/web/")
