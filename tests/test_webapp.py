from rugby_sim import webapp


def _client():
    webapp.app.config["TESTING"] = True
    return webapp.app.test_client()


def test_positions_and_unions_endpoints():
    client = _client()
    assert client.get("/api/positions").get_json()
    unions = client.get("/api/unions").get_json()
    codes = {u["code"] for u in unions}
    assert "ENG" in codes and "BAR" in codes


def test_build_team_and_play_a_match_end_to_end():
    client = _client()
    pool = client.get("/api/pool/ENG?season=2026").get_json()
    positions = client.get("/api/positions").get_json()

    used = set()
    slots = {}
    for pos in positions:
        candidates = [p["id"] for p in pool if p["id"] not in used]
        ranked = client.post("/api/rank", json={"player_ids": candidates, "position": pos}).get_json()
        best = ranked[0]
        slots[pos] = best["id"]
        used.add(best["id"])

    home_res = client.post("/api/team", json={
        "name": "England", "slots": slots, "captain": list(slots.values())[0], "bench": [],
    }).get_json()
    assert home_res["problems"] == []

    pool2 = client.get("/api/pool/FRA?season=2026").get_json()
    used2 = set()
    slots2 = {}
    for pos in positions:
        candidates = [p["id"] for p in pool2 if p["id"] not in used2]
        ranked = client.post("/api/rank", json={"player_ids": candidates, "position": pos}).get_json()
        best = ranked[0]
        slots2[pos] = best["id"]
        used2.add(best["id"])
    away_res = client.post("/api/team", json={
        "name": "France", "slots": slots2, "captain": list(slots2.values())[0], "bench": [],
    }).get_json()
    assert away_res["problems"] == []

    match = client.post("/api/match", json={
        "home_team_id": home_res["team_id"], "away_team_id": away_res["team_id"], "seed": 1,
    }).get_json()
    assert "scoreline" in match
    assert len(match["events"]) > 0
    assert "England" in match["stats"] and "France" in match["stats"]


def _build_minimal_team(client, code, name):
    pool = client.get(f"/api/pool/{code}?season=2026").get_json()
    positions = client.get("/api/positions").get_json()
    used, slots = set(), {}
    for pos in positions:
        candidates = [p["id"] for p in pool if p["id"] not in used]
        ranked = client.post("/api/rank", json={"player_ids": candidates, "position": pos}).get_json()
        best = ranked[0]
        slots[pos] = best["id"]
        used.add(best["id"])
    res = client.post("/api/team", json={
        "name": name, "slots": slots, "captain": list(slots.values())[0], "bench": [],
    }).get_json()
    return res["team_id"]


def test_auto_draft_team_endpoint():
    client = _client()
    res = client.post("/api/team/auto", json={"name": "Ireland (auto)", "code": "IRE"}).get_json()
    assert res["problems"] == []
    assert len(res["slots"]) == 15
    assert res["code"] == "IRE"


def test_auto_draft_team_endpoint_resolves_code_from_nation_name():
    client = _client()
    res = client.post("/api/team/auto", json={"name": "Wales"}).get_json()
    assert res["problems"] == []
    assert res["code"] == "WAL"


def test_tournament_match_results_are_drillable_into_full_detail():
    client = _client()
    team_ids = {
        "A": _build_minimal_team(client, "ENG", "A"),
        "B": _build_minimal_team(client, "FRA", "B"),
        "C": _build_minimal_team(client, "IRE", "C"),
        "D": _build_minimal_team(client, "WAL", "D"),
    }
    report = client.post("/api/tournament/run", json={
        "type": "custom", "team_ids": team_ids, "format": "round_robin", "seed": 1,
    }).get_json()

    assert report["results"]
    for row in report["results"]:
        assert "match_id" in row

    match_id = report["results"][0]["match_id"]
    detail = client.get(f"/api/match/{match_id}").get_json()
    assert detail["scoreline"] == report["results"][0]["scoreline"]
    assert len(detail["events"]) > 0
    assert "stats" in detail

    assert client.get("/api/match/not-a-real-id").status_code == 404


def test_custom_tournament_round_robin_via_api():
    client = _client()
    team_ids = {
        "A": _build_minimal_team(client, "ENG", "A"),
        "B": _build_minimal_team(client, "FRA", "B"),
        "C": _build_minimal_team(client, "IRE", "C"),
        "D": _build_minimal_team(client, "WAL", "D"),
    }
    report = client.post("/api/tournament/run", json={
        "type": "custom", "team_ids": team_ids, "format": "round_robin", "seed": 1,
    }).get_json()
    assert report["standings"] is not None
    assert len(report["standings"]) == 4
    assert len(report["results"]) == 6  # 4 choose 2


def test_team_export_import_round_trip():
    client = _client()
    team_id = _build_minimal_team(client, "ENG", "England")
    exported = client.get(f"/api/team/{team_id}/export").get_json()
    assert exported["name"] == "England"

    imported = client.post("/api/team/import", json=exported).get_json()
    assert imported["problems"] == []
    assert imported["team_id"] != team_id
    assert len(imported["slots"]) == len(exported["starters"])


def test_world_cup_2027_tournament_via_api():
    client = _client()
    wc = client.get("/api/tournament/options").get_json()["world_cup_2027"]
    team_ids = {
        name: _build_minimal_team(client, wc["code_by_nation"][name], name)
        for name in wc["teams"]
    }
    report = client.post("/api/tournament/run", json={
        "type": "world_cup_2027", "team_ids": team_ids, "fixture_mode": "specific", "seed": 1,
    }).get_json()
    assert report["champion"] in wc["teams"]
    assert len(report["pools"]) == 6
    assert report["bracket"][0]["stage"] == "round-of-16"
