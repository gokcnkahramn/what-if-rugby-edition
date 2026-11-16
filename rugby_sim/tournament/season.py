"""Season mode: chain every real tournament a given nation actually played
in a given real calendar year into one continuous run, with
injuries/suspensions/condition (`TournamentAvailability`) and team rankings
(`TeamRankingTracker`) carried over BETWEEN tournaments instead of reset
fresh for each one - the thing `Tournament`/`CustomTournament`'s
`availability=`/`rankings=` constructor params (see `tournament.py`) exist
to make possible.

13b reworks this from v1's synchronous, fully-auto-simmed-only
`play_next_block` (called once per HTTP request, no user control at all)
into the same background-thread pause/resume mechanism `webapp.py`'s
`TournamentSession`/`_run_tournament_session` already use for interactive
Tournament mode: one `SeasonSession` owns a `threading.Event` pair and runs
its WHOLE season (every block, chained automatically) on a single
background thread, pausing only when the session's own `my_team` has a
fixture - every other, AI-controlled nation auto-drafts and auto-sims
unattended, exactly like Tournament mode's non-`my_team` fixtures do today.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..data.sources.historical_rwc import AVAILABLE_RWC_YEARS, get_rwc_year_data
from ..data.sources.pool_builder import ALL_TEAM_IDS, NATION_DISPLAY, build_season_pool
from ..engine.match_engine import MatchResult
from ..models.player import Player
from .availability import TournamentAvailability
from .rankings import TeamRankingTracker
from .real_fixtures import TOURNAMENTS, load_real_fixtures
from .tournament import Tournament, TournamentReport


@dataclass
class SeasonFixtureBlock:
    kind: str  # "real" | "historical_world_cup"
    key: str  # e.g. "six_nations", or the RWC year as a string
    display_name: str
    team_names: List[str]  # every real union display name involved in this block


def _real_block_for(tournament_key: str, year: int) -> Optional[SeasonFixtureBlock]:
    """Builds this tournament's block for `year` from whatever real fixture
    data exists, regardless of which union the season itself belongs to -
    a season no longer only includes blocks its own nation actually played
    in; every real tournament with any data for `year` is simulated in
    full, feeding `TeamRankingTracker` for every union involved (see
    module docstring)."""
    fixtures = load_real_fixtures(tournament_key, season=str(year))
    if not fixtures:
        return None
    team_names = sorted({f.home for f in fixtures} | {f.away for f in fixtures})
    template = TOURNAMENTS[tournament_key]
    return SeasonFixtureBlock(
        kind="real", key=tournament_key,
        display_name=f"{template.name} {year}", team_names=team_names,
    )


def _world_cup_block_for(year: int) -> Optional[SeasonFixtureBlock]:
    if year not in AVAILABLE_RWC_YEARS:
        return None
    pools, _squads = get_rwc_year_data(year)
    team_names = sorted({name for pool in pools.values() for name in pool})
    return SeasonFixtureBlock(
        kind="historical_world_cup", key=str(year),
        display_name=f"{year} Rugby World Cup", team_names=team_names,
    )


def SeasonPlan(nation_code: str, year: int) -> List[SeasonFixtureBlock]:
    """Every real tournament block with ANY real fixture data for `year` -
    not just the ones `nation_code`'s own union happened to play in. Every
    other union's real matches that year are still fully simulated (through
    the same `Tournament`/`MatchEngine` machinery) so the shared
    `TeamRankingTracker` moves for everyone, exactly like Tournament mode's
    non-`my_team` fixtures already do - `nation_code` only determines which
    union is this session's `my_team` (passed separately so ITS fixtures
    pause for live play elsewhere in `webapp.py`); it does NOT filter which
    blocks are included. A union with no real fixture data at all that year
    still gets every available block, just with no fixture ever pausing it
    - a legitimate outcome, not an error (see module docstring/Ask 1).
    Blocks are returned in a fixed, real calendar order (Six Nations in
    Jan-Mar, Rugby Championship in Aug-Oct, World Cup in Sep-Oct of a World
    Cup year, Autumn Nations Series in Nov) - never an arbitrary dict
    order."""
    if nation_code not in ALL_TEAM_IDS:
        raise ValueError(f"Unknown union short code: {nation_code}")

    blocks: List[SeasonFixtureBlock] = []
    six_nations = _real_block_for("six_nations", year)
    if six_nations:
        blocks.append(six_nations)
    # Rugby Europe Championship sits in the same Jan-Mar window as Six
    # Nations (see `real_fixtures.py`), so it's placed right alongside it.
    rugby_europe_championship = _real_block_for("rugby_europe_championship", year)
    if rugby_europe_championship:
        blocks.append(rugby_europe_championship)
    rugby_championship = _real_block_for("rugby_championship", year)
    if rugby_championship:
        blocks.append(rugby_championship)
    # Pacific Nations Cup (Tier 2 coverage - see real_fixtures.py) sits in
    # the same Aug-Sep window as the Rugby Championship, so it's placed
    # right after it, before the (Sep-Oct) World Cup slot.
    pacific_nations_cup = _real_block_for("pacific_nations_cup", year)
    if pacific_nations_cup:
        blocks.append(pacific_nations_cup)
    world_cup = _world_cup_block_for(year)
    if world_cup:
        blocks.append(world_cup)
    # Nations Championship (new in 2026) spans BOTH a July window and a
    # November window, so it logically sits after the Rugby Championship's
    # Aug-Oct window (its July round comes before that, but its November
    # round/finals weekend is the dominant, latest part of its calendar
    # footprint) and alongside the old Autumn Nations Series slot. In
    # practice "autumn_nations_series" and "nations_championship" should
    # never both produce a block for the same real year - one replaced the
    # other in 2026 - so the order between these two specifically doesn't
    # matter; it's placed first here purely to keep ordering stable/
    # deterministic if that assumption is ever wrong.
    nations_championship = _real_block_for("nations_championship", year)
    if nations_championship:
        blocks.append(nations_championship)
    autumn_nations = _real_block_for("autumn_nations_series", year)
    if autumn_nations:
        blocks.append(autumn_nations)
    return blocks


def squad_for_team(team_name: str, year: int) -> List[Player]:
    """Plain (capped-only) roster for any non-`my_team` union in a season
    block - same lookup `webapp.py`'s old `_season_squad_for` used, moved
    here so both the background-thread runner and webapp.py can share it."""
    code = next((c for c, (_, _, nation) in ALL_TEAM_IDS.items() if nation == team_name), None)
    if code is None:
        return []
    return build_season_pool(code, year)


@dataclass
class SeasonSession:
    """Same dataclass-of-live-state shape convention as webapp.py's own
    `TournamentSession` (13b) - owns the ONE shared `TournamentAvailability`
    and `TeamRankingTracker` for the whole season (passed into every
    block's `Tournament`), the ordered list of per-block reports/results,
    AND (new in 13b) the same threading.Event pause/resume pair + live-
    match bookkeeping `TournamentSession` uses, so an interactive
    `my_team` fixture anywhere in the season can pause this session's
    background thread exactly like a `my_team` fixture pauses a
    Tournament-mode session."""
    nation_code: str
    year: int
    blocks: List[SeasonFixtureBlock]
    my_team: Optional[str] = None
    pool: List[Player] = field(default_factory=list)
    # 12d: real club players carrying this union's flag on Wikipedia but
    # never capped internationally there - kept as a SEPARATE list from
    # `pool` (never silently merged) so provenance stays visible. In 13b
    # this is the "extra" portion of `my_team`'s widest draft pool.
    uncapped_pool: List[Player] = field(default_factory=list)
    availability: TournamentAvailability = field(default_factory=TournamentAvailability)
    rankings: TeamRankingTracker = field(default_factory=TeamRankingTracker)
    current_block_index: int = 0
    block_reports: List[TournamentReport] = field(default_factory=list)
    all_results: List[MatchResult] = field(default_factory=list)  # flattened across blocks

    # -- threading state (13b, mirrors webapp.TournamentSession) --------
    state_changed: threading.Event = field(default_factory=threading.Event)
    resume_event: threading.Event = field(default_factory=threading.Event)
    status: str = "running"  # "running" | "paused" | "finished" | "error"
    live_session_id: Optional[str] = None
    home_name: Optional[str] = None
    away_name: Optional[str] = None
    pending_result: Optional[MatchResult] = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None
    # Live progress of whichever block is currently running (same shape
    # `_tournament_progress_json` builds off a `Tournament` instance).
    progress: Optional[dict] = None
    current_block_report: Optional[TournamentReport] = None

    @property
    def finished(self) -> bool:
        return self.current_block_index >= len(self.blocks)


def run_season(
    session: SeasonSession,
    squads_by_team_by_block: Dict[int, Dict[str, List[Player]]],
    pause_hook: Callable,
    on_match_played: Callable,
    progress_hook: Callable,
    seed: Optional[int] = None,
) -> None:
    """Background-thread entry point (mirrors `webapp._run_tournament_session`
    shape exactly, just looping over every block in `session.blocks`
    instead of running a single tournament): for each block, builds that
    block's own `Tournament(squads=..., my_team=session.my_team,
    pause_hook=..., on_match_played=..., rankings=session.rankings,
    availability=session.availability)`, runs the right `run_real`/
    `run_historical_world_cup` method, appends the report, advances
    `current_block_index`, and - the one real adaptation vs. the single-
    tournament version - CONTINUES straight into the next block without
    returning control to the caller, since nothing needs to happen between
    blocks except moving on; the caller only gets control back when
    `pause_hook` blocks it (a `my_team` fixture) or the whole season ends.
    `squads_by_team_by_block[i]` must already cover every name in
    `session.blocks[i].team_names` - the caller (webapp.py) builds these
    up front, using `session.pool`/`session.uncapped_pool` (already merged
    into the widest pool by the caller) for `session.my_team` and plain
    `squad_for_team` for every other name."""
    try:
        for i, block in enumerate(session.blocks):
            squads = squads_by_team_by_block[i]
            t = Tournament(
                squads=squads, my_team=session.my_team, pause_hook=pause_hook,
                on_match_played=on_match_played, rankings=session.rankings,
                availability=session.availability,
            )
            progress_hook(t)
            if block.kind == "real":
                if block.key == "nations_championship":
                    report = t.run_nations_championship(int(session.year), seed=seed)
                else:
                    report = t.run_real(block.key, season=str(session.year), seed=seed)
            elif block.kind == "historical_world_cup":
                report = t.run_historical_world_cup(int(block.key), seed=seed)
            else:
                raise ValueError(f"Unknown season block kind: {block.kind}")

            session.block_reports.append(report)
            session.current_block_report = report
            session.all_results.extend(report.results)
            session.current_block_index = i + 1
        session.status = "finished"
    except ValueError as e:
        session.error = str(e)
        session.status = "error"
    except Exception as e:  # pragma: no cover - defensive, surfaces instead of hanging the request
        session.error = f"unexpected error: {e}"
        session.status = "error"
    finally:
        session.state_changed.set()
