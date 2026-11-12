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


def _report_json(report: TournamentReport) -> dict:
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
    body = request.get_json(force=True)
    kind = body["type"]  # "real" | "world_cup_2027" | "historical_world_cup" | "historical_six_nations" | "custom"
    team_ids: Dict[str, str] = body["team_ids"]  # team display name -> team_id
    seed = body.get("seed")

    teams: Dict[str, Team] = {}
    for name, tid in team_ids.items():
        team = _TEAMS.get(tid)
        if team is None:
            return jsonify({"error": f"unknown team_id for {name}"}), 400
        teams[name] = team

    try:
        if kind == "real":
            report = Tournament(teams).run_real(body["key"], season=body.get("season", "2026"), seed=seed)
        elif kind == "world_cup_2027":
            report = Tournament(teams).run_world_cup_2027(
                fixture_mode=body.get("fixture_mode", "specific"), seed=seed,
            )
        elif kind == "historical_world_cup":
            report = Tournament(teams).run_historical_world_cup(int(body["year"]), seed=seed)
        elif kind == "historical_six_nations":
            report = Tournament(teams).run_historical_six_nations(int(body["year"]), seed=seed)
        elif kind == "custom":
            fmt = body.get("format", "round_robin")
            pool_count = int(body.get("pool_count", 2))
            report = CustomTournament(teams, format=fmt).run(pool_count=pool_count, seed=seed)
        else:
            return jsonify({"error": f"unknown tournament type {kind}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(_report_json(report))


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
        app.run(debug=False, port=port)
    except OSError as e:
        print(
            f"\nCould not bind to port {port}: {e}\n"
            f"Something else is using it and couldn't be stopped automatically - "
            f"close it manually, or set WEBAPP_PORT to a free port."
        )


if __name__ == "__main__":
    main()
