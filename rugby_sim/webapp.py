"""Clickable local web UI for the "what if" builder.

    python -m rugby_sim.webapp

Starts a Flask server on http://127.0.0.1:5000 serving a single-page,
click-driven team builder (no typing required for the core flow - pick a
pool, click a position, click a player) on top of the exact same
`POOLS`/`get_all_legends`/`MatchEngine` used by the interactive CLI. This
is a thin JSON API + static frontend, not a reimplementation - all rugby
logic (fit ratings, match simulation) is the real engine, called directly.

Single-process, single-user, local-only tool: team/player state lives in
plain in-memory dicts (`_TEAMS`, `_PLAYER_BY_ID`), reset whenever the
server restarts. Not meant to be exposed on a network or shared between
browser tabs expecting isolation.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory

from .data.legends import get_all_legends
from .data.national_teams import POOLS
from .data.sources.auto_draft import auto_draft_team
from .data.sources.pool_builder import DEFAULT_SEASON, NATION_DISPLAY, NATION_TO_CODE
from .data.squad_repository import team_from_dict, team_to_dict
from .engine import MatchEngine
from .engine.match_engine import MatchResult
from .models import Lineup, Player, Position, Team
from .tournament import (
    ALL_TEAMS_2027,
    CODE_BY_NATION,
    CustomTournament,
    POOLS_2027,
    Standings,
    Tournament,
    TournamentReport,
    list_tournaments,
)
from .tournament.real_fixtures import load_real_fixtures

app = Flask(__name__, static_folder=None)

# A priority order of generally-strong unions, used to auto-fill a custom
# tournament's teams you didn't name yourself ("mostly the best ones").
# Not a ranking claim beyond "reasonable depth of real data" - just a
# sensible default fill order.
STRONG_UNIONS_FILL_ORDER = [
    "NZL", "RSA", "FRA", "IRE", "ENG", "ARG", "AUS", "WAL", "SCO", "ITA",
    "FIJ", "JPN", "GEO", "SAM", "TGA", "ROU", "USA", "CAN", "URU", "POR",
    "ESP", "CHI", "NAM",
]

# -- player id registry (stable ids for the frontend to reference) --------
_PLAYER_BY_ID: Dict[int, Player] = {}
_ID_BY_PLAYER: Dict[int, int] = {}  # keyed by python id(player)
_next_id = 1


def _register(players: List[Player]) -> None:
    global _next_id
    for p in players:
        key = id(p)
        if key not in _ID_BY_PLAYER:
            _ID_BY_PLAYER[key] = _next_id
            _PLAYER_BY_ID[_next_id] = p
            _next_id += 1


def _player_json(p: Player) -> dict:
    return {
        "id": _ID_BY_PLAYER[id(p)],
        "name": p.name,
        "nation": p.nation,
        "era": p.era,
        "natural_position": p.natural_position.value,
        "data_source": p.data_source,
        "notes": p.notes,
    }


# -- team registry ----------------------------------------------------------
_TEAMS: Dict[str, Team] = {}
_next_team_id = 1

# -- match-result registry (so a tournament's individual matches can be
# drilled into afterwards, same detail as a single friendly) ---------------
_MATCH_RESULTS: Dict[str, MatchResult] = {}
_next_match_id = 1


def _register_match(result: MatchResult) -> str:
    global _next_match_id
    match_id = f"m{_next_match_id}"
    _next_match_id += 1
    _MATCH_RESULTS[match_id] = result
    return match_id


# -- static frontend ----------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(_web_dir(), "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(_web_dir(), filename)


def _web_dir():
    import os
    return os.path.join(os.path.dirname(__file__), "web")


# -- API: reference data -------------------------------------------------
@app.get("/api/unions")
def api_unions():
    return jsonify([
        {"code": code, "name": NATION_DISPLAY.get(code, code)}
        for code in sorted(POOLS.keys())
    ])


@app.get("/api/positions")
def api_positions():
    return jsonify([p.value for p in Position])


@app.get("/api/pool/<code>")
def api_pool(code: str):
    code = code.upper()
    if code not in POOLS:
        return jsonify({"error": f"unknown code {code}"}), 404
    season = request.args.get("season", "2026")
    try:
        players = POOLS[code](season=season)
    except TypeError:
        players = POOLS[code]()
    _register(players)
    return jsonify([_player_json(p) for p in players])


@app.get("/api/logos")
def api_logos():
    """Which union/Barbarians codes have a cached PNG crest ready to serve
    at `/logos/<CODE>.png` (see `team_logos.py`) - fetched ahead of time via
    `python -m rugby_sim.data.sources.team_logos`, not on-demand per
    request, since pulling from Wikipedia live is too slow for a page
    load. A code missing here just means no logo displays for it - not an
    error, some unions (e.g. Tonga) don't have a badge in their own
    Wikipedia infobox at all."""
    import os

    from .data.sources.team_logos import HISTORICAL_NATION_ALIASES, LOGO_DIR, TEAM_LOGO_PAGES

    codes = list(TEAM_LOGO_PAGES.keys()) + ["BAR"]
    available = {}
    for code in codes:
        path = os.path.join(LOGO_DIR, f"{code}.png")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            available[code] = f"/logos/{code}.png"

    # Historical squads are keyed by real nation name ("South Africa"), not
    # a union code - this lets the frontend resolve either one to a logo.
    name_to_code = dict(NATION_TO_CODE)
    for old_name, current_name in HISTORICAL_NATION_ALIASES.items():
        if current_name in name_to_code:
            name_to_code[old_name] = name_to_code[current_name]

    return jsonify({"logos": available, "name_to_code": name_to_code})


@app.get("/api/legends")
def api_legends():
    players = get_all_legends()
    _register(players)
    return jsonify([_player_json(p) for p in players])


@app.get("/api/world_cup_2027/pools")
def api_wc27_pools():
    return jsonify({
        "pools": POOLS_2027,
        "teams": ALL_TEAMS_2027,
        "code_by_nation": CODE_BY_NATION,
    })


@app.get("/api/historical_rwc/years")
def api_historical_rwc_years():
    from .data.sources.historical_rwc import AVAILABLE_RWC_YEARS
    return jsonify({"years": AVAILABLE_RWC_YEARS})


@app.get("/api/historical_rwc/<int:year>")
def api_historical_rwc_year(year: int):
    """Real pool draw + each team's real historical squad (already-built
    `Player`s, registered here so `/api/team/auto`'s fixed-pool variant or a
    manual draft can reference them by id - same pattern as `/api/pool`)."""
    from .data.sources.historical_rwc import get_rwc_year_data

    try:
        pools, squads = get_rwc_year_data(year)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    for squad in squads.values():
        _register(squad)

    return jsonify({
        "year": year,
        "pools": pools,
        "squads": {name: [_player_json(p) for p in squad] for name, squad in squads.items()},
    })


@app.get("/api/historical_six_nations/years")
def api_historical_six_nations_years():
    from .data.sources.historical_six_nations import AVAILABLE_SIX_NATIONS_YEARS
    return jsonify({"years": AVAILABLE_SIX_NATIONS_YEARS})


@app.get("/api/historical_six_nations/<int:year>")
def api_historical_six_nations_year(year: int):
    """Each of the six teams' real historical squad for that Six Nations
    edition - same registration pattern as the historical World Cup
    endpoint, usable both by the dedicated tournament-mode flow and by the
    generic "historical squad" picker in free-pool team building."""
    from .data.sources.historical_six_nations import get_six_nations_year_data

    try:
        squads = get_six_nations_year_data(year)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    for squad in squads.values():
        _register(squad)

    return jsonify({
        "year": year,
        "squads": {name: [_player_json(p) for p in squad] for name, squad in squads.items()},
    })


# -- API: rate candidates for a position -------------------------------
@app.post("/api/rank")
def api_rank():
    body = request.get_json(force=True)
    player_ids: List[int] = body["player_ids"]
    position = Position(body["position"])
    candidates = [_PLAYER_BY_ID[pid] for pid in player_ids if pid in _PLAYER_BY_ID]
    ranked = sorted(candidates, key=lambda p: p.rating_at(position), reverse=True)
    return jsonify([
        {**_player_json(p), "fit": p.rating_at(position)}
        for p in ranked
    ])


# -- API: build + validate a team ---------------------------------------
@app.post("/api/team")
def api_build_team():
    body = request.get_json(force=True)
    name: str = body["name"]
    slots: Dict[str, int] = body["slots"]  # position value -> player id
    captain_id: Optional[int] = body.get("captain")
    bench_ids: List[int] = body.get("bench", [])

    duplicate_ids = {pid for pid in slots.values() if list(slots.values()).count(pid) > 1}
    duplicate_ids |= {pid for pid in bench_ids if bench_ids.count(pid) > 1}
    duplicate_ids |= set(slots.values()) & set(bench_ids)
    if duplicate_ids:
        names = ", ".join(
            _PLAYER_BY_ID[pid].name for pid in duplicate_ids if pid in _PLAYER_BY_ID
        )
        return jsonify({"error": f"same player picked more than once in this squad: {names}"}), 400

    lineup = Lineup()
    for pos_value, pid in slots.items():
        player = _PLAYER_BY_ID.get(pid)
        if player is None:
            return jsonify({"error": f"unknown player id {pid}"}), 400
        lineup.set_starter(Position(pos_value), player)
    for pid in bench_ids:
        player = _PLAYER_BY_ID.get(pid)
        if player is not None:
            try:
                lineup.add_bench(player)
            except ValueError:
                break
    if captain_id is not None and captain_id in _PLAYER_BY_ID:
        lineup.captain = _PLAYER_BY_ID[captain_id]

    problems = lineup.validate()
    team = Team(name=name, short_code=name[:3].upper(), lineup=lineup)
    team_id = _register_team(team)

    return jsonify({
        "team_id": team_id,
        "problems": problems,
        "fit_ratings": {
            pos.value: round(slot.player.rating_at(pos), 1)
            for pos, slot in lineup.starters.items()
        },
    })


def _register_team(team: Team) -> str:
    global _next_team_id
    team_id = f"t{_next_team_id}"
    _next_team_id += 1
    _TEAMS[team_id] = team
    return team_id


@app.post("/api/team/auto")
def api_team_auto():
    """Auto-drafts a full XV (greedy best-fit, see `auto_draft.py`) instead
    of making the user pick all 15 slots - for "I'll draft my own team(s),
    auto-fill the rest of the tournament" in the web UI's tournament mode."""
    body = request.get_json(force=True)
    name: str = body["name"]
    code: Optional[str] = body.get("code")
    season: str = body.get("season", DEFAULT_SEASON)

    if not code:
        code = NATION_TO_CODE.get(name)
    if not code or code not in POOLS:
        return jsonify({"error": f"don't know which union pool to use for '{name}' - pass a code"}), 400

    try:
        pool = POOLS[code](season=season)
    except TypeError:
        pool = POOLS[code]()
    if not pool:
        return jsonify({"error": f"no players found for {code} {season}"}), 404
    _register(pool)

    team = auto_draft_team(name, pool, short_code=code)
    team_id = _register_team(team)

    return jsonify({
        "team_id": team_id,
        "name": team.name,
        "code": code,
        "problems": team.lineup.validate(),
        "slots": {pos.value: _ID_BY_PLAYER[id(slot.player)] for pos, slot in team.lineup.starters.items()},
        "bench": [_ID_BY_PLAYER[id(p)] for p in team.lineup.bench],
        "captain": _ID_BY_PLAYER[id(team.lineup.captain)] if team.lineup.captain else None,
        "pool": [_player_json(slot.player) for slot in team.lineup.starters.values()]
        + [_player_json(p) for p in team.lineup.bench],
    })


@app.post("/api/team/auto_from_ids")
def api_team_auto_from_ids():
    """Auto-drafts a full XV from an explicit list of already-registered
    player ids, rather than a `POOLS` union code - used for historical
    World Cup squads, which aren't a standing national pool (a team's 1995
    squad isn't the same player list as its 2026 one)."""
    body = request.get_json(force=True)
    name: str = body["name"]
    player_ids: List[int] = body["player_ids"]
    code: Optional[str] = body.get("code")

    pool = [_PLAYER_BY_ID[pid] for pid in player_ids if pid in _PLAYER_BY_ID]
    if not pool:
        return jsonify({"error": "no known player ids given"}), 400

    team = auto_draft_team(name, pool, short_code=code or name[:3].upper())
    team_id = _register_team(team)

    return jsonify({
        "team_id": team_id,
        "name": team.name,
        "problems": team.lineup.validate(),
        "slots": {pos.value: _ID_BY_PLAYER[id(slot.player)] for pos, slot in team.lineup.starters.items()},
        "bench": [_ID_BY_PLAYER[id(p)] for p in team.lineup.bench],
        "captain": _ID_BY_PLAYER[id(team.lineup.captain)] if team.lineup.captain else None,
    })


def _match_json(result: MatchResult) -> dict:
    pom = result.player_of_the_match
    pom_json = None
    if pom is not None:
        pom_json = {"name": pom.name, "nation": pom.nation, "natural_position": pom.natural_position.value}
    return {
        "scoreline": result.scoreline(),
        "score_home": result.score_home,
        "score_away": result.score_away,
        "player_of_the_match": pom_json,
        "top_scorers": [
            {"name": ps.player.name, "team": ps.team, "points": ps.points,
             "tries": ps.tries, "conversions": ps.conversions, "penalty_goals": ps.penalty_goals}
            for ps in sorted(result.player_stats, key=lambda p: p.points, reverse=True)
            if ps.points > 0
        ],
        "events": [
            {"minute": e.minute, "team": e.team, "text": e.text,
             "score_home": e.score_home, "score_away": e.score_away}
            for e in result.events
        ],
        "stats": {
            name: {
                "tries": s.tries, "conversions": s.conversions,
                "penalty_goals": s.penalty_goals, "drop_goals": s.drop_goals,
                "turnovers_won": s.turnovers_won, "handling_errors": s.handling_errors,
                "penalties_conceded": s.penalties_conceded,
                "yellow_cards": s.yellow_cards, "red_cards": s.red_cards,
                "territory_pct": round(s.territory_pct, 1),
                "injuries": s.injuries, "substitutions": s.substitutions,
            }
            for name, s in result.stats.items()
        },
    }


def _standings_json(standings: Standings) -> list:
    return [
        {
            "team": row.team, "played": row.played, "won": row.won,
            "drawn": row.drawn, "lost": row.lost,
            "points_for": row.points_for, "points_against": row.points_against,
            "points_diff": row.points_diff, "table_points": row.table_points,
        }
        for row in standings.table()
    ]


def _match_summary_json(result: MatchResult) -> dict:
    """One tournament match's scoreline + a `match_id` to drill into its
    full event-by-event detail via `/api/match/<id>` (same shape as a
    single friendly's report)."""
    return {
        "home": result.home.name, "away": result.away.name,
        "score_home": result.score_home, "score_away": result.score_away,
        "scoreline": result.scoreline(), "match_id": _register_match(result),
    }


def _team_tournament_stats_json(s) -> dict:
    return {
        "team": s.team, "played": s.played, "tries": s.tries,
        "conversions": s.conversions, "penalty_goals": s.penalty_goals,
        "drop_goals": s.drop_goals, "turnovers_won": s.turnovers_won,
        "handling_errors": s.handling_errors, "penalties_conceded": s.penalties_conceded,
        "yellow_cards": s.yellow_cards, "red_cards": s.red_cards,
        "avg_territory_pct": s.avg_territory_pct,
        "injuries": s.injuries, "substitutions": s.substitutions,
    }


def _player_tournament_stats_json(s) -> dict:
    return {
        "name": s.player.name, "nation": s.player.nation, "team": s.team,
        "position": s.primary_position.value if s.primary_position else None,
        "matches_started": s.matches_started,
        "tries": s.tries, "conversions": s.conversions, "penalty_goals": s.penalty_goals,
        "points": s.points, "average_performance": s.average_performance,
        "played_late_stage": s.played_late_stage,
    }


def _report_json(report: TournamentReport) -> dict:
    top_scorers = sorted(
        (s for s in report.player_stats_aggregate.values() if s.points > 0),
        key=lambda s: s.points, reverse=True,
    )[:15]
    return {
        "name": report.name,
        "results": [_match_summary_json(r) for r in report.results],
        "standings": _standings_json(report.standings) if report.standings else None,
        "pools": (
            {name: _standings_json(s) for name, s in report.pools.items()}
            if report.pools else None
        ),
        "bracket": [
            {"stage": rnd.stage, "matches": [_match_summary_json(r) for r in rnd.results]}
            for rnd in report.bracket
        ],
        "champion": report.champion,
        "team_stats": [_team_tournament_stats_json(s) for s in report.team_stats.values()],
        "top_scorers": [_player_tournament_stats_json(s) for s in top_scorers],
        "team_of_tournament": [
            {"position": position.value, **_player_tournament_stats_json(s)}
            for position, s in report.team_of_tournament.items()
        ],
        "player_of_tournament": (
            _player_tournament_stats_json(report.player_of_tournament)
            if report.player_of_tournament else None
        ),
    }


@app.get("/api/match/<match_id>")
def api_match_detail(match_id: str):
    """Full event-by-event detail for one match already simulated as part
    of a tournament - same JSON shape `/api/match` returns for a friendly,
    so the frontend can reuse the same report renderer."""
    result = _MATCH_RESULTS.get(match_id)
    if result is None:
        return jsonify({"error": f"unknown match_id {match_id}"}), 404
    return jsonify(_match_json(result))


# -- API: save/load a team as JSON ---------------------------------------
@app.get("/api/team/<team_id>/export")
def api_team_export(team_id: str):
    team = _TEAMS.get(team_id)
    if team is None:
        return jsonify({"error": f"unknown team_id {team_id}"}), 404
    return jsonify(team_to_dict(team))


@app.post("/api/team/import")
def api_team_import():
    body = request.get_json(force=True)
    try:
        team = team_from_dict(body)
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"invalid team file: {e}"}), 400

    for slot in team.lineup.starters.values():
        _register([slot.player])
    _register(team.lineup.bench)

    team_id = _register_team(team)
    pool_json = [_player_json(slot.player) for slot in team.lineup.starters.values()]
    pool_json += [_player_json(p) for p in team.lineup.bench]
    return jsonify({
        "team_id": team_id,
        "name": team.name,
        "problems": team.lineup.validate(),
        "slots": {pos.value: _ID_BY_PLAYER[id(slot.player)] for pos, slot in team.lineup.starters.items()},
        "bench": [_ID_BY_PLAYER[id(p)] for p in team.lineup.bench],
        "captain": _ID_BY_PLAYER[id(team.lineup.captain)] if team.lineup.captain else None,
        "pool": pool_json,
    })


# -- API: run a single match --------------------------------------------
@app.post("/api/match")
def api_match():
    body = request.get_json(force=True)
    home = _TEAMS.get(body["home_team_id"])
    away = _TEAMS.get(body["away_team_id"])
    if home is None or away is None:
        return jsonify({"error": "unknown team_id - build both teams first"}), 400
    seed = body.get("seed")

    try:
        result = MatchEngine(home, away, seed=seed).run()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(_match_json(result))


# -- API: a pausable "live" match, for mid-match substitutions -----------
# Checkpoints a live match pauses at - same convention as the interactive
# CLI's SUB_CHECKPOINTS (rugby_sim/interactive_cli.py).
LIVE_MATCH_CHECKPOINTS = [20, 40, 60, 70]

_LIVE_MATCHES: Dict[str, MatchEngine] = {}
_next_live_match_id = 1


def _lineup_json(engine: MatchEngine, team: Team) -> list:
    return [
        {"position": pos.value, **_player_json(slot.player)}
        for pos, slot in engine.active_lineup(team).items()
    ]


def _bench_json(engine: MatchEngine, team: Team) -> list:
    return [_player_json(p) for p in engine.bench_for(team)]


def _live_match_state_json(session_id: str, engine: MatchEngine) -> dict:
    result = engine.result
    return {
        "session_id": session_id,
        "minute": engine.minute,
        "finished": engine.is_finished(),
        "score_home": result.score_home if result else 0,
        "score_away": result.score_away if result else 0,
        "scoreline": result.scoreline() if result else "",
        "events": [
            {"minute": e.minute, "team": e.team, "text": e.text,
             "score_home": e.score_home, "score_away": e.score_away}
            for e in (result.events if result else [])
        ],
        "home": {
            "name": engine.home.name, "lineup": _lineup_json(engine, engine.home),
            "bench": _bench_json(engine, engine.home),
        },
        "away": {
            "name": engine.away.name, "lineup": _lineup_json(engine, engine.away),
            "bench": _bench_json(engine, engine.away),
        },
    }


def _start_live_match(home: Team, away: Team, seed: Optional[int]) -> str:
    """Starts a pausable match (engine advanced to its first checkpoint) and
    registers it in `_LIVE_MATCHES`, returning its session id. Shared by the
    single-friendly `/api/match/live/start` endpoint and the interactive
    tournament's pause hook, which needs the exact same pausable flow for
    whichever fixture involves the user's own team."""
    global _next_live_match_id
    engine = MatchEngine(home, away, seed=seed)
    engine.start()
    if LIVE_MATCH_CHECKPOINTS:
        engine.advance_to(LIVE_MATCH_CHECKPOINTS[0])
    else:
        engine.finish()
    session_id = f"live{_next_live_match_id}"
    _next_live_match_id += 1
    _LIVE_MATCHES[session_id] = engine
    return session_id


@app.post("/api/match/live/start")
def api_match_live_start():
    """Starts a pausable match - advances straight to the first checkpoint
    (not minute 0) so the very first response already has something to
    react to. The frontend keeps calling .../continue to reach each
    further checkpoint, optionally calling .../substitute in between."""
    body = request.get_json(force=True)
    home = _TEAMS.get(body["home_team_id"])
    away = _TEAMS.get(body["away_team_id"])
    if home is None or away is None:
        return jsonify({"error": "unknown team_id - build both teams first"}), 400
    seed = body.get("seed")

    try:
        session_id = _start_live_match(home, away, seed)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(_live_match_state_json(session_id, _LIVE_MATCHES[session_id]))


@app.post("/api/match/live/<session_id>/continue")
def api_match_live_continue(session_id: str):
    """Advances to the next checkpoint (or finishes the match, finalizing
    stats/Player of the Match, once checkpoints are exhausted)."""
    engine = _LIVE_MATCHES.get(session_id)
    if engine is None:
        return jsonify({"error": f"unknown live match session {session_id}"}), 404
    if engine.is_finished():
        return jsonify(_live_match_state_json(session_id, engine))

    remaining = [m for m in LIVE_MATCH_CHECKPOINTS if m > engine.minute]
    if remaining:
        engine.advance_to(remaining[0])
    else:
        engine.finish()

    state = _live_match_state_json(session_id, engine)
    if engine.is_finished():
        state["result"] = _match_json(engine.result)
    return jsonify(state)


@app.post("/api/match/live/<session_id>/substitute")
def api_match_live_substitute(session_id: str):
    """Manually brings on a specific bench player at a position - the
    "pause, make a substitution" control. `team` is `"home"` or `"away"`;
    `bench_player_id` picks exactly who comes on."""
    engine = _LIVE_MATCHES.get(session_id)
    if engine is None:
        return jsonify({"error": f"unknown live match session {session_id}"}), 404
    body = request.get_json(force=True)
    team = engine.home if body.get("team") == "home" else engine.away
    try:
        position = Position(body["position"])
    except ValueError:
        return jsonify({"error": f"unknown position {body.get('position')}"}), 400
    bench_player = _PLAYER_BY_ID.get(body.get("bench_player_id"))
    if bench_player is None:
        return jsonify({"error": "unknown bench_player_id"}), 400

    ok = engine.apply_substitution(team, position, bench_player=bench_player)
    if not ok:
        return jsonify({"error": "could not make that substitution (not on the bench, or 8-sub cap reached)"}), 400
    return jsonify(_live_match_state_json(session_id, engine))


# -- API: tournament modes ------------------------------------------------
@app.get("/api/tournament/options")
def api_tournament_options():
    return jsonify({
        "real_keys": list_tournaments(),
        "world_cup_2027": {"teams": ALL_TEAMS_2027, "pools": POOLS_2027, "code_by_nation": CODE_BY_NATION},
        "strong_unions_fill_order": STRONG_UNIONS_FILL_ORDER,
        "default_season": DEFAULT_SEASON,
    })


@app.get("/api/tournament/real/teams")
def api_tournament_real_teams():
    key = request.args.get("key")
    season = request.args.get("season", "2026")
    fixtures = load_real_fixtures(key, season)
    if not fixtures:
        return jsonify({"error": "no fixtures found for that competition/season"}), 404
    team_names = sorted({f.home for f in fixtures} | {f.away for f in fixtures})
    code_by_nation = {name: NATION_TO_CODE[name] for name in team_names if name in NATION_TO_CODE}
    return jsonify({"teams": team_names, "code_by_nation": code_by_nation})


@app.post("/api/tournament/run")
def api_tournament_run():
    """`team_ids`: display name -> a pre-built team's `team_id` (the
    original, fixed-lineup-for-the-whole-tournament mode). `squad_player_ids`,
    for the same tournament, lets a different subset of teams use the
    "fresh squad every match" mode instead - display name -> a list of
    player ids forming that team's full pool; `Tournament`/`CustomTournament`
    auto-draft a new lineup for that team before every single match, and an
    in-match injury/red card sidelines that player for their team's next
    match (see `tournament/availability.py`). A name must be in exactly one
    of the two maps, never both."""
    body = request.get_json(force=True)
    kind = body["type"]  # "real" | "world_cup_2027" | "historical_world_cup" | "historical_six_nations" | "custom"
    team_ids: Dict[str, str] = body.get("team_ids", {})
    squad_player_ids: Dict[str, List[int]] = body.get("squad_player_ids", {})
    seed = body.get("seed")

    teams: Dict[str, Team] = {}
    for name, tid in team_ids.items():
        team = _TEAMS.get(tid)
        if team is None:
            return jsonify({"error": f"unknown team_id for {name}"}), 400
        teams[name] = team

    squads: Dict[str, List[Player]] = {}
    for name, pids in squad_player_ids.items():
        pool = [_PLAYER_BY_ID[pid] for pid in pids if pid in _PLAYER_BY_ID]
        if not pool:
            return jsonify({"error": f"no known players in the squad pool for {name}"}), 400
        squads[name] = pool

    try:
        if kind == "real":
            report = Tournament(teams=teams, squads=squads).run_real(
                body["key"], season=body.get("season", "2026"), seed=seed,
            )
        elif kind == "world_cup_2027":
            report = Tournament(teams=teams, squads=squads).run_world_cup_2027(
                fixture_mode=body.get("fixture_mode", "specific"), seed=seed,
            )
        elif kind == "historical_world_cup":
            report = Tournament(teams=teams, squads=squads).run_historical_world_cup(int(body["year"]), seed=seed)
        elif kind == "historical_six_nations":
            report = Tournament(teams=teams, squads=squads).run_historical_six_nations(int(body["year"]), seed=seed)
        elif kind == "custom":
            fmt = body.get("format", "round_robin")
            pool_count = int(body.get("pool_count", 2))
            report = CustomTournament(teams=teams, format=fmt, squads=squads).run(pool_count=pool_count, seed=seed)
        else:
            return jsonify({"error": f"unknown tournament type {kind}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(_report_json(report))


# -- API: interactive ("my team") tournaments ----------------------------
# Same tournament modes as `/api/tournament/run`, but the user picks which
# team is theirs: every fixture NOT involving that team is auto-simmed
# exactly as before, but a fixture that DOES involve it pauses, mid-
# tournament, on the same pausable "live match" flow the single-friendly
# live match uses (`_LIVE_MATCHES`, `/api/match/live/.../continue` +
# `.../substitute`) - so the user can actually play their own matches out
# while the rest of the draw simulates itself around them.
#
# Implementation: `Tournament`/`CustomTournament` still run start-to-finish,
# synchronously, in their own existing `run_*` methods - no rewrite of the
# bracket/pool logic into a generator. Instead each session's tournament
# runs on a background thread; its `pause_hook` (passed to `Tournament`)
# blocks that thread on a `threading.Event` the moment it hits a `my_team`
# fixture, after registering a live match the same way a single friendly
# would. The Flask request thread that kicked things off (or that later
# resumes it) waits on a separate "state changed" event and returns as soon
# as the tournament thread either pauses or finishes - so each HTTP call
# still gets a normal, bounded response, never streaming or polling.
@dataclass
class TournamentSession:
    state_changed: threading.Event
    resume_event: threading.Event
    status: str = "running"  # "running" | "paused" | "finished" | "error"
    live_session_id: Optional[str] = None
    home_name: Optional[str] = None
    away_name: Optional[str] = None
    pending_result: Optional[MatchResult] = None
    report: Optional[TournamentReport] = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None
    # Every fixture's result, in play order, as soon as it's resolved -
    # auto-simmed ones and my_team's own - so the web UI can show a running
    # "results so far" feed instead of only the single final report.
    completed: List[MatchResult] = field(default_factory=list)
    # Current stage name + live standings/pools/bracket, refreshed after
    # every match (see `_tournament_progress_json`) - lets the web UI show
    # "what stage am I in, what's the table like right now" mid-tournament.
    progress: Optional[dict] = None


_TOURNAMENT_SESSIONS: Dict[str, TournamentSession] = {}
_next_tournament_session_id = 1


def _tournament_progress_json(instance) -> dict:
    """Live snapshot of an in-progress `Tournament`/`CustomTournament` -
    `current_stage`/`current_standings`/`current_pools`/`current_bracket`
    are updated in place as the tournament runs (see `Tournament.__init__`),
    so this always reflects every match played up to this exact point, not
    just the final report."""
    return {
        "stage": instance.current_stage,
        "standings": _standings_json(instance.current_standings) if instance.current_standings else None,
        "pools": (
            {name: _standings_json(s) for name, s in instance.current_pools.items()}
            if instance.current_pools else None
        ),
        "bracket": [
            {"stage": rnd.stage, "matches": [_match_summary_json(r) for r in rnd.results]}
            for rnd in instance.current_bracket
        ],
    }


def _tournament_session_state_json(session_id: str, session: TournamentSession) -> dict:
    # `results_so_far`/`progress` are cumulative (every fixture resolved up
    # to the moment this response was built) and sent on every response
    # shape - paused, finished, or error - so the web UI always has a full
    # running feed + current stage/standings to show alongside whatever
    # else is happening.
    results_so_far = [_match_summary_json(r) for r in session.completed]
    progress = session.progress
    if session.status == "paused":
        live = _LIVE_MATCHES[session.live_session_id]
        return {
            "session_id": session_id, "status": "paused",
            "home": session.home_name, "away": session.away_name,
            "live_match": _live_match_state_json(session.live_session_id, live),
            "results_so_far": results_so_far, "progress": progress,
        }
    if session.status == "finished":
        return {
            "session_id": session_id, "status": "finished",
            "report": _report_json(session.report), "results_so_far": results_so_far,
            "progress": progress,
        }
    if session.status == "error":
        return {
            "session_id": session_id, "status": "error", "error": session.error,
            "results_so_far": results_so_far, "progress": progress,
        }
    return {
        "session_id": session_id, "status": session.status,
        "results_so_far": results_so_far, "progress": progress,
    }


def _build_tournament(kind: str, body: dict, teams: Dict[str, Team], squads: Dict[str, List[Player]],
                       my_team: Optional[str], pause_hook, on_match_played, holder: dict) -> TournamentReport:
    """`holder['instance']` is set to the `Tournament`/`CustomTournament`
    right after construction, before its `run_*` is called - this is how
    `_run_tournament_session` gets a live reference to read
    `current_stage`/`current_standings`/`current_pools`/`current_bracket`
    off of while the tournament is still running (they're the only thing
    the caller has *during* the run; the return value is just the final
    report)."""
    seed = body.get("seed")
    if kind == "real":
        t = Tournament(teams=teams, squads=squads, my_team=my_team, pause_hook=pause_hook, on_match_played=on_match_played)
        holder["instance"] = t
        return t.run_real(body["key"], season=body.get("season", "2026"), seed=seed)
    if kind == "world_cup_2027":
        t = Tournament(teams=teams, squads=squads, my_team=my_team, pause_hook=pause_hook, on_match_played=on_match_played)
        holder["instance"] = t
        return t.run_world_cup_2027(fixture_mode=body.get("fixture_mode", "specific"), seed=seed)
    if kind == "historical_world_cup":
        t = Tournament(teams=teams, squads=squads, my_team=my_team, pause_hook=pause_hook, on_match_played=on_match_played)
        holder["instance"] = t
        return t.run_historical_world_cup(int(body["year"]), seed=seed)
    if kind == "historical_six_nations":
        t = Tournament(teams=teams, squads=squads, my_team=my_team, pause_hook=pause_hook, on_match_played=on_match_played)
        holder["instance"] = t
        return t.run_historical_six_nations(int(body["year"]), seed=seed)
    if kind == "custom":
        fmt = body.get("format", "round_robin")
        pool_count = int(body.get("pool_count", 2))
        t = CustomTournament(
            teams=teams, format=fmt, squads=squads, my_team=my_team, pause_hook=pause_hook,
            on_match_played=on_match_played,
        )
        holder["instance"] = t
        return t.run(pool_count=pool_count, seed=seed)
    raise ValueError(f"unknown tournament type {kind}")


def _run_tournament_session(session: TournamentSession, kind: str, body: dict,
                             teams: Dict[str, Team], squads: Dict[str, List[Player]], my_team: Optional[str]):
    def pause_hook(home_name, away_name, home_team, away_team, seed):
        live_session_id = _start_live_match(home_team, away_team, seed)
        session.live_session_id = live_session_id
        session.home_name, session.away_name = home_name, away_name
        session.status = "paused"
        session.resume_event.clear()
        session.state_changed.set()
        session.resume_event.wait()
        return session.pending_result

    holder: dict = {}

    def on_match_played(home_name, away_name, result):
        session.completed.append(result)
        instance = holder.get("instance")
        if instance is not None:
            session.progress = _tournament_progress_json(instance)

    try:
        report = _build_tournament(kind, body, teams, squads, my_team, pause_hook, on_match_played, holder)
        session.report = report
        session.status = "finished"
    except ValueError as e:
        session.error = str(e)
        session.status = "error"
    except Exception as e:  # pragma: no cover - defensive, surfaces instead of hanging the request
        session.error = f"unexpected error: {e}"
        session.status = "error"
    finally:
        session.state_changed.set()


@app.post("/api/tournament/start")
def api_tournament_start():
    """Same body as `/api/tournament/run`, plus `my_team` (a display name
    already present in `team_ids`/`squad_player_ids`). Starts the
    tournament on a background thread and blocks until it either pauses on
    the user's own first fixture or (if `my_team` is absent, not in this
    tournament, or the tournament finishes without the thread ever
    reaching a `my_team` fixture) runs straight through to completion -
    either way the response is the resulting state, same shape
    `/api/tournament/<id>/resume` returns."""
    global _next_tournament_session_id
    body = request.get_json(force=True)
    kind = body["type"]
    team_ids: Dict[str, str] = body.get("team_ids", {})
    squad_player_ids: Dict[str, List[int]] = body.get("squad_player_ids", {})
    my_team: Optional[str] = body.get("my_team") or None

    teams: Dict[str, Team] = {}
    for name, tid in team_ids.items():
        team = _TEAMS.get(tid)
        if team is None:
            return jsonify({"error": f"unknown team_id for {name}"}), 400
        teams[name] = team

    squads: Dict[str, List[Player]] = {}
    for name, pids in squad_player_ids.items():
        pool = [_PLAYER_BY_ID[pid] for pid in pids if pid in _PLAYER_BY_ID]
        if not pool:
            return jsonify({"error": f"no known players in the squad pool for {name}"}), 400
        squads[name] = pool

    session_id = f"ts{_next_tournament_session_id}"
    _next_tournament_session_id += 1
    session = TournamentSession(state_changed=threading.Event(), resume_event=threading.Event())
    _TOURNAMENT_SESSIONS[session_id] = session

    thread = threading.Thread(
        target=_run_tournament_session, args=(session, kind, body, teams, squads, my_team), daemon=True,
    )
    session.thread = thread
    thread.start()
    session.state_changed.wait()
    session.state_changed.clear()
    return jsonify(_tournament_session_state_json(session_id, session))


@app.post("/api/tournament/<session_id>/resume")
def api_tournament_resume(session_id: str):
    """Call once the user's own live match (started by the pause above,
    under `live_match.session_id`) is finished - its result is handed back
    into the tournament's ongoing standings/bracket, and the tournament
    auto-advances again until either the next `my_team` fixture pauses it
    or the tournament ends."""
    session = _TOURNAMENT_SESSIONS.get(session_id)
    if session is None:
        return jsonify({"error": f"unknown tournament session {session_id}"}), 404
    if session.status != "paused":
        return jsonify({"error": f"tournament session {session_id} is not paused (status: {session.status})"}), 400

    live = _LIVE_MATCHES.get(session.live_session_id)
    if live is None or not live.is_finished():
        return jsonify({"error": "the live match for this pause point hasn't finished yet - "
                                  "use /api/match/live/.../continue (and .../substitute) to finish it first"}), 400

    session.pending_result = live.result
    session.state_changed.clear()
    session.resume_event.set()
    session.state_changed.wait()
    session.state_changed.clear()
    return jsonify(_tournament_session_state_json(session_id, session))


@app.get("/api/tournament/<session_id>/status")
def api_tournament_status(session_id: str):
    session = _TOURNAMENT_SESSIONS.get(session_id)
    if session is None:
        return jsonify({"error": f"unknown tournament session {session_id}"}), 404
    return jsonify(_tournament_session_state_json(session_id, session))


def _parse_listening_pids(netstat_output: str, port: int) -> set:
    """Pure-logic half of `_free_port_if_busy`, split out so it's testable
    without actually shelling out to `netstat`. Parses Windows
    `netstat -ano` output for PIDs LISTENING on `port`."""
    pids = set()
    for line in netstat_output.splitlines():
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address, pid = parts[1], parts[-1]
        if local_address.endswith(f":{port}") and pid.isdigit() and pid != "0":
            pids.add(pid)
    return pids


def _free_port_if_busy(port: int) -> None:
    """Best-effort: if something (almost always a stale run of this same
    server, left over from before a code change) is already listening on
    `port`, stop it so `python -m rugby_sim.webapp` can always just use the
    same URL instead of climbing to a new port every time. Windows-only
    (uses `netstat`/`taskkill`); on other platforms this is a no-op and
    Flask's own "address already in use" error explains what to do."""
    import platform
    import subprocess

    if platform.system() != "Windows":
        return
    try:
        netstat = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return

    pids_to_kill = _parse_listening_pids(netstat, port)

    for pid in pids_to_kill:
        print(f"Port {port} is already in use (PID {pid}) - stopping it so this run can use it...")
        try:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
        except Exception as e:
            print(f"  could not stop PID {pid}: {e} - you may need to close it yourself.")

    if pids_to_kill:
        import time
        time.sleep(0.5)


def main():
    import os
    port = int(os.environ.get("WEBAPP_PORT", "5000"))
    _free_port_if_busy(port)
    print(f"What If Rugby Edition - web UI starting on http://127.0.0.1:{port}")
    try:
        app.run(debug=False, port=port, threaded=True)
    except OSError as e:
        print(
            f"\nCould not bind to port {port}: {e}\n"
            f"Something else is using it and couldn't be stopped automatically - "
            f"close it manually, or set WEBAPP_PORT to a free port."
        )


if __name__ == "__main__":
    main()
