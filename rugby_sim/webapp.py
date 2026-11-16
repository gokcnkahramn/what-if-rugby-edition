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

import random
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
from .data.sources.pool_builder import ALL_TEAM_IDS, build_season_pool, build_union_pool
from .tournament.rankings import TeamRankingTracker
from .tournament.real_fixtures import TOURNAMENTS, load_real_fixtures
from .tournament.season import SeasonFixtureBlock, SeasonPlan, SeasonSession, run_season, squad_for_team
from .data.sources.pool_builder import build_widest_season_pool

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


def _dedupe_players_by_name(players: List[Player]) -> List[Player]:
    """Merging several sources into one pool (e.g. draft mode's union codes
    + historical squads + Legends) can genuinely include the same real
    person twice - each source builds its own fresh `Player` objects, so
    they're distinct by identity even when they're the same athlete (same
    convention/problem `build_union_pool` already handles *within* one
    union's own pool, see README - this is the same fix applied across a
    multi-source merge). Keeps whichever occurrence came first."""
    seen = set()
    deduped = []
    for p in players:
        if p.name in seen:
            continue
        seen.add(p.name)
        deduped.append(p)
    return deduped


def _player_json(p: Player) -> dict:
    return {
        "id": _ID_BY_PLAYER[id(p)],
        "name": p.name,
        "nation": p.nation,
        "era": p.era,
        "natural_position": p.natural_position.value,
        # Fit rating at their own natural position - not the same as /api/rank's
        # "fit", which is rated against whatever target position *you're*
        # filling (e.g. a flanker's /api/rank "fit" when considering them for
        # No. 8 is lower than this). This is just "how good are they at their
        # own normal job" - useful anywhere a player is listed without a
        # specific slot in mind yet, like the draft mode pool/roster lists.
        "natural_fit": round(p.rating_at(p.natural_position), 1),
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
# A tournament's progress/results-so-far gets rebuilt from scratch on every
# status poll (see `_tournament_session_state_json`) - this caches one
# `match_id` per result (keyed by python id(result)) so re-describing the
# same already-played match across polls doesn't keep minting fresh ids for
# it, which would break any link to it (e.g. from the injury report below)
# saved from an earlier poll.
_MATCH_ID_BY_RESULT: Dict[int, str] = {}


def _register_match(result: MatchResult) -> str:
    global _next_match_id
    existing = _MATCH_ID_BY_RESULT.get(id(result))
    if existing is not None:
        return existing
    match_id = f"m{_next_match_id}"
    _next_match_id += 1
    _MATCH_RESULTS[match_id] = result
    _MATCH_ID_BY_RESULT[id(result)] = match_id
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


@app.get("/api/backgrounds")
def api_backgrounds():
    """Which blurred-background stadium photos are cached and ready to
    serve at `/backgrounds/<key>.jpg` (see `background_image.py`) - same
    pre-fetched, never-live-per-request convention as `/api/logos`. Every
    entry's `license`/`author` is included because every one of these
    photos is under a Creative Commons license that requires attribution -
    the web UI shows it, this isn't optional metadata."""
    import os

    from .data.sources.background_image import BACKGROUND_DIR, BACKGROUND_IMAGES

    available = {}
    for key, entry in BACKGROUND_IMAGES.items():
        path = os.path.join(BACKGROUND_DIR, f"{key}.jpg")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            available[key] = {
                "url": f"/backgrounds/{key}.jpg",
                "caption": entry.caption,
                "license": entry.license,
                "author": entry.author,
            }
    return jsonify({"backgrounds": available})


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
        "injuries": list(result.injury_details),
        "cards": list(result.card_details),
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


def _injury_report_json(results: List[MatchResult], availability=None) -> list:
    """Every injury across every match in `results` (auto-simmed AND the
    user's own, in an interactive tournament - `results` is just whichever
    list the caller has: `session.completed` mid-tournament, or
    `report.results` for the final/non-interactive report), each one
    carrying its own match's `match_id` so the web UI can link straight to
    that match's full report, same convention as "Results so far".

    `availability`, if given (the `Tournament`/`CustomTournament`'s own
    `TournamentAvailability`), adds a LIVE `matches_remaining` - how many
    more of that player's team's matches they're sidelined for as of right
    now, which can be less than the injury's original `layoff_matches` if
    further matches have already been played since. Without it (no
    tournament context, e.g. called on a plain list of results), each entry
    still has its own `layoff_matches`/`severity` from the match itself,
    just not a live countdown."""
    out = []
    for result in results:
        if not result.injury_details:
            continue
        match_id = _register_match(result)
        # Lines up with `injury_details` by index - see
        # `availability.record_match`'s own identical assumption.
        players_by_index = list(result.injured_players)
        for i, detail in enumerate(result.injury_details):
            entry = {
                **detail,
                "match_id": match_id,
                "scoreline": result.scoreline(),
                "home": result.home.name, "away": result.away.name,
            }
            if availability is not None and i < len(players_by_index):
                team_name, player = players_by_index[i]
                entry["matches_remaining"] = availability.matches_remaining(team_name, player)
            out.append(entry)
    return out


def _card_report_json(results: List[MatchResult], availability=None) -> list:
    """Every card across every match in `results` - same shape/purpose as
    `_injury_report_json` (see there for the general pattern), each entry
    carrying its own match's `match_id` to link back to the full report.

    `availability`, if given, adds a LIVE `matches_remaining` for a red
    card (first-time or escalated from a second yellow) - whether that
    player's suspension for their team's next match is still in effect
    right now. A plain yellow never gets this field: it never carries a
    tournament-level suspension at all (see `tournament/availability.py`)."""
    out = []
    for result in results:
        if not result.card_details:
            continue
        match_id = _register_match(result)
        # Lines up with `card_details` by index - see
        # `availability.record_match`'s own identical assumption for injuries.
        players_by_index = list(result.carded_players)
        for i, detail in enumerate(result.card_details):
            entry = {
                **detail,
                "match_id": match_id,
                "scoreline": result.scoreline(),
                "home": result.home.name, "away": result.away.name,
            }
            if (
                availability is not None and detail.get("card_type") == "red"
                and i < len(players_by_index)
            ):
                team_name, player, _card_type = players_by_index[i]
                entry["matches_remaining"] = availability.matches_remaining(team_name, player)
            out.append(entry)
    return out


def _team_form_json(rankings, results: List[MatchResult]) -> list:
    """One row per union this project tracks at all - every code in
    `pool_builder.ALL_TEAM_IDS`/`NATION_DISPLAY`, unioned with every name
    already in `rankings.rankings.WR_RANKING_SEED` (covers a few seeded
    unions, e.g. Hong Kong, that aren't in `ALL_TEAM_IDS`) - not just teams
    that happen to appear in `results` (Ask 2: a team with zero matches
    played yet still shows up, at its seed/baseline rating and a 0-0-0
    record, so the full world rankings are always visible). A World-Rugby-
    style ranking rating (see `tournament/rankings.py`) plus the W/D/L
    record `results` gives each team that did play. `rankings`, if given
    (the `Tournament`/`CustomTournament`/`SeasonSession`'s own
    `TeamRankingTracker`), supplies each team's live current rating and
    `baseline` (its `WR_RANKING_SEED`/default starting point) - `change`
    is the net movement since that baseline, i.e. across every match this
    tracker has ever recorded for that team (within this tournament, or -
    for a shared Season-mode tracker - across the whole season so far)."""
    if rankings is None:
        return []
    from .data.sources.pool_builder import NATION_DISPLAY
    from .tournament.rankings import DEFAULT_RATING, WR_RANKING_SEED

    wins: Dict[str, int] = {}
    draws: Dict[str, int] = {}
    losses: Dict[str, int] = {}

    universe = set(NATION_DISPLAY.values()) | set(WR_RANKING_SEED.keys())

    def _touch(name: str) -> None:
        if name not in wins:
            wins[name] = draws[name] = losses[name] = 0
        universe.add(name)

    for result in results:
        home, away = result.home.name, result.away.name
        _touch(home)
        _touch(away)
        if result.score_home > result.score_away:
            wins[home] += 1
            losses[away] += 1
        elif result.score_away > result.score_home:
            wins[away] += 1
            losses[home] += 1
        else:
            draws[home] += 1
            draws[away] += 1

    out = []
    for name in universe:
        rating = rankings.rating(name)
        baseline = WR_RANKING_SEED.get(name, DEFAULT_RATING)
        out.append({
            "team": name, "rating": round(rating, 1), "baseline": round(baseline, 1),
            "change": round(rating - baseline, 1),
            "wins": wins.get(name, 0), "draws": draws.get(name, 0), "losses": losses.get(name, 0),
        })
    out.sort(key=lambda row: row["rating"], reverse=True)
    return out


def _report_json(report: TournamentReport, availability=None, rankings=None) -> dict:
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
        "injury_report": _injury_report_json(report.results, availability=availability),
        "card_report": _card_report_json(report.results, availability=availability),
        "team_form": _team_form_json(rankings, report.results),
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
    # `condition` (live, in-match stamina, see `MatchEngine.condition_for`) is
    # deliberately a separate field from `natural_fit` - position fit and
    # match condition are two different numbers, never folded into one on
    # the wire, even though the engine itself multiplies them together
    # internally when computing a team's rating (see `_stamina_factor`).
    return [
        {"position": pos.value, "condition": round(engine.condition_for(slot.player), 1),
         **_player_json(slot.player)}
        for pos, slot in engine.active_lineup(team).items()
    ]


def _bench_json(engine: MatchEngine, team: Team) -> list:
    return [
        {"condition": round(engine.condition_for(p), 1), **_player_json(p)}
        for p in engine.bench_for(team)
    ]


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


def _start_live_match(home: Team, away: Team, seed: Optional[int], initial_condition: Optional[Dict[int, float]] = None) -> str:
    """Starts a pausable match (engine advanced to its first checkpoint) and
    registers it in `_LIVE_MATCHES`, returning its session id. Shared by the
    single-friendly `/api/match/live/start` endpoint and the interactive
    tournament's pause hook, which needs the exact same pausable flow for
    whichever fixture involves the user's own team. `initial_condition`:
    see `MatchEngine.__init__` - carries a squads-mode team's short-rest
    stamina penalty (if any) into their own interactively-played match too,
    same as an auto-simmed one (`Tournament._play`)."""
    global _next_live_match_id
    engine = MatchEngine(home, away, seed=seed, initial_condition=initial_condition)
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


@app.post("/api/match/live/<session_id>/swap")
def api_match_live_swap(session_id: str):
    """Swaps two of a team's own ON-FIELD players between their two
    positions (e.g. fly-half <-> fullback mid-match) - not a substitution,
    see `MatchEngine.swap_positions`. `team` is "home"/"away";
    `position_a`/`position_b` are both currently-filled positions."""
    engine = _LIVE_MATCHES.get(session_id)
    if engine is None:
        return jsonify({"error": f"unknown live match session {session_id}"}), 404
    body = request.get_json(force=True)
    team = engine.home if body.get("team") == "home" else engine.away
    try:
        position_a = Position(body["position_a"])
        position_b = Position(body["position_b"])
    except ValueError:
        return jsonify({"error": "unknown position"}), 400

    ok = engine.swap_positions(team, position_a, position_b)
    if not ok:
        return jsonify({"error": "could not make that swap (both positions must be currently filled, and different)"}), 400
    return jsonify(_live_match_state_json(session_id, engine))


# -- API: tournament modes ------------------------------------------------
@app.get("/api/tournament/options")
def api_tournament_options():
    return jsonify({
        "real_keys": list_tournaments(),
        "real_key_names": {key: TOURNAMENTS[key].name for key in list_tournaments()},
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
            t = Tournament(teams=teams, squads=squads)
            if body["key"] == "nations_championship":
                report = t.run_nations_championship(int(body.get("season", "2026")), seed=seed)
            else:
                report = t.run_real(body["key"], season=body.get("season", "2026"), seed=seed)
        elif kind == "world_cup_2027":
            t = Tournament(teams=teams, squads=squads)
            report = t.run_world_cup_2027(fixture_mode=body.get("fixture_mode", "specific"), seed=seed)
        elif kind == "historical_world_cup":
            t = Tournament(teams=teams, squads=squads)
            report = t.run_historical_world_cup(int(body["year"]), seed=seed)
        elif kind == "historical_six_nations":
            t = Tournament(teams=teams, squads=squads)
            report = t.run_historical_six_nations(int(body["year"]), seed=seed)
        elif kind == "custom":
            fmt = body.get("format", "round_robin")
            pool_count = int(body.get("pool_count", 2))
            t = CustomTournament(teams=teams, format=fmt, squads=squads)
            report = t.run(pool_count=pool_count, seed=seed)
        else:
            return jsonify({"error": f"unknown tournament type {kind}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(_report_json(report, availability=t.availability, rankings=t.rankings))


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
    # The running `Tournament`/`CustomTournament` instance's own
    # `TournamentAvailability`, once it exists - lets `_injury_report_json`
    # compute a LIVE "matches remaining" for each injury (see
    # `_tournament_session_state_json`).
    availability: Optional[object] = None
    # The running instance's own `TeamRankingTracker` (12b), once it
    # exists - same convention/timing as `availability` above, lets
    # `_team_form_json` compute a live "Team form / rankings" section.
    rankings: Optional[object] = None


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
    injury_report = _injury_report_json(session.completed, availability=session.availability)
    card_report = _card_report_json(session.completed, availability=session.availability)
    team_form = _team_form_json(session.rankings, session.completed)
    progress = session.progress
    if session.status == "paused":
        live = _LIVE_MATCHES[session.live_session_id]
        return {
            "session_id": session_id, "status": "paused",
            "home": session.home_name, "away": session.away_name,
            "live_match": _live_match_state_json(session.live_session_id, live),
            "results_so_far": results_so_far, "progress": progress,
            "injury_report": injury_report, "card_report": card_report, "team_form": team_form,
        }
    if session.status == "finished":
        return {
            "session_id": session_id, "status": "finished",
            "report": _report_json(session.report, availability=session.availability, rankings=session.rankings),
            "results_so_far": results_so_far,
            "progress": progress, "injury_report": injury_report,
            "card_report": card_report, "team_form": team_form,
        }
    if session.status == "error":
        return {
            "session_id": session_id, "status": "error", "error": session.error,
            "results_so_far": results_so_far, "progress": progress,
            "injury_report": injury_report, "card_report": card_report, "team_form": team_form,
        }
    return {
        "session_id": session_id, "status": session.status,
        "results_so_far": results_so_far, "progress": progress,
        "injury_report": injury_report, "card_report": card_report, "team_form": team_form,
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
        if body["key"] == "nations_championship":
            return t.run_nations_championship(int(body.get("season", "2026")), seed=seed)
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
    def pause_hook(home_name, away_name, home_team, away_team, seed, initial_condition=None):
        live_session_id = _start_live_match(home_team, away_team, seed, initial_condition)
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
            session.availability = instance.availability
            session.rankings = instance.rankings

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


# -- API: Season mode (12c, reworked interactive in 13b) ------------------
# Chains every real tournament a chosen nation actually played in a chosen
# real calendar year into one continuous run (see `tournament/season.py`),
# sharing ONE `TournamentAvailability`/`TeamRankingTracker` across the
# whole season so sidelining/condition/ratings carry over between
# tournaments - not reset per tournament the way Tournament mode is.
#
# 13b: the season now runs exactly like an interactive Tournament-mode
# session (see `TournamentSession`/`_run_tournament_session` above) but for
# EVERY block chained together on one background thread: the user picks one
# nation as `my_team`, drafts it from the widest real pool
# (`build_widest_season_pool`), and that nation's own fixtures pause on the
# same pausable live-match flow (`_LIVE_MATCHES`,
# `/api/match/live/<id>/...`) while every other nation auto-drafts/auto-sims
# unattended - across every block, with no manual "play next block" call.
_SEASON_SESSIONS: Dict[str, SeasonSession] = {}
_next_season_session_id = 1


def _season_block_json(block: SeasonFixtureBlock) -> dict:
    return {"kind": block.kind, "key": block.key, "display_name": block.display_name, "team_names": block.team_names}


def _season_progress_json(instance) -> dict:
    return _tournament_progress_json(instance) if instance is not None else None


def _season_state_json(session_id: str, session: SeasonSession) -> dict:
    results_so_far = [_match_summary_json(r) for r in session.all_results]
    injury_report = _injury_report_json(session.all_results, availability=session.availability)
    card_report = _card_report_json(session.all_results, availability=session.availability)
    team_form = _team_form_json(session.rankings, session.all_results)
    base = {
        "session_id": session_id,
        "nation_code": session.nation_code, "year": session.year,
        "my_team": session.my_team,
        "blocks": [_season_block_json(b) for b in session.blocks],
        "current_block_index": session.current_block_index,
        "finished": session.finished,
        "pool": [_player_json(p) for p in session.pool],
        # 12d/13a: kept clearly separate from "pool" (never merged in) -
        # real club players carrying this union's Wikipedia flag but never
        # capped internationally for it - the "extra" part of the widest
        # draft pool `my_team` got to pick from.
        "uncapped_pool": [_player_json(p) for p in session.uncapped_pool],
        "results_so_far": results_so_far,
        "injury_report": injury_report, "card_report": card_report, "team_form": team_form,
        "progress": session.progress,
        "status": session.status,
    }
    if session.status == "paused":
        live = _LIVE_MATCHES[session.live_session_id]
        base.update({
            "home": session.home_name, "away": session.away_name,
            "live_match": _live_match_state_json(session.live_session_id, live),
        })
    elif session.status == "finished":
        base["latest_block_report"] = (
            _report_json(session.block_reports[-1], availability=session.availability, rankings=session.rankings)
            if session.block_reports else None
        )
    elif session.status == "error":
        base["error"] = session.error
    if session.current_block_report is not None:
        base["latest_block_report"] = _report_json(
            session.current_block_report, availability=session.availability, rankings=session.rankings,
        )
    return base


@app.get("/api/season/widest_pool")
def api_season_widest_pool():
    """`?nation=<code>&year=<year>` - the widest real draft pool for that
    union/year (capped internationals + 12d/13a's uncapped club pool,
    merged - see `build_widest_season_pool`), so the frontend can let the
    user draft their own matchday-23 BEFORE starting the season (their
    nation's first live fixture can happen as early as the season's first
    block)."""
    nation_code = request.args.get("nation")
    year = request.args.get("year")
    if not nation_code or not year:
        return jsonify({"error": "nation and year query params are required"}), 400
    if nation_code not in ALL_TEAM_IDS:
        return jsonify({"error": f"Unknown union short code: {nation_code}"}), 400
    pool = build_widest_season_pool(nation_code, int(year))
    _register(pool)
    return jsonify({"pool": [_player_json(p) for p in pool]})


def _run_season_session(session: SeasonSession, squad_player_ids: Dict[str, List[int]], seed: Optional[int]):
    holder: dict = {}

    def pause_hook(home_name, away_name, home_team, away_team, match_seed, initial_condition=None):
        live_session_id = _start_live_match(home_team, away_team, match_seed, initial_condition)
        session.live_session_id = live_session_id
        session.home_name, session.away_name = home_name, away_name
        session.status = "paused"
        session.resume_event.clear()
        session.state_changed.set()
        session.resume_event.wait()
        return session.pending_result

    def on_match_played(home_name, away_name, result):
        session.all_results.append(result)
        instance = holder.get("instance")
        if instance is not None:
            session.progress = _season_progress_json(instance)

    def progress_hook(instance):
        holder["instance"] = instance
        session.progress = _season_progress_json(instance)

    # Builds each block's `squads_by_team` lazily, right before that block
    # runs (next fixture data/years can differ per block, same as the old
    # per-block endpoint did) - `my_team`'s own entry always uses the
    # already-drafted widest-pool roster (`squad_player_ids`), everyone
    # else resolves via plain `squad_for_team` (capped-only).
    squads_by_block: Dict[int, Dict[str, List[Player]]] = {}
    nation = NATION_DISPLAY.get(session.nation_code)
    my_squad = [_PLAYER_BY_ID[pid] for pid in squad_player_ids.get(session.my_team or nation, []) if pid in _PLAYER_BY_ID]
    if not my_squad:
        my_squad = session.pool
    for i, block in enumerate(session.blocks):
        squads: Dict[str, List[Player]] = {}
        for team_name in block.team_names:
            if team_name == session.my_team:
                squads[team_name] = my_squad
            else:
                squads[team_name] = squad_for_team(team_name, session.year)
            if not squads[team_name]:
                session.error = f"No roster available for {team_name} in {session.year}."
                session.status = "error"
                session.state_changed.set()
                return
            _register(squads[team_name])
        squads_by_block[i] = squads

    run_season(session, squads_by_block, pause_hook, on_match_played, progress_hook, seed=seed)


@app.post("/api/season/start")
def api_season_start():
    """body: {nation_code, year, include_uncapped?, my_team?, squad_player_ids?, seed?}.
    Builds the `SeasonPlan` and this union's season-wide roster, then - if
    `my_team` is given - spawns the season's background thread (mirroring
    `/api/tournament/start`) and blocks until it either pauses on
    `my_team`'s first live fixture or the whole season finishes with no
    `my_team` fixture ever occurring. If `my_team` is omitted, the response
    is just the plan + pool so the frontend can let the user draft from it.

    `pool`/`uncapped_pool` in the response stay the original (12d, pre-13b)
    shape for backward compatibility: `pool` is always the plain capped-only
    roster, `uncapped_pool` is only populated when `include_uncapped=true`
    is passed (default false) - NOT automatically the widest pool. 13b's
    actual widest-pool draft flow (capped + uncapped merged, for `my_team`
    only) goes through the dedicated `/api/season/widest_pool` endpoint
    instead, which the frontend calls before drafting; `squad_player_ids`
    here can be built from either, the background thread doesn't care which
    endpoint supplied the ids."""
    global _next_season_session_id
    body = request.get_json(force=True)
    nation_code = body["nation_code"]
    year = int(body["year"])
    include_uncapped = bool(body.get("include_uncapped", False))
    my_team: Optional[str] = body.get("my_team") or None
    squad_player_ids: Dict[str, List[int]] = body.get("squad_player_ids", {})
    seed = body.get("seed")

    if nation_code not in ALL_TEAM_IDS:
        return jsonify({"error": f"Unknown union short code: {nation_code}"}), 400
    try:
        blocks = SeasonPlan(nation_code, year)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not blocks:
        return jsonify({"error": f"No real tournaments found for {nation_code} in {year}."}), 400

    nation = ALL_TEAM_IDS[nation_code][2]
    if my_team is not None and my_team != nation:
        return jsonify({"error": f"my_team ({my_team}) must match this union's display name ({nation})."}), 400

    pool = build_season_pool(nation_code, year)
    _register(pool)
    uncapped_pool: List[Player] = []
    if include_uncapped:
        from .data.sources.uncapped_pool import build_uncapped_pool
        capped_names = {p.name.strip().lower() for p in pool}
        uncapped_pool = [p for p in build_uncapped_pool(nation_code, nation) if p.name.strip().lower() not in capped_names]
        _register(uncapped_pool)

    session_id = f"ss{_next_season_session_id}"
    _next_season_session_id += 1
    session = SeasonSession(
        nation_code=nation_code, year=year, blocks=blocks, my_team=my_team,
        pool=pool, uncapped_pool=uncapped_pool,
        state_changed=threading.Event(), resume_event=threading.Event(),
    )
    _SEASON_SESSIONS[session_id] = session

    if my_team is None:
        session.status = "not_started"
        return jsonify(_season_state_json(session_id, session))

    thread = threading.Thread(
        target=_run_season_session, args=(session, squad_player_ids, seed), daemon=True,
    )
    session.thread = thread
    thread.start()
    session.state_changed.wait()
    session.state_changed.clear()
    return jsonify(_season_state_json(session_id, session))


@app.post("/api/season/<session_id>/resume")
def api_season_resume(session_id: str):
    """Call once `my_team`'s own live match (started by the pause above,
    under `live_match.session_id`) is finished - mirrors
    `/api/tournament/<id>/resume` exactly: hands the finished result back
    into the season's ongoing block, which auto-advances again (possibly
    straight into the NEXT block with no pause at all) until either the
    next `my_team` fixture pauses it or the whole season ends."""
    session = _SEASON_SESSIONS.get(session_id)
    if session is None:
        return jsonify({"error": f"unknown season session {session_id}"}), 404
    if session.status != "paused":
        return jsonify({"error": f"season session {session_id} is not paused (status: {session.status})"}), 400

    live = _LIVE_MATCHES.get(session.live_session_id)
    if live is None or not live.is_finished():
        return jsonify({"error": "the live match for this pause point hasn't finished yet - "
                                  "use /api/match/live/.../continue (and .../substitute) to finish it first"}), 400

    session.pending_result = live.result
    session.state_changed.clear()
    session.resume_event.set()
    session.state_changed.wait()
    session.state_changed.clear()
    return jsonify(_season_state_json(session_id, session))


@app.get("/api/season/<session_id>/state")
def api_season_state(session_id: str):
    session = _SEASON_SESSIONS.get(session_id)
    if session is None:
        return jsonify({"error": f"unknown season session {session_id}"}), 404
    return jsonify(_season_state_json(session_id, session))


# -- API: draft mode ------------------------------------------------------
# "Draft mode": a shared player pool built from whichever union/Legends
# codes the user picks, then a PES21/eFootball-style turn-based draft
# (alternating single-player picks between the human and a simple AI
# heuristic) followed by a 3-round "protect a player from your opponent"
# phase, before each side builds their final XV.
#
# Design choice (see README/task notes): the draft itself does NOT assign
# positions - it's purely "whose personal roster does this player join".
# That fits this project's existing "what if, any player in any slot"
# philosophy far better than a position-locked draft would, and it means
# the post-draft step is just the existing `TeamBuilder` UI (for the human,
# seeded from their drafted roster instead of a union pool) plus the
# existing `auto_draft_team` greedy best-fit (for the AI side) - no new
# lineup-building logic needed at all.
#
# State is a simple in-memory dataclass + Dict[str, ...] registry, the same
# convention as `_TEAMS`/`_LIVE_MATCHES`/`_TOURNAMENT_SESSIONS` above -
# single-process, single-user, local-only, reset on server restart.
DRAFT_ROSTER_TARGET = 23  # a real matchday squad: 15 starters + 8 bench, each side drafts this many before the protect phase
PROTECT_ROUNDS = 3


@dataclass
class DraftSession:
    pool_ids: List[int]           # every player id in the shared pool, in draft order
    remaining_ids: List[int]      # not yet drafted by either side
    human_roster: List[int] = field(default_factory=list)
    ai_roster: List[int] = field(default_factory=list)
    first_picker: str = "human"   # who the coin flip gave first pick to
    turn: str = "human"           # whose turn it is right now ("human" | "ai")
    phase: str = "drafting"       # "drafting" | "protect" | "done"
    protect_round: int = 0        # 0..PROTECT_ROUNDS, completed rounds so far
    protected_human: List[int] = field(default_factory=list)
    protected_ai: List[int] = field(default_factory=list)
    log: List[str] = field(default_factory=list)


_DRAFT_SESSIONS: Dict[str, DraftSession] = {}
_next_draft_session_id = 1


def _ai_best_remaining(ids: List[int]) -> Optional[int]:
    """AI drafting heuristic: of the remaining pool, take whoever rates
    highest at their own natural position (a simple, documented stand-in
    for "best player available" - the same greedy "take the best remaining
    fit" idea `auto_draft.py` already uses, just picking one player instead
    of filling a whole lineup)."""
    if not ids:
        return None
    return max(ids, key=lambda pid: _PLAYER_BY_ID[pid].rating_at(_PLAYER_BY_ID[pid].natural_position))


def _draft_session_json(session_id: str, s: DraftSession) -> dict:
    return {
        "session_id": session_id,
        "phase": s.phase,
        "turn": s.turn,
        "first_picker": s.first_picker,
        "protect_round": s.protect_round,
        "protect_rounds_total": PROTECT_ROUNDS,
        "remaining_pool": [_player_json(_PLAYER_BY_ID[pid]) for pid in s.remaining_ids],
        "human_roster": [_player_json(_PLAYER_BY_ID[pid]) for pid in s.human_roster],
        "ai_roster": [_player_json(_PLAYER_BY_ID[pid]) for pid in s.ai_roster],
        "protected_human": s.protected_human,
        "protected_ai": s.protected_ai,
        "log": s.log,
        "roster_target": DRAFT_ROSTER_TARGET,
    }


@app.post("/api/draft/start")
def api_draft_start():
    """Builds the shared pool from `codes` (union codes, all pulled at the
    one shared `season`) and/or `union_squads` (a list of
    `{code, season}` pairs - lets the SAME union be added more than once at
    DIFFERENT seasons in one draft, e.g. "Ireland 2026" and "Ireland 2025"
    together, which a single shared `codes`+`season` pair can never express),
    plus optional `legends` (bool) and optional `historical` (a list of
    `{competition: "rwc"|"sn", year: int, team: str}` historical-squad
    selections) - every source merges into the one shared pool, deduped by
    real-person name (see `_dedupe_players_by_name` - the same real player
    can easily appear in e.g. both a 2026 and a 2025 pull). Coin-flips who
    picks first (seedable via `seed` for tests - real randomness otherwise),
    and opens a new draft session. `codes`/`season`/`legends`-only requests
    keep working exactly as before; `union_squads`/`historical` are purely
    additive."""
    global _next_draft_session_id
    body = request.get_json(force=True)
    codes: List[str] = body.get("codes", [])
    season: str = body.get("season", DEFAULT_SEASON)
    union_squads: List[dict] = body.get("union_squads", [])
    include_legends: bool = bool(body.get("legends"))
    historical: List[dict] = body.get("historical", [])
    seed = body.get("seed")

    def _pull_union(code: str, season_: str):
        code = code.upper()
        if code not in POOLS:
            return None, f"unknown union code {code}"
        try:
            return POOLS[code](season=season_), None
        except TypeError:
            return POOLS[code](), None

    pool: List[Player] = []
    for code in codes:
        players, error = _pull_union(code, season)
        if error:
            return jsonify({"error": error}), 400
        pool.extend(players)
    for sel in union_squads:
        code = sel.get("code", "")
        sel_season = sel.get("season", season)
        players, error = _pull_union(code, sel_season)
        if error:
            return jsonify({"error": error}), 400
        pool.extend(players)
    if include_legends:
        pool.extend(get_all_legends())

    for sel in historical:
        competition = sel.get("competition")
        year = sel.get("year")
        team_name = sel.get("team")
        try:
            if competition == "rwc":
                from .data.sources.historical_rwc import get_rwc_year_data
                _pools, squads = get_rwc_year_data(int(year))
            elif competition == "sn":
                from .data.sources.historical_six_nations import get_six_nations_year_data
                squads = get_six_nations_year_data(int(year))
            else:
                return jsonify({"error": f"unknown historical competition {competition}"}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        squad = squads.get(team_name)
        if squad is None:
            return jsonify({"error": f"unknown historical team {team_name!r} for {competition} {year}"}), 404
        pool.extend(squad)

    pool = _dedupe_players_by_name(pool)

    if len(pool) < 2 * DRAFT_ROSTER_TARGET:
        return jsonify({
            "error": f"shared pool only has {len(pool)} players - need at least "
                     f"{2 * DRAFT_ROSTER_TARGET} for both sides to draft a full XV",
        }), 400

    _register(pool)
    pool_ids = [_ID_BY_PLAYER[id(p)] for p in pool]

    rng = random.Random(seed) if seed is not None else random.Random()
    first_picker = "human" if rng.random() < 0.5 else "ai"

    session_id = f"d{_next_draft_session_id}"
    _next_draft_session_id += 1
    session = DraftSession(
        pool_ids=pool_ids, remaining_ids=list(pool_ids),
        first_picker=first_picker, turn=first_picker,
        log=[f"Coin flip: {first_picker} picks first."],
    )
    _DRAFT_SESSIONS[session_id] = session
    return jsonify(_draft_session_json(session_id, session))


@app.get("/api/draft/<session_id>/state")
def api_draft_state(session_id: str):
    session = _DRAFT_SESSIONS.get(session_id)
    if session is None:
        return jsonify({"error": f"unknown draft session {session_id}"}), 404
    return jsonify(_draft_session_json(session_id, session))


@app.get("/api/draft/<session_id>/depth_chart")
def api_draft_depth_chart(session_id: str):
    """A "depth chart" preview of the human's drafted roster so far: for
    every real position, the top 3 roster players ranked by their
    `rating_at(position)` (same per-position rating `/api/rank` uses
    elsewhere - no rugby logic duplicated here). Draft mode deliberately
    doesn't assign positions during the draft itself (see README), so this
    is purely "if I had to assign positions right now, here's who'd play
    where" - a ranking, not a lock-in; more than one drafted player can
    reasonably fit a slot, hence top 3 rather than just the single best."""
    session = _DRAFT_SESSIONS.get(session_id)
    if session is None:
        return jsonify({"error": f"unknown draft session {session_id}"}), 404
    roster = [_PLAYER_BY_ID[pid] for pid in session.human_roster]
    chart = {}
    for pos in Position:
        ranked = sorted(roster, key=lambda p: p.rating_at(pos), reverse=True)[:3]
        chart[pos.value] = [
            {**_player_json(p), "fit": round(p.rating_at(pos), 1)}
            for p in ranked
        ]
    return jsonify({"depth_chart": chart})


def _run_ai_pick(session: DraftSession) -> None:
    pid = _ai_best_remaining(session.remaining_ids)
    if pid is None:
        return
    session.remaining_ids.remove(pid)
    session.ai_roster.append(pid)
    session.log.append(f"AI drafts {_PLAYER_BY_ID[pid].name}.")
    session.turn = "human"
    if len(session.human_roster) >= DRAFT_ROSTER_TARGET and len(session.ai_roster) >= DRAFT_ROSTER_TARGET:
        session.phase = "protect"


@app.post("/api/draft/<session_id>/pick")
def api_draft_pick(session_id: str):
    """One human pick, immediately followed by one AI pick (if the draft
    isn't finished and it's the AI's turn next) - keeps the turn-based flow
    to a single request/response per human action instead of needing the
    frontend to poll for the AI's move."""
    session = _DRAFT_SESSIONS.get(session_id)
    if session is None:
        return jsonify({"error": f"unknown draft session {session_id}"}), 404
    if session.phase != "drafting":
        return jsonify({"error": f"draft is not in its drafting phase (phase: {session.phase})"}), 400

    body = request.get_json(force=True)
    player_id = body.get("player_id")

    # If it's currently the AI's turn (e.g. AI picks first, or the draft
    # alternates back to it), let it move and return immediately - this
    # same request is then just "please let the AI take its turn", not a
    # human pick, so it never falls through to needing a `player_id`.
    if session.turn == "ai":
        _run_ai_pick(session)
        return jsonify(_draft_session_json(session_id, session))

    if session.turn != "human":
        return jsonify({"error": "not the human's turn"}), 400
    if player_id not in session.remaining_ids:
        return jsonify({"error": "that player isn't in the remaining shared pool"}), 400
    if len(session.human_roster) >= DRAFT_ROSTER_TARGET:
        return jsonify({"error": "your roster is already full"}), 400

    session.remaining_ids.remove(player_id)
    session.human_roster.append(player_id)
    session.log.append(f"You draft {_PLAYER_BY_ID[player_id].name}.")
    session.turn = "ai"

    if len(session.human_roster) >= DRAFT_ROSTER_TARGET and len(session.ai_roster) >= DRAFT_ROSTER_TARGET:
        session.phase = "protect"
    elif len(session.ai_roster) < DRAFT_ROSTER_TARGET:
        _run_ai_pick(session)

    return jsonify(_draft_session_json(session_id, session))


@app.post("/api/draft/<session_id>/protect_round")
def api_draft_protect_round(session_id: str):
    """Resolves one of the 3 post-draft protect/poach rounds (PES21/
    eFootball-style): the human names up to one of their own already-
    drafted players to protect (`protect_id`) and, optionally, one
    unprotected AI-roster player to poach (`poach_id`); the AI auto-
    protects its own best unprotected player and attempts to poach the
    human's best unprotected player. The explicit, non-negotiable rule: a
    player already marked protected (by either side, in this or an earlier
    round) can never be poached."""
    session = _DRAFT_SESSIONS.get(session_id)
    if session is None:
        return jsonify({"error": f"unknown draft session {session_id}"}), 404
    if session.phase != "protect":
        return jsonify({"error": f"not in the protect phase (phase: {session.phase})"}), 400
    if session.protect_round >= PROTECT_ROUNDS:
        return jsonify({"error": "all protect rounds are already complete"}), 400

    body = request.get_json(force=True)
    human_protect_id = body.get("protect_id")
    human_poach_id = body.get("poach_id")

    # 1) Protections are locked in first, simultaneously, before any poach
    #    is resolved - so a poach this same round can never target a
    #    player protected in this same round.
    if human_protect_id is not None:
        if human_protect_id in session.human_roster and human_protect_id not in session.protected_human:
            session.protected_human.append(human_protect_id)
            session.log.append(f"You protect {_PLAYER_BY_ID[human_protect_id].name}.")

    ai_unprotected = [pid for pid in session.ai_roster if pid not in session.protected_ai]
    ai_protect_id = _ai_best_remaining(ai_unprotected) if ai_unprotected else None
    if ai_protect_id is not None:
        session.protected_ai.append(ai_protect_id)
        session.log.append(f"AI protects {_PLAYER_BY_ID[ai_protect_id].name}.")

    # 2) Poaches - a protected player (just now, or from an earlier round)
    #    can never be taken, no matter what.
    if human_poach_id is not None:
        if human_poach_id in session.ai_roster and human_poach_id not in session.protected_ai:
            session.ai_roster.remove(human_poach_id)
            session.human_roster.append(human_poach_id)
            session.log.append(f"You poach {_PLAYER_BY_ID[human_poach_id].name} from the AI.")
        else:
            session.log.append("Your poach attempt failed (player is protected or not on the AI's roster).")

    human_unprotected = [pid for pid in session.human_roster if pid not in session.protected_human]
    ai_poach_id = _ai_best_remaining(human_unprotected) if human_unprotected else None
    if ai_poach_id is not None:
        session.human_roster.remove(ai_poach_id)
        session.ai_roster.append(ai_poach_id)
        session.log.append(f"AI poaches {_PLAYER_BY_ID[ai_poach_id].name} from you.")

    session.protect_round += 1
    if session.protect_round >= PROTECT_ROUNDS:
        session.phase = "done"
        session.log.append("Protect phase complete - build your final lineup.")

    return jsonify(_draft_session_json(session_id, session))


@app.post("/api/draft/<session_id>/finalize_ai")
def api_draft_finalize_ai(session_id: str):
    """Auto-drafts the AI's final lineup (reusing the existing greedy
    `auto_draft_team`, same as everywhere else in this codebase) from
    whatever ended up on its roster after the protect phase. The human
    side isn't finalized here - they build their own lineup through the
    normal `TeamBuilder` UI, seeded from `human_roster` below."""
    session = _DRAFT_SESSIONS.get(session_id)
    if session is None:
        return jsonify({"error": f"unknown draft session {session_id}"}), 404
    if session.phase != "done":
        return jsonify({"error": f"protect phase isn't finished yet (phase: {session.phase})"}), 400

    ai_pool = [_PLAYER_BY_ID[pid] for pid in session.ai_roster]
    team = auto_draft_team("AI Draft XV", ai_pool, short_code="AID")
    team_id = _register_team(team)

    return jsonify({
        "team_id": team_id,
        "name": team.name,
        "problems": team.lineup.validate(),
        "human_roster": [_player_json(_PLAYER_BY_ID[pid]) for pid in session.human_roster],
    })


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
