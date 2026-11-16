"""Tests for 12d: the uncapped/eligible-but-never-capped club player pool
(`rugby_sim/data/sources/uncapped_pool.py`). Parser test runs against real
fetched (disk-cached) Wikipedia wikitext, same convention as the rest of
this project's Wikipedia-backed tests - no invented fixtures."""

from rugby_sim import webapp
from rugby_sim.data.sources.pool_builder import build_season_pool
from rugby_sim.data.sources.uncapped_pool import (
    SUPER_RUGBY_TEAM_TITLES,
    _parse_senior_squad,
    _parse_super_rugby_team_names,
    build_uncapped_pool,
    fetch_league_club_names,
    fetch_super_rugby_club_titles,
)
from rugby_sim.data.sources.wikipedia_squad import fetch_wikitext


def test_parse_senior_squad_leicester_real_wikitext():
    wikitext = fetch_wikitext("Leicester Tigers")
    assert wikitext, "expected to fetch Leicester Tigers wikitext (live or disk-cached)"
    entries = _parse_senior_squad(wikitext)
    assert entries, "expected to parse at least one squad entry"
    names = {e["name"] for e in entries}
    # Freddie Steward is a well-known, long-capped England fullback - must
    # show up as capped, never in the uncapped pool.
    steward = next(e for e in entries if e["name"] == "Freddie Steward")
    assert steward["capped"] is True
    assert steward["nat"] == "ENG"
    assert names, entries


def test_build_uncapped_pool_england_real_players_and_scoping():
    pool = build_uncapped_pool("ENG", "England")
    assert pool, "expected at least one uncapped England player from covered clubs"
    for p in pool:
        assert p.nation == "England"
        assert p.data_source in ("uncapped_wikipedia", "uncapped_wikipedia_archetype")
        assert "capped" in p.notes.lower()
    # Known current England internationals must NOT appear in the uncapped pool.
    names = {p.name for p in pool}
    assert "Freddie Steward" not in names
    assert "Ollie Chessum" not in names


def test_build_uncapped_pool_unsupported_union_returns_empty():
    # Honest scope limit - no silent guessing for a union not in
    # `UNION_STRENGTH` (this project's list of fully-supported unions).
    assert build_uncapped_pool("NZL_NOT_A_REAL_CODE", "Nowhere") == []


def test_build_uncapped_pool_italy_covered_via_urc():
    # 12e: Italy has no CLUB_PAGES entry of its own, but IS now covered
    # via its two United Rugby Championship clubs (Benetton, Zebre Parma).
    pool = build_uncapped_pool("ITA", "Italy")
    assert pool, "expected at least one uncapped Italy player via URC clubs"
    for p in pool:
        assert p.nation == "Italy"


def test_fetch_league_club_names_real_wikitext():
    # Live/disk-cached parse of each league season page's "Teams" table.
    premiership = fetch_league_club_names("premiership")
    assert "Leicester Tigers" in premiership
    assert len(premiership) >= 8

    top14 = fetch_league_club_names("top14")
    assert "Stade Toulousain" in top14
    assert len(top14) >= 10

    urc = fetch_league_club_names("urc")
    assert "Leinster Rugby" in urc
    assert len(urc) >= 12


def test_parse_super_rugby_team_names_real_wikitext():
    from rugby_sim.data.sources.uncapped_pool import SUPER_RUGBY_SEASON_PAGE
    wikitext = fetch_wikitext(SUPER_RUGBY_SEASON_PAGE)
    assert wikitext, "expected to fetch the Super Rugby Pacific season page (live or disk-cached)"
    names = _parse_super_rugby_team_names(wikitext)
    assert set(names) == set(SUPER_RUGBY_TEAM_TITLES.keys())
    assert len(names) == 11


def test_fetch_super_rugby_club_titles_real_wikitext():
    titles = fetch_super_rugby_club_titles()
    assert "ACT Brumbies" in titles
    assert "Fijian Drua" in titles
    assert "Crusaders (rugby union)" in titles
    assert len(titles) == 11


def test_build_uncapped_pool_nzl_aus_fij_via_super_rugby():
    # 13a: Super Rugby Pacific clubs now unlock NZL/AUS/FIJ the same way
    # Premiership/Top14/URC unlock ENG/FRA/IRE/SCO/WAL/ITA/RSA.
    for code, name in (("NZL", "New Zealand"), ("AUS", "Australia"), ("FIJ", "Fiji")):
        pool = build_uncapped_pool(code, name)
        assert pool, f"expected at least one uncapped {name} player via Super Rugby Pacific clubs"
        for p in pool:
            assert p.nation == name
            assert p.data_source in ("uncapped_wikipedia", "uncapped_wikipedia_archetype")


def test_build_uncapped_pool_covers_more_unions_than_the_original_two():
    # Before 12e this module only ever returned players for ENG/FRA.
    covered = [
        code for code in ("ENG", "FRA", "IRE", "SCO", "WAL", "ITA", "RSA")
        if build_uncapped_pool(code, code)
    ]
    assert set(covered) >= {"ENG", "FRA", "IRE", "SCO", "WAL", "ITA", "RSA"}


def test_build_season_pool_include_uncapped_dedupes_against_capped():
    capped = build_season_pool("ENG", 2026, include_uncapped=False)
    merged = build_season_pool("ENG", 2026, include_uncapped=True)
    assert len(merged) >= len(capped)

    capped_names = {p.name.strip().lower() for p in capped}
    merged_names = [p.name.strip().lower() for p in merged]
    # No duplicate names in the merged pool.
    assert len(merged_names) == len(set(merged_names))
    # Every capped player is still present, with their capped data_source
    # (never shadowed by an uncapped_wikipedia entry of the same name).
    for p in merged:
        if p.name.strip().lower() in capped_names:
            assert p.data_source != "uncapped_wikipedia"
            assert p.data_source != "uncapped_wikipedia_archetype"


def test_season_start_endpoint_include_uncapped_returns_separate_list():
    webapp.app.config["TESTING"] = True
    client = webapp.app.test_client()

    plain = client.post("/api/season/start", json={"nation_code": "ENG", "year": 2026})
    assert plain.status_code == 200
    assert plain.get_json()["uncapped_pool"] == []

    with_uncapped = client.post(
        "/api/season/start", json={"nation_code": "ENG", "year": 2026, "include_uncapped": True},
    )
    assert with_uncapped.status_code == 200
    data = with_uncapped.get_json()
    assert len(data["uncapped_pool"]) > 0
    pool_names = {p["name"] for p in data["pool"]}
    uncapped_names = {p["name"] for p in data["uncapped_pool"]}
    # Clearly separate, never silently merged into the main pool.
    assert pool_names.isdisjoint(uncapped_names)
    for p in data["uncapped_pool"]:
        assert p["data_source"].startswith("uncapped_wikipedia")
