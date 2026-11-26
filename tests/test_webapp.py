from rugby_sim import webapp
from rugby_sim.models import Position


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
    assert all(
        e["zone"] in ("home_tryline", "home_22", "midfield", "away_22", "away_tryline")
        for e in match["events"]
    )
    assert all(e["side"] in ("left", "middle", "right") for e in match["events"])

    # Starting XV + team names - what the finished-report screen's average-
    # position pitch diagram needs (see app.js's `averagePlayerPositions`).
    assert match["home_name"] == "England" and match["away_name"] == "France"
    assert len(match["home_lineup"]) == 15 and len(match["away_lineup"]) == 15
    assert {slot["position"] for slot in match["home_lineup"]} == {p.value for p in Position}


def _build_minimal_team(client, code, name):
    pool = client.get(f"/api/pool/{code}?season=2026").get_json()
    positions = client.get("/api/positions").get_json()
    # Excludes by NAME, not just id: a Wikipedia/historical-sourced pool
    # can legitimately contain the same real person twice under two
    # different ids, one per "twin" position (e.g. a real winger with no
    # recorded left/right split - see `wikipedia_squad.with_twin_position_duplicates`)
    # - picking the best-ranked candidate per slot using only an id-based
    # exclusion set (the old version of this helper) could field that one
    # real person in two different starting positions at once, an invalid
    # lineup that made this test's own tournament run error out instead of
    # producing a champion. Same fix as `auto_draft_lineup`'s own.
    used_ids, used_names, slots = set(), set(), {}
    for pos in positions:
        candidates = [p["id"] for p in pool if p["id"] not in used_ids and p["name"] not in used_names]
        ranked = client.post("/api/rank", json={"player_ids": candidates, "position": pos}).get_json()
        best = ranked[0]
        slots[pos] = best["id"]
        used_ids.add(best["id"])
        used_names.add(best["name"])
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


def test_api_team_rejects_same_real_player_drafted_at_two_positions_by_name():
    # A Wikipedia/historical-sourced squad can contain the same real
    # person twice under two different ids, one per "twin" position (see
    # `wikipedia_squad.with_twin_position_duplicates`) - `/api/team` must
    # reject fielding them in two slots at once even though their ids
    # genuinely differ, not just an exact-id duplicate (the pre-existing
    # check).
    client = _client()
    hist = client.get("/api/historical_rwc/1995").get_json()
    squad = hist["squads"]["South Africa"]
    dup = [p for p in squad if p["name"] == "Os du Randt"]
    assert len(dup) == 2, "expected the real 1995 Os du Randt twin-position duplicate"
    others = iter(p for p in squad if p["name"] != "Os du Randt")

    positions = client.get("/api/positions").get_json()
    slots = {"Loosehead Prop": dup[0]["id"], "Hooker": dup[1]["id"]}
    for pos in positions:
        if pos not in slots:
            slots[pos] = next(others)["id"]

    res = client.post("/api/team", json={
        "name": "Test", "slots": slots, "captain": list(slots.values())[0], "bench": [],
    })
    assert res.status_code == 400
    assert "Os du Randt" in res.get_json()["error"]


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


def test_squad_mode_tournament_run_end_to_end():
    client = _client()
    squad_player_ids = {}
    for code in ["ENG", "FRA", "IRE", "SCO"]:
        players = client.get(f"/api/pool/{code}?season=2026").get_json()
        squad_player_ids[code] = [p["id"] for p in players]

    res = client.post("/api/tournament/run", json={
        "type": "custom", "format": "round_robin",
        "squad_player_ids": squad_player_ids, "seed": 4,
    })
    assert res.status_code == 200
    report = res.get_json()
    assert report["name"] == "Round-robin"
    assert len(report["results"]) == 6
    assert report["team_of_tournament"]


def test_live_match_start_substitute_continue_until_finished():
    client = _client()
    home = client.post("/api/team/auto", json={"name": "England", "code": "ENG", "season": "2026"}).get_json()
    away = client.post("/api/team/auto", json={"name": "France", "code": "FRA", "season": "2026"}).get_json()

    start = client.post("/api/match/live/start", json={
        "home_team_id": home["team_id"], "away_team_id": away["team_id"], "seed": 11,
    }).get_json()
    assert start["finished"] is False
    assert start["minute"] >= 20
    # Live match stats (previously only computed at full time) are now
    # available mid-match so a manager can read running totals while paused.
    assert set(start["stats"].keys()) == {"England", "France"}
    some_team_stats = next(iter(start["stats"].values()))
    assert "tries" in some_team_stats and "possession_pct" in some_team_stats
    session_id = start["session_id"]

    bench_player_id = start["home"]["bench"][0]["id"]
    position = start["home"]["lineup"][0]["position"]
    sub = client.post(f"/api/match/live/{session_id}/substitute", json={
        "team": "home", "position": position, "bench_player_id": bench_player_id,
    }).get_json()
    assert "error" not in sub
    assert any(p["id"] == bench_player_id for p in sub["home"]["lineup"])

    state = sub
    guard = 0
    while not state["finished"] and guard < 10:
        state = client.post(f"/api/match/live/{session_id}/continue", json={}).get_json()
        guard += 1
    assert state["finished"] is True
    assert "result" in state
    assert state["result"]["scoreline"]


def test_live_match_substitute_rejects_unknown_session():
    client = _client()
    res = client.post("/api/match/live/does-not-exist/substitute", json={
        "team": "home", "position": "Hooker", "bench_player_id": 1,
    })
    assert res.status_code == 404


def _play_out_live_match(client, live_state):
    """Drives a `live_match` (or single-friendly live match state) through
    `.../continue` until finished, returns the final state. A pending
    penalty decision (manager-controls pass - see
    `test_manager_penalty_decision_endpoint_end_to_end` for a focused test
    of the decision itself) is resolved with a fixed "touch" choice here,
    same as a manager who always kicks for the corner - this helper exists
    to drive OTHER tests' live matches to completion, not to exercise the
    decision mechanism itself."""
    state = live_state
    guard = 0
    while not state["finished"] and guard < 40:
        session_id = state["session_id"]
        if state.get("pending_penalty") is not None:
            state = client.post(f"/api/match/live/{session_id}/decide_penalty", json={"choice": "touch"}).get_json()
        else:
            state = client.post(f"/api/match/live/{session_id}/continue", json={}).get_json()
        guard += 1
    assert state["finished"] is True
    return state


def _drive_tournament_session(client, state):
    """Resolves an interactive tournament session to completion: whenever
    paused on my_team's own fixture, plays that live match straight through
    (no manual subs - that path is already covered by the live-match tests)
    and resumes, repeating until the session finishes. Returns
    (final_state, pause_count)."""
    pause_count = 0
    while state["status"] == "paused":
        pause_count += 1
        _play_out_live_match(client, state["live_match"])
        state = client.post(f"/api/tournament/{state['session_id']}/resume").get_json()
    return state, pause_count


def test_interactive_tournament_pauses_on_my_team_and_resumes_to_a_final_report():
    client = _client()
    team_ids = {
        "A": _build_minimal_team(client, "ENG", "A"),
        "B": _build_minimal_team(client, "FRA", "B"),
        "C": _build_minimal_team(client, "IRE", "C"),
        "D": _build_minimal_team(client, "WAL", "D"),
    }
    start = client.post("/api/tournament/start", json={
        "type": "custom", "team_ids": team_ids, "format": "round_robin",
        "my_team": "A", "seed": 1,
    }).get_json()
    assert start["status"] == "paused"
    assert "A" in (start["home"], start["away"])

    final_state, pause_count = _drive_tournament_session(client, start)
    assert final_state["status"] == "finished"
    assert pause_count == 3  # "A" plays each of the other 3 teams once in a round robin
    report = final_state["report"]
    assert report["standings"] is not None
    assert len(report["results"]) == 6


def test_interactive_tournament_without_my_team_runs_straight_through():
    client = _client()
    team_ids = {
        "A": _build_minimal_team(client, "ENG", "A"),
        "B": _build_minimal_team(client, "FRA", "B"),
        "C": _build_minimal_team(client, "IRE", "C"),
        "D": _build_minimal_team(client, "WAL", "D"),
    }
    # No my_team at all.
    start = client.post("/api/tournament/start", json={
        "type": "custom", "team_ids": team_ids, "format": "round_robin", "seed": 2,
    }).get_json()
    assert start["status"] == "finished"
    assert len(start["report"]["results"]) == 6

    # my_team given, but it isn't even one of this tournament's teams.
    start2 = client.post("/api/tournament/start", json={
        "type": "custom", "team_ids": team_ids, "format": "round_robin",
        "my_team": "Not In This Tournament", "seed": 2,
    }).get_json()
    assert start2["status"] == "finished"


def test_tournament_run_endpoint_still_works_unchanged():
    client = _client()
    team_ids = {
        "A": _build_minimal_team(client, "ENG", "A"),
        "B": _build_minimal_team(client, "FRA", "B"),
        "C": _build_minimal_team(client, "IRE", "C"),
        "D": _build_minimal_team(client, "WAL", "D"),
    }
    report = client.post("/api/tournament/run", json={
        "type": "custom", "team_ids": team_ids, "format": "round_robin", "seed": 3,
    }).get_json()
    assert report["standings"] is not None
    assert len(report["results"]) == 6


def test_tournament_resume_rejects_unknown_or_not_paused_session():
    client = _client()
    assert client.post("/api/tournament/does-not-exist/resume").status_code == 404

    team_ids = {
        "A": _build_minimal_team(client, "ENG", "A"),
        "B": _build_minimal_team(client, "FRA", "B"),
    }
    start = client.post("/api/tournament/start", json={
        "type": "custom", "team_ids": team_ids, "format": "round_robin", "seed": 4,
    }).get_json()
    assert start["status"] == "finished"
    # Already finished - resuming it again should be rejected, not hang.
    res = client.post(f"/api/tournament/{start['session_id']}/resume")
    assert res.status_code == 400


def test_live_match_swap_endpoint_swaps_two_on_field_players():
    client = _client()
    home = client.post("/api/team/auto", json={"name": "England", "code": "ENG", "season": "2026"}).get_json()
    away = client.post("/api/team/auto", json={"name": "France", "code": "FRA", "season": "2026"}).get_json()

    start = client.post("/api/match/live/start", json={
        "home_team_id": home["team_id"], "away_team_id": away["team_id"], "seed": 11,
    }).get_json()
    session_id = start["session_id"]
    pos_a = start["home"]["lineup"][0]["position"]
    pos_b = start["home"]["lineup"][1]["position"]
    name_a = start["home"]["lineup"][0]["name"]
    name_b = start["home"]["lineup"][1]["name"]

    swapped = client.post(f"/api/match/live/{session_id}/swap", json={
        "team": "home", "position_a": pos_a, "position_b": pos_b,
    }).get_json()
    assert "error" not in swapped
    by_pos = {p["position"]: p["name"] for p in swapped["home"]["lineup"]}
    assert by_pos[pos_a] == name_b
    assert by_pos[pos_b] == name_a
    # Not a substitution - the sub counter is untouched.
    assert swapped["events"][-1]["text"].startswith("Positional swap")


def test_live_match_swap_rejects_unknown_session_or_bad_positions():
    client = _client()
    assert client.post("/api/match/live/does-not-exist/swap", json={
        "team": "home", "position_a": "Hooker", "position_b": "Fullback",
    }).status_code == 404

    home = client.post("/api/team/auto", json={"name": "England", "code": "ENG", "season": "2026"}).get_json()
    away = client.post("/api/team/auto", json={"name": "France", "code": "FRA", "season": "2026"}).get_json()
    start = client.post("/api/match/live/start", json={
        "home_team_id": home["team_id"], "away_team_id": away["team_id"], "seed": 11,
    }).get_json()
    bad = client.post(f"/api/match/live/{start['session_id']}/swap", json={
        "team": "home", "position_a": "Hooker", "position_b": "Hooker",
    })
    assert bad.status_code == 400


def test_match_report_includes_injury_detail_list():
    client = _client()
    home = _build_minimal_team(client, "ENG", "England")
    away = _build_minimal_team(client, "FRA", "France")
    match = client.post("/api/match", json={
        "home_team_id": home, "away_team_id": away, "seed": 1,
    }).get_json()
    assert "injuries" in match
    for inj in match["injuries"]:
        # "severity"/"layoff_matches" - each injury's own rolled tier, see
        # `engine/match_engine.py`'s INJURY_SEVERITY_TIERS.
        assert {"minute", "team", "player", "position", "severity", "layoff_matches"} <= set(inj.keys())


def test_live_match_lineup_and_bench_expose_condition_separately_from_fit():
    # Position fit and match condition are two separate numbers (see
    # README/webapp.py's `_lineup_json`) - this confirms both are present,
    # under different keys, in the live-match JSON a real client reads.
    client = _client()
    home = client.post("/api/team/auto", json={"name": "England", "code": "ENG", "season": "2026"}).get_json()
    away = client.post("/api/team/auto", json={"name": "France", "code": "FRA", "season": "2026"}).get_json()
    start = client.post("/api/match/live/start", json={
        "home_team_id": home["team_id"], "away_team_id": away["team_id"], "seed": 11,
    }).get_json()
    for p in start["home"]["lineup"] + start["home"]["bench"]:
        assert "natural_fit" in p
        assert "condition" in p
    # Condition is a live in-match stamina reading (0-100) - having played
    # some of the match already, at least someone on the park isn't still
    # sitting at a fresh 100.
    assert any(p["condition"] < 100.0 for p in start["home"]["lineup"])


def test_tournament_report_and_session_state_include_injury_report():
    client = _client()
    squad_player_ids = {}
    for code in ["ENG", "FRA", "IRE", "SCO"]:
        players = client.get(f"/api/pool/{code}?season=2026").get_json()
        squad_player_ids[code] = [p["id"] for p in players]

    report = client.post("/api/tournament/run", json={
        "type": "custom", "format": "round_robin",
        "squad_player_ids": squad_player_ids, "seed": 4,
    }).get_json()
    assert "injury_report" in report
    for inj in report["injury_report"]:
        assert {"minute", "team", "player", "position", "match_id"} <= set(inj.keys())

    team_ids = {
        "A": _build_minimal_team(client, "ENG", "A"),
        "B": _build_minimal_team(client, "FRA", "B"),
    }
    start = client.post("/api/tournament/start", json={
        "type": "custom", "team_ids": team_ids, "format": "round_robin", "seed": 4,
    }).get_json()
    assert "injury_report" in start


def test_manager_penalty_decision_endpoint_end_to_end():
    # Manager-controls pass: starting a live match with `decision_teams`
    # pauses for a real in-match choice on that team's own penalties -
    # verified here via the actual HTTP endpoints a frontend would call.
    client = _client()
    home = client.post("/api/team/auto", json={"name": "England", "code": "ENG", "season": "2026"}).get_json()
    away = client.post("/api/team/auto", json={"name": "France", "code": "FRA", "season": "2026"}).get_json()

    state = None
    for seed in range(1, 200):
        state = client.post("/api/match/live/start", json={
            "home_team_id": home["team_id"], "away_team_id": away["team_id"], "seed": seed,
            "decision_teams": ["England"],
        }).get_json()
        guard = 0
        while not state["finished"] and state.get("pending_penalty") is None and guard < 50:
            state = client.post(f"/api/match/live/{state['session_id']}/continue", json={}).get_json()
            guard += 1
        if state.get("pending_penalty") is not None:
            break
    assert state["pending_penalty"] is not None
    assert state["pending_penalty"]["team"] == "England"
    session_id = state["session_id"]

    # An invalid choice is rejected, not silently accepted.
    bad = client.post(f"/api/match/live/{session_id}/decide_penalty", json={"choice": "nonsense"})
    assert bad.status_code == 400

    decided = client.post(f"/api/match/live/{session_id}/decide_penalty", json={"choice": "touch"}).get_json()
    assert decided.get("pending_penalty") is None or decided["pending_penalty"]["team"] == "England"
