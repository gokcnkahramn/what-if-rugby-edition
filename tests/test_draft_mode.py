from rugby_sim import webapp

DRAFT_ROSTER_TARGET = webapp.DRAFT_ROSTER_TARGET  # 15 starters + 8 bench


def _client():
    webapp.app.config["TESTING"] = True
    return webapp.app.test_client()


def test_draft_pool_setup_from_multiple_unions():
    client = _client()
    res = client.post("/api/draft/start", json={"codes": ["ENG", "WAL"], "seed": 1})
    assert res.status_code == 200
    data = res.get_json()
    assert data["phase"] == "drafting"
    assert data["first_picker"] in ("human", "ai")
    assert len(data["remaining_pool"]) >= 2 * DRAFT_ROSTER_TARGET


def test_draft_pool_dedupes_the_same_real_player_across_sources():
    # Submitting the same union twice built two distinct Player objects per
    # real person (each `/api/pool`-style fetch constructs fresh objects) -
    # without deduping by name, that's a literal duplicate pick available
    # in the shared draft pool. ENG alone has too few players to pass the
    # "at least 2x roster target" check, which itself is evidence the
    # duplicate copies were dropped rather than counted twice.
    client = _client()
    res = client.post("/api/draft/start", json={"codes": ["ENG", "ENG"], "seed": 1})
    assert res.status_code == 400
    assert "shared pool only has" in res.get_json()["error"]

    res2 = client.post("/api/draft/start", json={"codes": ["ENG", "WAL", "WAL"], "seed": 1})
    assert res2.status_code == 200
    names = [p["name"] for p in res2.get_json()["remaining_pool"]]
    assert len(names) == len(set(names))


def test_draft_pool_can_mix_the_same_union_at_different_seasons():
    # The original bug report: a single shared `codes`+`season` pair can
    # never express "Ireland 2026 AND Ireland 2025 at once" - `union_squads`
    # (a list of independent {code, season} pairs) is what makes that
    # possible, merged and deduped into the same shared pool as everything
    # else.
    client = _client()
    res = client.post("/api/draft/start", json={
        "union_squads": [
            {"code": "IRE", "season": "2026"}, {"code": "IRE", "season": "2025"},
            {"code": "WAL", "season": "2026"},
        ],
        "seed": 1,
    })
    assert res.status_code == 200
    names = [p["name"] for p in res.get_json()["remaining_pool"]]
    assert len(names) == len(set(names))


def test_draft_pool_can_mix_historical_squads_in():
    client = _client()
    res = client.post("/api/draft/start", json={
        "codes": ["ENG"],
        "historical": [{"competition": "rwc", "year": 2003, "team": "England"}],
        "seed": 1,
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["phase"] == "drafting"
    assert len(data["remaining_pool"]) >= 2 * DRAFT_ROSTER_TARGET


def test_draft_pool_unknown_historical_team_errors():
    client = _client()
    res = client.post("/api/draft/start", json={
        "codes": ["ENG", "WAL"],
        "historical": [{"competition": "rwc", "year": 2003, "team": "Narnia"}],
        "seed": 1,
    })
    assert res.status_code == 404


def test_depth_chart_endpoint_ranks_roster_by_position():
    client = _client()
    start = client.post("/api/draft/start", json={"codes": ["ENG", "WAL"], "seed": 2}).get_json()
    session_id = start["session_id"]
    state = client.get(f"/api/draft/{session_id}/state").get_json()
    pid = state["remaining_pool"][0]["id"]
    client.post(f"/api/draft/{session_id}/pick", json={"player_id": pid})

    res = client.get(f"/api/draft/{session_id}/depth_chart")
    assert res.status_code == 200
    chart = res.get_json()["depth_chart"]
    assert "Fly-half" in chart or len(chart) > 0
    for pos, entries in chart.items():
        assert len(entries) <= 3
        fits = [e["fit"] for e in entries]
        assert fits == sorted(fits, reverse=True)


def test_coin_flip_is_seedable():
    client = _client()
    a = client.post("/api/draft/start", json={"codes": ["ENG", "WAL"], "seed": 7}).get_json()
    b = client.post("/api/draft/start", json={"codes": ["ENG", "WAL"], "seed": 7}).get_json()
    assert a["first_picker"] == b["first_picker"]


def _drive_full_draft(client, session_id):
    state = client.get(f"/api/draft/{session_id}/state").get_json()
    while state["phase"] == "drafting":
        if state["turn"] == "human":
            pid = state["remaining_pool"][0]["id"]
            state = client.post(f"/api/draft/{session_id}/pick", json={"player_id": pid}).get_json()
        else:
            # AI moves on its own turn inside the pick endpoint; poke it by
            # sending a human pick request, which lets the AI go first if
            # it's actually AI's turn before enforcing "not human's turn".
            state = client.post(f"/api/draft/{session_id}/pick", json={"player_id": None}).get_json()
    return state


def test_full_draft_no_duplicate_players_across_both_rosters():
    client = _client()
    start = client.post("/api/draft/start", json={"codes": ["ENG", "WAL"], "seed": 3}).get_json()
    session_id = start["session_id"]
    state = _drive_full_draft(client, session_id)

    assert state["phase"] == "protect"
    assert len(state["human_roster"]) == DRAFT_ROSTER_TARGET
    assert len(state["ai_roster"]) == DRAFT_ROSTER_TARGET
    human_ids = [p["id"] for p in state["human_roster"]]
    ai_ids = [p["id"] for p in state["ai_roster"]]
    all_ids = human_ids + ai_ids
    assert len(all_ids) == len(set(all_ids))


def test_protect_phase_protected_player_is_never_poachable():
    client = _client()
    start = client.post("/api/draft/start", json={"codes": ["ENG", "WAL"], "seed": 5}).get_json()
    session_id = start["session_id"]
    state = _drive_full_draft(client, session_id)
    assert state["phase"] == "protect"

    # Protect the AI's first roster player every round, and try to poach it
    # every round too - it must never move to the human roster.
    protected_ai_target = state["ai_roster"][0]["id"]
    for _ in range(3):
        # We can't protect the opponent's own player (only our own), but we
        # can assert the explicit rule the other way: protect our own best
        # player and confirm an AI poach attempt against it always fails.
        own_target = state["human_roster"][0]["id"]
        state = client.post(
            f"/api/draft/{session_id}/protect_round",
            json={"protect_id": own_target, "poach_id": None},
        ).get_json()
        assert own_target in [p["id"] for p in state["human_roster"]], (
            "a protected player must never be poached away"
        )

    assert state["phase"] == "done"
    assert state["protect_round"] == 3


def test_finalize_and_run_a_match_end_to_end():
    client = _client()
    start = client.post("/api/draft/start", json={"codes": ["ENG", "WAL"], "seed": 11}).get_json()
    session_id = start["session_id"]
    state = _drive_full_draft(client, session_id)
    for _ in range(3):
        # Poach back one AI player every round too, same as the AI does to
        # the human side - net roster sizes stay at 15/15 (just membership
        # changes), which is what the full-XV match step below needs.
        # Pick the AI's weakest unprotected player as the poach target (not
        # the strongest) so this same round's AI self-protect - which always
        # grabs its own best remaining player - can never collide with it.
        ai_unprotected = [p["id"] for p in state["ai_roster"] if p["id"] not in state["protected_ai"]]
        poach_id = ai_unprotected[-1] if ai_unprotected else None
        state = client.post(
            f"/api/draft/{session_id}/protect_round",
            json={"protect_id": state["human_roster"][0]["id"], "poach_id": poach_id},
        ).get_json()
    assert state["phase"] == "done"

    finalized = client.post(f"/api/draft/{session_id}/finalize_ai").get_json()
    assert finalized["team_id"]
    human_roster = finalized["human_roster"]
    assert len(human_roster) == DRAFT_ROSTER_TARGET

    # Same hand-off the real UI uses for the human side's final lineup
    # build: auto-draft a full XV from exactly the drafted roster's ids
    # (the existing `/api/team/auto_from_ids`, the same one historical-squad
    # drafting already reuses) - a human playing for real would instead
    # click through `TeamBuilder` seeded with this roster, but the
    # server-side greedy fill is what's under test here, not the UI clicks.
    human_team_res = client.post(
        "/api/team/auto_from_ids",
        json={"name": "Draft XV", "player_ids": [p["id"] for p in human_roster]},
    ).get_json()
    human_team_id = human_team_res["team_id"]

    match_res = client.post(
        "/api/match",
        json={"home_team_id": human_team_id, "away_team_id": finalized["team_id"], "seed": 1},
    )
    assert match_res.status_code == 200
    assert "scoreline" in match_res.get_json()
