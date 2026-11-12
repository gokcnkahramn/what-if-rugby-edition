import os

from rugby_sim.data.sources.team_logos import LOGO_DIR, TEAM_LOGO_PAGES, resolve_logo_code
from rugby_sim.webapp import app

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_cached_logos_are_valid_pngs():
    """Doesn't hit the network - just checks whatever's already cached in
    `web/logos/` (populated by `python -m rugby_sim.data.sources.team_logos`)
    is really a PNG, not an error page or a truncated download."""
    assert os.path.isdir(LOGO_DIR), "no logos cached - run `python -m rugby_sim.data.sources.team_logos` first"
    codes = list(TEAM_LOGO_PAGES.keys()) + ["BAR"]
    cached = [c for c in codes if os.path.exists(os.path.join(LOGO_DIR, f"{c}.png"))]
    assert len(cached) >= 20, f"expected most unions to have a cached logo, only found {cached}"
    for code in cached:
        with open(os.path.join(LOGO_DIR, f"{code}.png"), "rb") as f:
            assert f.read(8) == PNG_MAGIC, f"{code}.png isn't a real PNG"


def test_resolve_logo_code_handles_historical_aliases():
    assert resolve_logo_code("ENG") == "ENG"
    assert resolve_logo_code("South Africa") == "RSA"
    assert resolve_logo_code("Western Samoa") == "SAM"  # historical alias -> current union


def test_api_logos_endpoint_matches_disk_cache():
    client = app.test_client()
    res = client.get("/api/logos")
    assert res.status_code == 200
    data = res.get_json()
    assert "logos" in data and "name_to_code" in data
    for code, url in data["logos"].items():
        assert url == f"/logos/{code}.png"
        static_res = client.get(url)
        assert static_res.status_code == 200
        assert static_res.data[:8] == PNG_MAGIC
