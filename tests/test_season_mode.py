from rugby_sim import webapp
from rugby_sim.data.sources.pool_builder import build_season_pool, build_widest_season_pool
from rugby_sim.tournament.season import SeasonPlan


def _client():
    webapp.app.config["TESTING"] = True
    return webapp.app.test_client()


def test_season_plan_resolves_six_nations_block_for_a_tier1_union():
    blocks = SeasonPlan("IRE", 2026)
    assert any(b.kind == "real" and b.key == "six_nations" for b in blocks)
    six_nations = next(b for b in blocks if b.key == "six_nations")
    assert "Ireland" in six_nations.team_names
    assert len(six_nations.team_names) == 6


def test_season_plan_includes_rugby_championship_even_for_a_non_participant_nation():
    # Scotland never plays in the Rugby Championship, but (Ask 1) every
    # real tournament block with data for that year must still be included
    # and fully simulated, so the shared rankings tracker moves for every
    # union the real calendar actually had matches for that year - not
    # just the ones the chosen nation personally played in.
    blocks = SeasonPlan("SCO", 2025)
    assert any(b.kind == "real" and b.key == "six_nations" for b in blocks)
    rc = next((b for b in blocks if b.key == "rugby_championship"), None)
    assert rc is not None, "expected a Rugby Championship block for Scotland's 2025 season"
    assert "Scotland" not in rc.team_names
    for team in ("New Zealand", "South Africa", "Australia", "Argentina"):
        assert team in rc.team_names


def test_season_plan_does_not_crash_on_nations_championship_block_lookup():
    # The Nations Championship (new in 2026) has no real fixture data in
    # the dataset yet, so it should simply produce no block for 2026 - the
    # no-data path must not error, and every other block (e.g. Six Nations)
    # must still resolve normally alongside it.
    blocks = SeasonPlan("IRE", 2026)
    nc = next((b for b in blocks if b.key == "nations_championship"), None)
    if nc is not None:
        # Real data has since appeared - confirm it's included like any
        # other block, properly named and team-populated.
        assert nc.kind == "real"
        assert len(nc.team_names) > 0
    assert any(b.kind == "real" and b.key == "six_nations" for b in blocks)


def test_rugby_championship_block_updates_rankings_for_teams_my_team_never_plays():
    client = _client()
    from rugby_sim.data.sources.pool_builder import NATION_DISPLAY
    nation_code, year = "SCO", 2025
    my_team = NATION_DISPLAY[nation_code]

    widest = client.get(f"/api/season/widest_pool?nation={nation_code}&year={year}").get_json()
    squad_ids = [p["id"] for p in widest["pool"]]

    start = client.post("/api/season/start", json={
        "nation_code": nation_code, "year": year, "my_team": my_team,
        "squad_player_ids": {my_team: squad_ids}, "seed": 7,
    }).get_json()
    assert "error" not in start
    session_id = start["session_id"]
    final_state, _pause_count = _drive_season_session(client, session_id, start)
    assert final_state["status"] == "finished"

    team_form = final_state["team_form"]
    teams_in_report = {row["team"] for row in team_form}
    for team in ("New Zealand", "South Africa", "Australia", "Argentina"):
        assert team in teams_in_report
        row = next(r for r in team_form if r["team"] == team)
        # Each played real Rugby Championship fixtures this season, so its
        # rating must have moved (or at least been recorded) even though
        # Scotland never played them.
        assert row["wins"] + row["draws"] + row["losses"] > 0


def test_season_plan_unknown_union_raises():
    try:
        SeasonPlan("ZZZ", 2026)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_widest_season_pool_is_at_least_as_big_as_plain_season_pool():
    # Ireland is covered by 12d/13a's league-wide uncapped pool (URC), so
    # the widest pool should be materially larger than the capped-only one.
    capped = build_season_pool("IRE", 2026)
    widest = build_widest_season_pool("IRE", 2026)
    assert len(widest) >= len(capped)
    capped_names = {p.name.strip().lower() for p in capped}
    widest_names = {p.name.strip().lower() for p in widest}
    assert capped_names <= widest_names


def test_build_widest_season_pool_graceful_noop_for_uncovered_union():
    # A union `uncapped_pool` doesn't cover at all should just fall back to
    # the plain capped pool, not crash.
    capped = build_season_pool("JPN", 2026)
    widest = build_widest_season_pool("JPN", 2026)
    assert len(widest) >= len(capped)


def _play_out_live_match(client, live_state):
    """Drives a live-match state (shared `/api/match/live/<id>/...`
    endpoints Season mode now reuses unchanged) through `.../continue`
    until finished, making one manual substitution along the way to
    exercise that control too. Returns the final state."""
    state = live_state
    session_id = state["session_id"]
    if state["home"]["bench"]:
        bench_player_id = state["home"]["bench"][0]["id"]
        position = state["home"]["lineup"][0]["position"]
        sub = client.post(f"/api/match/live/{session_id}/substitute", json={
            "team": "home", "position": position, "bench_player_id": bench_player_id,
        }).get_json()
        assert "error" not in sub
        state = sub
    guard = 0
    while not state["finished"] and guard < 20:
        state = client.post(f"/api/match/live/{session_id}/continue", json={}).get_json()
        guard += 1
    assert state["finished"] is True
    return state


def _drive_season_session(client, session_id, state):
    """Resolves an interactive season session to completion, driving every
    one of my_team's paused live matches through to the end and resuming,
    confirming the background thread auto-advances across block boundaries
    without any manual replay call. Returns (final_state, pause_count)."""
    pause_count = 0
    while state["status"] == "paused":
        pause_count += 1
        block_index_before = state["current_block_index"]
        _play_out_live_match(client, state["live_match"])
        state = client.post(f"/api/season/{session_id}/resume").get_json()
        assert state["current_block_index"] >= block_index_before
    return state, pause_count


def test_interactive_season_drafts_plays_live_and_auto_advances_blocks():
    client = _client()
    nation_code, year = "ITA", 2026

    # Step 1: plan-only call (no my_team yet) - returns the blocks + the
    # widest draft pool for the user to build their squad from.
    plan = client.post("/api/season/start", json={"nation_code": nation_code, "year": year}).get_json()
    assert plan["blocks"], "expected at least one real block for Italy 2026"
    assert plan["pool"]
    assert plan["status"] == "not_started"

    # The widest-pool endpoint (13b's dedicated draft-source lookup) should
    # be at least as big as the plain (capped-only) plan pool.
    widest = client.get(f"/api/season/widest_pool?nation={nation_code}&year={year}").get_json()
    assert len(widest["pool"]) >= len(plan["pool"])

    # Step 2: draft every player in the widest pool as the squad (simplest
    # valid "matchday-23 and then some" - squads mode auto-drafts a fresh
    # best-fit XV per match from whichever of this pool is available).
    from rugby_sim.data.sources.pool_builder import NATION_DISPLAY
    my_team = NATION_DISPLAY[nation_code]
    squad_ids = [p["id"] for p in widest["pool"]]

    start = client.post("/api/season/start", json={
        "nation_code": nation_code, "year": year, "my_team": my_team,
        "squad_player_ids": {my_team: squad_ids}, "seed": 5,
    }).get_json()
    assert "error" not in start
    session_id = start["session_id"]
    # First response is either paused on my_team's own fixture, or (if the
    # very first block's first fixture doesn't involve them - a bye) some
    # other clean, non-error state; either way it must not be "error".
    assert start["status"] in ("paused", "finished")

    final_state, pause_count = _drive_season_session(client, session_id, start)
    assert final_state["status"] == "finished"
    assert pause_count >= 1, "Italy should have at least one of its own fixtures in its Six Nations block"
    assert final_state["current_block_index"] == len(final_state["blocks"])
    assert final_state["results_so_far"]
    assert "team_form" in final_state

    # Polling state mid-/post-run still works.
    state = client.get(f"/api/season/{session_id}/state").get_json()
    assert state["finished"] is True
    assert state["results_so_far"]


def test_season_play_block_endpoint_removed():
    client = _client()
    plan = client.post("/api/season/start", json={"nation_code": "ITA", "year": 2026}).get_json()
    session_id = plan["session_id"]
    res = client.post(f"/api/season/{session_id}/play_block", json={})
    # No such route exists any more - Flask's catch-all static-file route
    # (`/<path:filename>`, GET-only) matches the URL shape before falling
    # through to a plain 404, so a POST here comes back 405 (method not
    # allowed on that catch-all), not 404. Either way, superseded.
    assert res.status_code in (404, 405)


def test_season_unknown_session_404():
    client = _client()
    res = client.get("/api/season/ss_nope/state")
    assert res.status_code == 404


def test_team_form_json_lists_every_known_union_not_just_played_ones():
    # Ask 2: the full tracked-union universe always shows up, including a
    # team with zero matches played yet (baseline rating, 0-0-0 record).
    from rugby_sim.tournament.rankings import TeamRankingTracker, WR_RANKING_SEED
    from rugby_sim.engine.match_engine import MatchResult

    rankings = TeamRankingTracker()
    # Force only Ireland/France to actually "play" something.
    rankings.record_result("Ireland", "France", 24, 20)

    team_form = webapp._team_form_json(rankings, [])
    teams = {row["team"] for row in team_form}
    assert "Ireland" in teams and "France" in teams
    # A team nobody simmed yet still appears, at its seed/baseline rating.
    assert "New Zealand" in teams
    nz_row = next(r for r in team_form if r["team"] == "New Zealand")
    assert nz_row["wins"] == 0 and nz_row["draws"] == 0 and nz_row["losses"] == 0
    assert nz_row["rating"] == round(WR_RANKING_SEED["New Zealand"], 1)
    # Full ranked list, sorted by rating descending.
    ratings = [row["rating"] for row in team_form]
    assert ratings == sorted(ratings, reverse=True)
    assert len(team_form) > 20
