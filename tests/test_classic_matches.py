import json

import pytest

from rugby_sim import webapp
from rugby_sim.data.classic_matches import (
    CLASSIC_MATCHES,
    group_by_tournament,
    no_cards,
    player_tries_at_least,
    resolve_pools,
    team_drop_goals_at_least,
    team_tries_at_least,
    total_points_at_least,
    win,
    win_margin_at_least,
)
from rugby_sim.engine.match_engine import MatchResult, PlayerMatchStats, TeamMatchStats
from rugby_sim.models import Player, Position, Team
from rugby_sim.models.attributes import Attributes


def _client():
    webapp.app.config["TESTING"] = True
    return webapp.app.test_client()


# ---------------------------------------------------------------------------
# Catalog shape
# ---------------------------------------------------------------------------

def test_catalog_has_tier_a_plus_tier_b_entries():
    # 25 Tier-A (2018+/RWC) + 44 Tier-B (pre-2018 Six/Five Nations and
    # Tri Nations/Rugby Championship - 1996 Tri Nations was skipped, no
    # verifiable real lineup found for the researched scoreline/date) +
    # 8 additional RWC semi-final/final-knockout classics
    # (1995/1999/2003/2007/2011/2015/2019/2023) + 4 additional RWC
    # pool-stage upset classics (2007 x2, 2011, 2023) + 6 additional Six
    # Nations classics (2018/2019 Calcutta Cups, 2022/2024 Italy upsets,
    # 2025 England-France, 2026 Wales-Scotland) + 3 additional Rugby
    # Championship classics (2018 Salta comeback, 2025 Argentina-NZ,
    # 2025 Australia-South Africa).
    assert len(CLASSIC_MATCHES) == 90


def test_catalog_ids_are_unique():
    ids = [m.id for m in CLASSIC_MATCHES]
    assert len(ids) == len(set(ids))


def test_group_by_tournament_counts_and_sorted_oldest_to_newest():
    groups = group_by_tournament()
    assert set(groups.keys()) == {"rwc", "six_nations", "rugby_championship"}
    assert len(groups["rwc"]) == 20
    assert len(groups["six_nations"]) == 38
    assert len(groups["rugby_championship"]) == 32
    for matches in groups.values():
        years = [m.year for m in matches]
        assert years == sorted(years)


def test_every_match_has_three_base_and_two_bonus_objectives():
    for match in CLASSIC_MATCHES:
        tiers = [o.tier for o in match.objectives]
        assert tiers.count("base") == 3
        assert tiers.count("bonus") == 2


def test_every_match_has_a_focus_team_matching_its_objectives():
    """`focus_team` must be "home" or "away", and must name the exact same
    team the match's own `win(...)` base objective is about - the
    objectives are written per-team from the start, so this should never
    be ambiguous (see classic_matches_tier_b_rugby_championship.py's
    convention of "home" always being the real winner, too)."""
    for match in CLASSIC_MATCHES:
        assert match.focus_team in ("home", "away")
        focus_name = match.home_name if match.focus_team == "home" else match.away_name
        win_objectives = [o for o in match.objectives if o.key.startswith("win:")]
        assert win_objectives, f"{match.id} has no win(...) objective to check focus_team against"
        win_team = win_objectives[0].key.split(":", 1)[1]
        assert win_team == focus_name, (
            f"{match.id}: focus_team={match.focus_team!r} ({focus_name}) doesn't match "
            f"its win objective's team ({win_team})"
        )


# ---------------------------------------------------------------------------
# Objective checkers - hand-built fake MatchResult, pass and fail cases
# ---------------------------------------------------------------------------

def _make_player(name: str, position: Position) -> Player:
    return Player(name=name, nation="Testland", natural_position=position, attributes=Attributes())


def _fake_result(score_home=20, score_away=10, drop_goals_home=0, tries_home=2,
                  yellow_home=0, red_home=0, injuries_home=0) -> MatchResult:
    home = Team(name="Home", short_code="HOM")
    away = Team(name="Away", short_code="AWY")
    result = MatchResult(home=home, away=away, score_home=score_home, score_away=score_away)
    result.stats["Home"] = TeamMatchStats(
        tries=tries_home, drop_goals=drop_goals_home,
        yellow_cards=yellow_home, red_cards=red_home, injuries=injuries_home,
    )
    result.stats["Away"] = TeamMatchStats(tries=1)
    wing = _make_player("Left Winger", Position.LEFT_WING)
    result.player_stats.append(PlayerMatchStats(player=wing, team="Home", tries=2, conversions=0, penalty_goals=0))
    return result


def test_win_checker():
    r = _fake_result(score_home=20, score_away=10)
    assert win("Home").check(r) is True
    assert win("Away").check(r) is False


def test_win_margin_checker():
    r = _fake_result(score_home=20, score_away=10)
    assert win_margin_at_least("Home", 5).check(r) is True
    assert win_margin_at_least("Home", 15).check(r) is False


def test_team_tries_checker():
    r = _fake_result(tries_home=4)
    assert team_tries_at_least("Home", 3).check(r) is True
    assert team_tries_at_least("Home", 10).check(r) is False


def test_team_drop_goals_checker():
    r = _fake_result(drop_goals_home=2)
    assert team_drop_goals_at_least("Home", 1).check(r) is True
    assert team_drop_goals_at_least("Home", 5).check(r) is False


def test_player_tries_checker():
    r = _fake_result()
    assert player_tries_at_least("Home", "Left Wing", 2).check(r) is True
    assert player_tries_at_least("Home", "Left Wing", 5).check(r) is False


def test_no_cards_checker():
    r_clean = _fake_result(yellow_home=0, red_home=0)
    r_carded = _fake_result(yellow_home=1, red_home=0)
    assert no_cards("Home").check(r_clean) is True
    assert no_cards("Home").check(r_carded) is False


def test_total_points_checker():
    r = _fake_result(score_home=20, score_away=10)
    assert total_points_at_least(25).check(r) is True
    assert total_points_at_least(40).check(r) is False


# ---------------------------------------------------------------------------
# Pool resolution - one RWC-tier, one Six-Nations-tier
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_resolve_pools_rwc_tier():
    match = next(m for m in CLASSIC_MATCHES if m.id == "rwc_2023_final")
    home_pool, away_pool = resolve_pools(match)
    assert home_pool and away_pool
    assert all(p.nation == match.home_name for p in home_pool)
    assert all(p.nation == match.away_name for p in away_pool)


@pytest.mark.slow
@pytest.mark.parametrize("match_id", [
    "rwc_1995_sf", "rwc_1999_sf_fra_nz", "rwc_2003_sf", "rwc_2007_sf",
    "rwc_2011_qf", "rwc_2015_qf", "rwc_2019_sf", "rwc_2023_qf",
    "rwc_2007_pool_arg_fra", "rwc_2007_pool_fij_wal",
    "rwc_2011_pool_ire_aus", "rwc_2023_pool_fij_aus",
])
def test_resolve_pools_new_rwc_classics(match_id):
    """Each new RWC classic's pool resolves to non-empty, real squads for
    its year (same `historical_rwc.get_rwc_year_data` mechanism already
    exercised by `test_resolve_pools_rwc_tier`)."""
    match = next(m for m in CLASSIC_MATCHES if m.id == match_id)
    home_pool, away_pool = resolve_pools(match)
    assert home_pool and away_pool
    assert all(p.nation == match.home_name for p in home_pool)
    assert all(p.nation == match.away_name for p in away_pool)


@pytest.mark.slow
def test_resolve_pools_six_nations_tier():
    match = next(m for m in CLASSIC_MATCHES if m.id == "six_nations_2026")
    home_pool, away_pool = resolve_pools(match)
    assert home_pool and away_pool


@pytest.mark.slow
@pytest.mark.parametrize("match_id", [
    "six_nations_2018_calcutta", "six_nations_2019_calcutta",
    "six_nations_2022_italy", "six_nations_2024_italy",
    "six_nations_2025_twickenham", "six_nations_2026_cardiff",
    "rugby_championship_2018_salta", "rugby_championship_2025_argentina_nz",
    "rugby_championship_2025_australia_rsa",
])
def test_resolve_pools_new_six_nations_and_rugby_championship_classics(match_id):
    """Each new 2018+ Six Nations/Rugby Championship classic's pool
    resolves to non-empty, real squads for its year/teams (same
    `pool_builder.build_union_pool` mechanism already exercised by
    `test_resolve_pools_six_nations_tier`)."""
    match = next(m for m in CLASSIC_MATCHES if m.id == match_id)
    home_pool, away_pool = resolve_pools(match)
    assert home_pool and away_pool
    assert all(p.nation == match.home_name for p in home_pool)
    assert all(p.nation == match.away_name for p in away_pool)


# ---------------------------------------------------------------------------
# Flask endpoints
# ---------------------------------------------------------------------------

def test_api_classic_matches_lists_grouped():
    client = _client()
    res = client.get("/api/classic_matches")
    assert res.status_code == 200
    data = res.get_json()
    assert data["mode"] in ("3", "5")
    assert set(data["tournaments"].keys()) == {"rwc", "six_nations", "rugby_championship"}
    assert len(data["tournaments"]["rwc"]) == 20


def test_api_classic_matches_lists_focus_team():
    client = _client()
    res = client.get("/api/classic_matches")
    data = res.get_json()
    for matches in data["tournaments"].values():
        for m in matches:
            assert m["focus_team"] in ("home", "away")


def test_api_classic_matches_settings_toggle():
    client = _client()
    res = client.post("/api/classic_matches/settings", json={"mode": "5"})
    assert res.status_code == 200
    assert res.get_json()["mode"] == "5"
    res2 = client.get("/api/classic_matches")
    assert res2.get_json()["mode"] == "5"
    # restore default for other tests
    client.post("/api/classic_matches/settings", json={"mode": "3"})


@pytest.mark.slow
def test_classic_matches_start_auto_drafts_the_non_focus_side():
    """rwc_2015_pool (the Brighton Miracle) has focus_team="home" (Japan) -
    its objectives are all about Japan. `/start` should hand back Japan's
    real pool for the user to draft (`focus`), and South Africa should
    already be auto-drafted into a registered, usable team (`auto`), same
    mechanism `auto_draft_team` uses for AI sides everywhere else."""
    client = _client()
    match = next(m for m in CLASSIC_MATCHES if m.id == "rwc_2015_pool")
    assert match.focus_team == "home"
    assert match.home_name == "Japan"

    start_res = client.post("/api/classic_matches/rwc_2015_pool/start")
    assert start_res.status_code == 200
    data = start_res.get_json()

    assert data["focus_team"] == "home"
    assert data["focus"]["name"] == "Japan"
    assert data["focus"]["pool"]

    assert data["auto"]["name"] == "South Africa"
    assert data["auto"]["team_id"]
    assert len(data["auto"]["lineup"]) == 15
    assert data["auto"]["problems"] == []  # a full, valid 15-player lineup


@pytest.mark.slow
def test_full_classic_match_flow_start_draft_live_complete():
    client = _client()

    start_res = client.post("/api/classic_matches/rwc_2015_pool/start")
    assert start_res.status_code == 200
    start_data = start_res.get_json()
    focus_ids = [p["id"] for p in start_data["focus"]["pool"]]
    assert focus_ids

    focus_team_res = client.post("/api/team/auto_from_ids", json={
        "name": "Japan", "player_ids": focus_ids, "code": "JPN",
    })
    assert focus_team_res.status_code == 200
    focus_team_id = focus_team_res.get_json()["team_id"]
    auto_team_id = start_data["auto"]["team_id"]

    # rwc_2015_pool's focus team (Japan) is the home side.
    home_team_id, away_team_id = focus_team_id, auto_team_id

    live_res = client.post("/api/match/live/start", json={
        "home_team_id": home_team_id, "away_team_id": away_team_id, "seed": 42,
    })
    assert live_res.status_code == 200
    session_id = live_res.get_json()["session_id"]

    finished = live_res.get_json()["finished"]
    while not finished:
        cont = client.post(f"/api/match/live/{session_id}/continue")
        assert cont.status_code == 200
        finished = cont.get_json()["finished"]

    complete_res = client.post(f"/api/classic_matches/rwc_2015_pool/complete", json={
        "session_id": session_id,
    })
    assert complete_res.status_code == 200
    complete_data = complete_res.get_json()
    assert 0 <= complete_data["stars"] <= complete_data["star_cap"]
    assert "objectives_passed" in complete_data
    assert "objectives_failed" in complete_data

    # progress persisted
    list_res = client.get("/api/classic_matches")
    rwc_entries = list_res.get_json()["tournaments"]["rwc"]
    entry = next(m for m in rwc_entries if m["id"] == "rwc_2015_pool")
    assert entry["best_stars"] == complete_data["best_stars"]


# ---------------------------------------------------------------------------
# Persistence file round-trip
# ---------------------------------------------------------------------------

def test_progress_file_round_trips_and_defaults_sanely(tmp_path, monkeypatch):
    fake_path = tmp_path / "classic_match_progress.json"
    monkeypatch.setattr(webapp, "_CLASSIC_PROGRESS_PATH", fake_path)

    # missing file -> sane defaults
    progress = webapp._load_classic_progress()
    assert progress == {"mode": "3", "completed": {}}

    progress["mode"] = "5"
    progress["completed"]["rwc_1995_final"] = {"stars": 4, "objectives_passed": ["win:South Africa"]}
    webapp._save_classic_progress(progress)

    assert fake_path.exists()
    reread = webapp._load_classic_progress()
    assert reread == progress
