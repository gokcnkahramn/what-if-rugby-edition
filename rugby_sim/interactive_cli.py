"""Interactive, prompt-driven "what if" builder.

    python -m rugby_sim.interactive_cli

Lets you, from a terminal, without writing any code:
- for each team, pick how it's built: **by nation** (pick a union or the
  Barbarians - its whole real capped pool, for any season the data covers,
  loads automatically and becomes the team) or **free pool** (mix any
  pool(s)/season(s) yourself for a fantasy roster, e.g. a few Fiji players
  dropped into an "England" side) - nothing stops you putting any player in
  any position either way, that's the whole point of the project;
- draft all 15 starting positions + a captain, one at a time, seeing the
  fit rating for each candidate at that specific slot;
- then either simulate a single match, a real tournament's actual fixture
  list (Six Nations, Rugby Championship, ...), or a custom round-robin /
  pool+knockout tournament - for however many teams you draft.
- in "free pool" mode only, add `LEG` to mix in ~30 Hall of Fame legends
  (Jonah Lomu, Richie McCaw, Dan Carter, Jonny Wilkinson, ...) spanning
  different eras/nations - they're deliberately excluded from "by nation"
  drafting and real tournaments, since they never played for a 2026 squad.
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional

# Some real player names use characters outside Windows consoles' default
# codepage (e.g. Namibian "!Gaoseb"'s click consonant) - never crash on
# printing a real name, just best-effort transliterate what can't display.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="backslashreplace")
    except Exception:
        pass

from .data.legends import get_all_legends
from .data.national_teams import POOLS
from .data.sources.pool_builder import ALL_TEAM_IDS
from .engine import MatchEngine
from .models import Lineup, Player, Position, Team
from .tournament import CustomTournament, Tournament, list_tournaments

# Hall of Fame "legends" are deliberately NOT part of `POOLS` - they never
# show up in "by nation" drafting or a real tournament's team list, only
# here, as an extra option when mixing a free/custom-roster team.
LEGENDS_CODE = "LEG"
HISTORICAL_CODE = "HIST"

# code -> real nation name (e.g. "ENG" -> "England"), used to suggest/default
# a code when a real fixture's team name already tells us which union it is.
NATION_DISPLAY = {code: nation for code, (_, _, nation) in ALL_TEAM_IDS.items()}
NATION_DISPLAY["BAR"] = "Barbarians"
NATION_DISPLAY["HKG"] = "Hong Kong"
NATION_DISPLAY["ZIM"] = "Zimbabwe"
CODE_BY_NATION_NAME = {v: k for k, v in NATION_DISPLAY.items()}


def _prompt(msg: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    raw = input(f"{msg}{suffix}: ").strip()
    return raw or (default or "")


def _choose_index(prompt: str, options: List[str], allow_blank: bool = False) -> Optional[int]:
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = _prompt(prompt)
        if allow_blank and not raw:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print("  (invalid choice, try again)")


def _pull_pool(code: str, season: str) -> List[Player]:
    print(f"  Pulling {code} {season} pool (first time may hit the network)...")
    try:
        pool = POOLS[code](season=season)
    except TypeError:
        pool = POOLS[code]()  # Barbarians ignores season but accepts it too
    if not pool:
        print(f"  No players found for {code} {season}.")
    else:
        print(f"  +{len(pool)} players added from {code} {season}.")
    return pool


def _pick_single_nation_pool(suggested_code: Optional[str] = None) -> tuple[List[Player], str]:
    """Mode 1: pick exactly one union/Barbarians pool - the team is that
    nation, nothing else gets mixed in. Picking the team *is* picking the
    nation: its whole capped pool loads automatically."""
    codes = sorted(POOLS.keys())
    print("\nAvailable unions/pools:", ", ".join(f"{c} ({NATION_DISPLAY.get(c, c)})" for c in codes))
    while True:
        code = _prompt("Union/pool code", default=suggested_code).upper()
        if code in POOLS:
            break
        print(f"  Unknown code '{code}'. Options: {', '.join(codes)}")
    season = _prompt("Season", default="2026")
    pool = _pull_pool(code, season)
    return pool, code


def _pick_pools_for_team() -> List[Player]:
    """Mode 2: lets the user merge one or more union/Barbarians pools (any
    season, any mix) into the pool of players available for one team - a
    fully free "what if" roster, not tied to a single nation. This is also
    the only place Hall of Fame legends (`LEG`) are selectable - add them
    deliberately, they never come bundled into a nation's own pool."""
    codes = sorted(POOLS.keys())
    available: List[Player] = []
    print(f"\nAvailable player pools: {', '.join(codes)}, {LEGENDS_CODE} (Hall of Fame legends), "
          f"{HISTORICAL_CODE} (a specific historical World Cup/Six Nations squad)")
    while True:
        code = _prompt("Add a union/pool code (blank when done)").upper()
        if not code:
            break
        if code == LEGENDS_CODE:
            print("  Pulling the full Hall of Fame roster (first time may hit the "
                  "network for ~190 pages - later calls are instant)...")
            legends = get_all_legends()
            print(f"  +{len(legends)} Hall of Fame legends added.")
            available.extend(legends)
            continue
        if code == HISTORICAL_CODE:
            available.extend(_pick_historical_squad())
            continue
        if code not in POOLS:
            print(f"  Unknown code '{code}'. Options: {', '.join(codes)}, {LEGENDS_CODE}, {HISTORICAL_CODE}")
            continue
        season = _prompt("  Season for this pool", default="2026")
        available.extend(_pull_pool(code, season))
    return available


def _pick_historical_squad() -> List[Player]:
    """Pulls one specific team's real historical squad (a past Rugby World
    Cup or Six Nations edition) into whatever free-pool team is being
    built - usable for a single match or a custom tournament, same as any
    other pool source, not just the dedicated historical-tournament mode."""
    from .data.sources.historical_rwc import AVAILABLE_RWC_YEARS, get_rwc_year_data
    from .data.sources.historical_six_nations import (
        AVAILABLE_SIX_NATIONS_YEARS,
        get_six_nations_year_data,
    )

    comp_idx = _choose_index(
        "  Which historical competition?",
        ["Rugby World Cup", "Six Nations Championship"],
    )
    if comp_idx == 0:
        year_options = [str(y) for y in AVAILABLE_RWC_YEARS]
        year_idx = _choose_index("  Pick a World Cup year", year_options)
        year = AVAILABLE_RWC_YEARS[year_idx]
        print(f"  Loading the {year} Rugby World Cup's real squads (first time is "
              f"network-heavy - cached after)...")
        _pools, squads = get_rwc_year_data(year)
    else:
        year_options = [str(y) for y in AVAILABLE_SIX_NATIONS_YEARS]
        year_idx = _choose_index("  Pick a Six Nations year", year_options)
        year = AVAILABLE_SIX_NATIONS_YEARS[year_idx]
        print(f"  Loading the {year} Six Nations' real squads (first time is "
              f"network-heavy - cached after)...")
        squads = get_six_nations_year_data(year)

    team_names = sorted(squads.keys())
    team_idx = _choose_index("  Which team's squad?", team_names)
    team_name = team_names[team_idx]
    squad = squads[team_name]
    print(f"  +{len(squad)} players added from {team_name}'s {year} squad.")
    return squad


def _draft_lineup(available: List[Player]) -> Lineup:
    lineup = Lineup()
    remaining = list(available)

    for pos in Position:
        print(f"\n-- {pos.value} --")
        ranked = sorted(remaining, key=lambda p: p.rating_at(pos), reverse=True)[:8]
        if not ranked:
            print("  (no players left in the pool - skipping this slot)")
            continue
        labels = [
            f"{p.name} ({p.nation}{', ' + p.era if p.era else ''}) "
            f"- fit {p.rating_at(pos)} (natural: {p.natural_position.value})"
            for p in ranked
        ]
        labels.append("search by name instead")
        idx = _choose_index(f"Pick for {pos.value} (number)", labels)
        if idx is None:
            continue
        if idx == len(labels) - 1:
            query = _prompt("  Name contains").lower()
            matches = [p for p in remaining if query in p.name.lower()]
            if not matches:
                print("  No match, skipping this slot.")
                continue
            match_labels = [f"{p.name} ({p.nation}) - fit {p.rating_at(pos)}" for p in matches]
            match_idx = _choose_index("  Pick one", match_labels)
            if match_idx is None:
                continue
            chosen = matches[match_idx]
        else:
            chosen = ranked[idx]

        lineup.set_starter(pos, chosen)
        remaining = [p for p in remaining if p is not chosen]

    if lineup.starters:
        names = [slot.player.name for slot in lineup.starters.values()]
        cap_idx = _choose_index("\nPick captain", names)
        if cap_idx is not None:
            lineup.captain = list(lineup.starters.values())[cap_idx].player

    return lineup


def _draft_team(fixed_label: Optional[str] = None, suggested_code_override: Optional[str] = None) -> Team:
    """Drafts one team. Three modes, chosen up front:
    1. By nation - pick one union/Barbarians pool; that nation's whole
       capped pool loads automatically, and (unless `fixed_label` pins the
       name, as for a real-tournament side) becomes the team's name too.
    2. Free pool - mix any pool(s)/season(s) yourself for a fantasy roster.
    3. Load from file - a squad previously saved with `save_team` (see
       `rugby_sim/data/squad_repository.py`), e.g. from an earlier session.
    """
    header = fixed_label or "new team"
    print(f"\n=== Drafting: {header} ===")

    mode_options = [
        "By nation - pick a union/Barbarians, its whole pool loads automatically",
        "Free pool - mix any pools/seasons yourself (fantasy roster)",
        "Load from a saved file",
    ]
    mode_idx = _choose_index("How do you want to build this team?", mode_options)

    if mode_idx == 2:
        from .data.squad_repository import load_team
        path = _prompt("Path to the saved team JSON file")
        try:
            team = load_team(path)
        except (FileNotFoundError, KeyError, ValueError) as e:
            raise SystemExit(f"Could not load '{path}': {e}")
        problems = team.lineup.validate()
        if problems:
            print(f"\nWarning - loaded lineup incomplete: {problems}")
        print(f"Loaded '{team.name}' from {path}.")
        return team

    suggested_code = suggested_code_override or (CODE_BY_NATION_NAME.get(fixed_label) if fixed_label else None)
    if mode_idx == 0:
        available, code = _pick_single_nation_pool(suggested_code=suggested_code)
        default_name = NATION_DISPLAY.get(code, code)
    else:
        available = _pick_pools_for_team()
        default_name = fixed_label or "Team"

    if not available:
        raise SystemExit(f"No players available for {header}, aborting.")

    name = fixed_label or _prompt("Team name", default=default_name)
    if fixed_label:
        print(f"Team name: {name} (fixed - matches the real fixture list)")

    lineup = _draft_lineup(available)
    problems = lineup.validate()
    if problems:
        print(f"\nWarning - lineup incomplete: {problems}")
    team = Team(name=name, short_code=name[:3].upper(), lineup=lineup)

    save_raw = _prompt("Save this team to a file for next time? (path, or blank to skip)")
    if save_raw:
        from .data.squad_repository import save_team
        save_team(team, save_raw)
        print(f"Saved to {save_raw}.")

    return team


SUB_CHECKPOINTS = [20, 40, 60, 70]


def _run_single_match():
    home = _draft_team()
    away = _draft_team()
    seed_raw = _prompt("Random seed (blank = random)")
    seed = int(seed_raw) if seed_raw.isdigit() else None

    live_idx = _choose_index(
        "Pause the match partway through to make substitutions yourself?",
        ["No - just simulate the full 80 minutes", "Yes - pause a few times during the match"],
    )
    engine = MatchEngine(home, away, seed=seed)
    if live_idx == 1:
        result = engine.run_interactive(SUB_CHECKPOINTS, _on_match_checkpoint)
    else:
        result = engine.run()
    result.print_report()


def _on_match_checkpoint(engine: MatchEngine, minute: int) -> None:
    """Pauses a live-run match at one checkpoint: shows the score so far
    and lets the user make zero or more manual substitutions (pick a team,
    a position to change, and which bench player comes on) before play
    resumes toward the next checkpoint."""
    result = engine.result
    print(f"\n--- {minute}' (paused) --- {result.scoreline()}")
    for team in (engine.home, engine.away):
        bench = engine.bench_for(team)
        bench_desc = ", ".join(p.name for p in bench) if bench else "(none left)"
        print(f"  {team.name} bench: {bench_desc}")

    while True:
        make_sub = _prompt("Make a substitution now? (y/N)", default="n").lower()
        if make_sub not in ("y", "yes"):
            break
        _prompt_one_substitution(engine)


def _prompt_one_substitution(engine: MatchEngine) -> None:
    team_idx = _choose_index("  Which team?", [engine.home.name, engine.away.name])
    team = engine.home if team_idx == 0 else engine.away
    bench = engine.bench_for(team)
    if not bench:
        print("  No bench players left for that team.")
        return

    active = engine.active_lineup(team)
    position_options = [f"{pos.value} ({slot.player.name})" for pos, slot in active.items()]
    positions = list(active.keys())
    pos_idx = _choose_index("  Which position comes off?", position_options)
    position = positions[pos_idx]

    bench_labels = [f"{p.name} - fit {p.rating_at(position)} at {position.value}" for p in bench]
    bench_idx = _choose_index("  Which bench player comes on?", bench_labels)
    chosen = bench[bench_idx]

    ok = engine.apply_substitution(team, position, bench_player=chosen)
    if ok:
        print(f"  {chosen.name} is on for {team.name} at {position.value}.")
    else:
        print("  Could not make that substitution (bench empty or 8-sub cap reached).")


WORLD_CUP_2027_LABEL = "rugby_world_cup_2027 (real pool draw, no fixtures exist yet)"
HISTORICAL_RWC_LABEL = "historical_rugby_world_cup (1995-2023, real squads from Wikipedia)"
HISTORICAL_SIX_NATIONS_LABEL = "historical_six_nations (2009-2021, real squads from Wikipedia)"


def _ask_fixture_mode() -> str:
    """Shared "specific vs random" prompt. "Specific" means a fixed,
    deterministic order (the real draw's pool order for the 2027 World Cup;
    the order you typed teams in for a custom tournament). "Random" shuffles
    that order (per pool, for the World Cup; the whole team list, for a
    custom tournament) before generating fixtures - same teams, different
    match order each time you pick it (unless you also fix a seed)."""
    options = [
        "Specific (fixed/deterministic order)",
        "Random (shuffle the order before generating fixtures)",
    ]
    idx = _choose_index("Fixture order", options)
    return "specific" if idx == 0 else "random"


def _ask_squad_mode() -> bool:
    """Shared choice for every tournament-building flow: a fixed lineup for
    the whole tournament (the original behavior - draft one XV per team,
    it never changes), or a fresh auto-drafted lineup before every single
    match, built from that team's full pool. The second option is what
    makes an in-match injury or red card actually matter past the match it
    happened in - an injured/sent-off player sits out the team's next
    match (see `tournament/availability.py`), which a fixed lineup can
    never reflect since it's the same 15 names every time regardless of
    what happened last match."""
    idx = _choose_index(
        "Squad mode for every team in this tournament",
        [
            "Fixed lineup - draft one XV per team, reused for every match (original behavior)",
            "Fresh squad every match - auto-draft a new best XV before each match from each "
            "team's full pool (an injury/red card sidelines that player for the next match)",
        ],
    )
    return idx == 1


def _pick_team_pool(label: str) -> List[Player]:
    """Squads-mode's equivalent of `_draft_team` - gets a player *pool* for
    this team (same by-nation/free-pool/legends/historical-squad choices
    as `_pick_pools_for_team`), but doesn't draft one fixed lineup from it -
    a fresh lineup gets auto-drafted from this pool before every match."""
    print(f"\n=== Pool for: {label} (fresh auto-drafted lineup every match) ===")
    pool = _pick_pools_for_team()
    if not pool:
        raise SystemExit(f"No players available for {label}, aborting.")
    return pool


def _run_real_tournament():
    keys = list_tournaments() + [WORLD_CUP_2027_LABEL, HISTORICAL_RWC_LABEL, HISTORICAL_SIX_NATIONS_LABEL]
    idx = _choose_index("Pick a real tournament", keys)
    key = keys[idx]

    if key == WORLD_CUP_2027_LABEL:
        _run_world_cup_2027()
        return
    if key == HISTORICAL_RWC_LABEL:
        _run_historical_world_cup()
        return
    if key == HISTORICAL_SIX_NATIONS_LABEL:
        _run_historical_six_nations()
        return

    season = _prompt("Season", default="2026")
    print(f"\nYou'll need a Team for every side that actually played in {key} {season}.")

    from .tournament.real_fixtures import load_real_fixtures
    fixtures = load_real_fixtures(key, season)
    if not fixtures:
        print("No fixtures found for that tournament/season.")
        return
    team_names = sorted({f.home for f in fixtures} | {f.away for f in fixtures})
    print(f"Teams in this competition: {', '.join(team_names)}")

    fresh_each_match = _ask_squad_mode()
    teams: Dict[str, Team] = {}
    squads: Dict[str, List[Player]] = {}
    for name in team_names:
        if fresh_each_match:
            squads[name] = _pick_team_pool(name)
        else:
            teams[name] = _draft_team(fixed_label=name)

    seed_raw = _prompt("Random seed (blank = random)")
    seed = int(seed_raw) if seed_raw.isdigit() else None
    report = Tournament(teams=teams, squads=squads).run_real(key, season=season, seed=seed)
    report.print_report()


def _run_world_cup_2027():
    """The 2027 Rugby World Cup hasn't been played - World Rugby's real
    pool draw (held 3 Dec 2025) is used, but since there's no fixture list
    to replay, you choose whether pool play follows that draw's order
    ("specific") or a shuffled one ("random") - see `world_cup_2027.py`."""
    from .tournament import ALL_TEAMS_2027, CODE_BY_NATION, POOLS_2027

    print("\n2027 Rugby World Cup - real pool draw:")
    for pool_name, pool_teams in POOLS_2027.items():
        print(f"  Pool {pool_name}: {', '.join(pool_teams)}")

    fixture_mode = _ask_fixture_mode()
    fresh_each_match = _ask_squad_mode()

    teams: Dict[str, Team] = {}
    squads: Dict[str, List[Player]] = {}
    for name in ALL_TEAMS_2027:
        if fresh_each_match:
            squads[name] = _pick_team_pool(name)
        else:
            teams[name] = _draft_team(fixed_label=name, suggested_code_override=CODE_BY_NATION.get(name))

    seed_raw = _prompt("Random seed (blank = random)")
    seed = int(seed_raw) if seed_raw.isdigit() else None
    report = Tournament(teams=teams, squads=squads).run_world_cup_2027(fixture_mode=fixture_mode, seed=seed)
    report.print_report()


def _draft_team_from_fixed_pool(label: str, available: List[Player]) -> Team:
    """Like `_draft_team`, but the available players come from a specific
    pre-built squad (a historical World Cup's real roster) rather than
    `POOLS`/`get_all_legends` - so "by nation"/"free pool" don't apply here,
    just auto-draft-or-draft-yourself from that exact squad."""
    print(f"\n=== Drafting: {label} ({len(available)} players in this historical squad) ===")
    if not available:
        raise SystemExit(f"No players available for {label}, aborting.")
    options = ["Auto-draft (recommended)", "Draft yourself"]
    idx = _choose_index("How do you want to build this team?", options)
    if idx == 0:
        from .data.sources.auto_draft import auto_draft_team
        return auto_draft_team(label, available, short_code=label[:3].upper())

    lineup = _draft_lineup(available)
    problems = lineup.validate()
    if problems:
        print(f"\nWarning - lineup incomplete: {problems}")
    return Team(name=label, short_code=label[:3].upper(), lineup=lineup)


def _run_historical_world_cup():
    """Replays a real past World Cup (1995-2023) with its real pool draw
    and real squads, scraped from that edition's Wikipedia squads page -
    see `historical_rwc.py`. Pre-2018 players have no rugbydata box scores
    to derive a rating from, so they get a position-archetype estimate
    scaled by that union's general competitiveness (same honest convention
    as "Legend mode") instead of a scouted number."""
    from .data.sources.historical_rwc import AVAILABLE_RWC_YEARS, get_rwc_year_data

    year_options = [str(y) for y in AVAILABLE_RWC_YEARS]
    year_idx = _choose_index("Pick a Rugby World Cup year", year_options)
    year = AVAILABLE_RWC_YEARS[year_idx]

    print(f"\nLoading the {year} Rugby World Cup's real squads from Wikipedia "
          f"(first time is network-heavy - ~20 teams - cached after)...")
    pools, squads = get_rwc_year_data(year)
    print(f"\n{year} Rugby World Cup - real pool draw:")
    for pool_name, team_names in pools.items():
        print(f"  {pool_name}: {', '.join(team_names)}")

    fresh_each_match = _ask_squad_mode()
    teams: Dict[str, Team] = {}
    squads_for_tournament: Dict[str, List[Player]] = {}
    for team_name, squad in squads.items():
        if fresh_each_match:
            squads_for_tournament[team_name] = squad
        else:
            teams[team_name] = _draft_team_from_fixed_pool(team_name, squad)

    seed_raw = _prompt("Random seed (blank = random)")
    seed = int(seed_raw) if seed_raw.isdigit() else None
    report = Tournament(teams=teams, squads=squads_for_tournament).run_historical_world_cup(year, seed=seed)
    report.print_report()


def _run_historical_six_nations():
    """Replays a historical Six Nations edition (2009-2021) with that
    year's real squads, scraped from that edition's Wikipedia squads page -
    see `historical_six_nations.py`. Same honest ratings convention as the
    historical World Cup mode. Note: the real match-by-match order isn't
    recoverable from the squads page, so this plays a synthetic
    round-robin order, not the exact historical fixture sequence."""
    from .data.sources.historical_six_nations import (
        AVAILABLE_SIX_NATIONS_YEARS,
        get_six_nations_year_data,
    )

    year_options = [str(y) for y in AVAILABLE_SIX_NATIONS_YEARS]
    year_idx = _choose_index("Pick a Six Nations year", year_options)
    year = AVAILABLE_SIX_NATIONS_YEARS[year_idx]

    print(f"\nLoading the {year} Six Nations' real squads from Wikipedia "
          f"(first time is network-heavy - cached after)...")
    squads = get_six_nations_year_data(year)
    print(f"\n{year} Six Nations Championship: {', '.join(squads.keys())}")

    fresh_each_match = _ask_squad_mode()
    teams: Dict[str, Team] = {}
    squads_for_tournament: Dict[str, List[Player]] = {}
    for team_name, squad in squads.items():
        if fresh_each_match:
            squads_for_tournament[team_name] = squad
        else:
            teams[team_name] = _draft_team_from_fixed_pool(team_name, squad)

    seed_raw = _prompt("Random seed (blank = random)")
    seed = int(seed_raw) if seed_raw.isdigit() else None
    report = Tournament(teams=teams, squads=squads_for_tournament).run_historical_six_nations(year, seed=seed)
    report.print_report()


def _run_custom_tournament():
    n_raw = _prompt("How many teams", default="4")
    n = int(n_raw) if n_raw.isdigit() else 4
    fresh_each_match = _ask_squad_mode()
    teams: Dict[str, Team] = {}
    squads: Dict[str, List[Player]] = {}
    for i in range(n):
        if fresh_each_match:
            name = _prompt(f"Team {i + 1} name")
            squads[name] = _pick_team_pool(name)
        else:
            team = _draft_team()
            teams[team.name] = team

    fixture_mode = _ask_fixture_mode()
    if fixture_mode == "random":
        import random
        if fresh_each_match:
            names = list(squads.keys())
            random.shuffle(names)
            squads = {name: squads[name] for name in names}
        else:
            names = list(teams.keys())
            random.shuffle(names)
            teams = {name: teams[name] for name in names}

    fmt_options = ["round_robin", "round_robin_home_away", "pool_knockout"]
    fmt_idx = _choose_index("Pick a format", fmt_options)
    fmt = fmt_options[fmt_idx]
    pool_count = 2
    if fmt == "pool_knockout":
        pc_raw = _prompt("How many pools", default="2")
        pool_count = int(pc_raw) if pc_raw.isdigit() else 2
    seed_raw = _prompt("Random seed (blank = random)")
    seed = int(seed_raw) if seed_raw.isdigit() else None

    report = CustomTournament(teams=teams, format=fmt, squads=squads).run(pool_count=pool_count, seed=seed)
    report.print_report()


def main():
    print("=== What If Rugby Edition - interactive builder ===")
    options = [
        "Single match (friendly / test match)",
        "Real tournament (actual fixture list, e.g. Six Nations)",
        "Custom tournament (round-robin / pool+knockout)",
    ]
    idx = _choose_index("What do you want to simulate?", options)
    if idx == 0:
        _run_single_match()
    elif idx == 1:
        _run_real_tournament()
    else:
        _run_custom_tournament()


if __name__ == "__main__":
    main()
