"""Loads the *actual* fixture list for a named real tournament/season from
rugbydata, so a "what if" replay follows who-played-whom in reality instead
of a synthetic round-robin.

Data-quality note (checked directly against the dataset): the `dates/*`
index tags most 2026 Six Nations matches with the generic "International
Test Match" competition_id, or none at all - only 2 of ~18 rows actually
carry the dedicated Six Nations id. So instead of trusting `competition_id`
alone, each named tournament below is defined by its **team set** + a
**month window**, and fixtures are recovered by matching both; the real
`competition_id`, where present, is kept for the record but isn't the sole
filter. This is a heuristic, not a guarantee - always worth spot-checking
an unfamiliar season's result count against the expected number of fixtures.

There used to be a `"rugby_world_cup"` entry here too - removed. Its team
set was a superset of `rugby_championship`'s 4 teams and its month window
("09"/"10") overlapped `rugby_championship`'s ("08"/"09"/"10"), so in any
season with no real World Cup (every season this dataset covers except
2023 - the next real edition is 2027, which already has its own dedicated
`Tournament.run_world_cup_2027`), a September/October Rugby Championship
match between Argentina/Australia/New Zealand/South Africa was silently
mislabeled as a "Rugby World Cup" fixture. Even for the real 2023 edition
it only ever recovered 12 of the 20 real participants, and the dedup-by-
team-pair step could drop or conflate an actual World Cup match with an
earlier Rugby Championship match between the same two sides. The real
2023 World Cup (and every other professional-era edition) is properly
covered - full real squads, full real pool draw - by
`Tournament.run_historical_world_cup`, so this broken entry wasn't filling
a real gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set

import pandas as pd

from ..data.sources.nations_championship_2026 import (
    fetch_nations_championship_2026_fixtures,
)
from ..data.sources.pool_builder import ALL_TEAM_IDS
from ..data.sources.rugby_data_client import fetch_season_fixture_index

# rugbydata's own team-name spelling for USA is "Usa" (see pool_builder.py's
# TIER2_TEAM_IDS comment), which differs from the display name "USA" every
# other part of this project (NATION_DISPLAY/NATION_TO_CODE, the rankings
# seed, squad_for_team's nation lookup) actually uses. Every other dataset
# team name this module touches already matches its display name 1:1, so
# this is a one-entry, documented fix-up rather than a general renaming
# table - built from ALL_TEAM_IDS so it stays correct if pool_builder's own
# mapping ever changes.
_DATASET_NAME_TO_DISPLAY = {
    dataset_name: nation
    for _code, (_team_id, dataset_name, nation) in ALL_TEAM_IDS.items()
    if dataset_name != nation
}


def _canonical_name(dataset_name: str) -> str:
    return _DATASET_NAME_TO_DISPLAY.get(dataset_name, dataset_name)


@dataclass
class RealFixture:
    home: str
    away: str
    date: str  # YYYYMMDD
    match_id: str
    competition_id: Optional[str]


@dataclass
class TournamentTemplate:
    name: str
    teams: Set[str]  # dataset team display names, e.g. {"England", "France", ...}
    months: Set[str]  # two-digit months this tournament is played in, e.g. {"01","02","03"}


TOURNAMENTS = {
    "six_nations": TournamentTemplate(
        name="Six Nations",
        teams={"England", "France", "Ireland", "Scotland", "Wales", "Italy"},
        months={"01", "02", "03"},
    ),
    "rugby_championship": TournamentTemplate(
        name="The Rugby Championship",
        teams={"New Zealand", "Australia", "South Africa", "Argentina"},
        months={"08", "09", "10"},
    ),
    "autumn_nations_series": TournamentTemplate(
        name="Autumn Nations Series",
        teams={
            "England", "France", "Ireland", "Scotland", "Wales", "Italy",
            "New Zealand", "Australia", "South Africa", "Argentina",
            "Japan", "Fiji",
        },
        months={"11"},
    ),
    # New in 2026: the "Nations Championship" is a brand-new real competition
    # that replaces the old, loosely-organized cross-hemisphere "Autumn
    # Nations Series" concept for these same 12 unions from 2026 onward. It
    # is NOT just a rename - it's a proper league with a cross-hemisphere
    # league stage played across TWO windows (3 rounds in July 2026, 3 more
    # in November 2026, every match North union vs. South union) plus a
    # Nov 27-29 2026 finals weekend in London where each side plays the
    # equivalent-ranked team from the other hemisphere (1st vs 1st is the
    # grand final). Hence the two-month, non-contiguous window below -
    # `load_real_fixtures`'s month filter is a plain `.isin()` set
    # membership check (confirmed by reading it), so a non-contiguous
    # `{"07", "11"}` is handled correctly, no "window" semantics to worry
    # about despite the module-level docstring's "month window" phrasing.
    # As of this writing (2026-11-16) the dataset has NO fixture rows for
    # this competition at all - not even the July round. `load_real_fixtures`
    # now falls back to a hand-verified Wikipedia fixture list for this one
    # tournament/season (see `_load_nations_championship_2026_from_wikipedia`
    # and `nations_championship_2026.py`) instead of returning `[]`; that
    # fallback is a narrow, documented patch that should be removed once
    # rugbydata actually picks this competition up - at that point this
    # branch will just stop triggering (the rugbydata path takes priority
    # whenever it returns rows), with no further code change needed here.
    # The old `"autumn_nations_series"`
    # entry above is left completely unchanged: this dataset has no
    # pre-2026 Nations Championship data and no post-2026 Autumn Nations
    # Series data either way, so the two entries simply coexist, each
    # naturally returning nothing for years it doesn't apply to.
    "nations_championship": TournamentTemplate(
        name="Nations Championship",
        teams={
            "England", "France", "Ireland", "Scotland", "Wales", "Italy",
            "New Zealand", "Australia", "South Africa", "Argentina",
            "Japan", "Fiji",
        },
        months={"07", "11"},
    ),
    # Tier 2 coverage (added so Tier 2 unions' `TeamRankingTracker` ratings
    # actually move - see `rankings.py`): the Pacific Nations Cup is a real,
    # annual Aug-Sep competition between the Pacific Islands/Japan and North
    # America. Checked live against the dataset (2022-2026): its dedicated
    # competition_id (`d1999468`) is only tagged for 2025 (10 matches), but
    # the same team-set+month heuristic this module already relies on for
    # Six Nations also recovers real 2023 (4 matches) and 2024 (11 matches)
    # fixtures tagged under other ids - current AND historical coverage, as
    # asked. 2022 and 2026 genuinely have zero matching rows in this
    # dataset, so those seasons simply produce no block (same graceful
    # "no data" behavior every other tournament already has) rather than a
    # fabricated fixture list.
    "pacific_nations_cup": TournamentTemplate(
        name="Pacific Nations Cup",
        teams={"Fiji", "Japan", "Samoa", "Tonga", "Canada", "Usa"},
        months={"08", "09"},
    ),
    # Rugby Europe Championship (`05d59524`) - re-investigated, NOW ADDED.
    #
    # The earlier pass only checked the (incomplete) 2026 season, saw 8
    # teams across 12 matches splitting into two disjoint 4-team groups -
    # {Georgia, Netherlands, Spain, Switzerland} vs {Belgium, Germany,
    # Portugal, Romania} - and guessed this id conflated two separate real
    # competitions (Championship + Trophy). A proper check across every
    # COMPLETE season 2021-2026 (connected-component analysis on the real
    # match graph) shows the same two-group split consistently from 2023
    # onward (2021/2022, pre-restructure, come back as one connected
    # group) - group membership even shows real promotion/relegation
    # (Germany top-group 2023/2024, Switzerland top-group 2025/2026; Poland
    # bottom-group 2023/2024, Germany bottom-group 2025/2026). A live web
    # search confirms this is the real, current format: ONE competition,
    # the "Rugby Europe Championship", run as two 4-team pools (Pool A/Pool
    # B) with a crossover finals weekend - not two separate competitions.
    # So the fixture data itself is fine; a single `TournamentTemplate`
    # with the full 8-union team set (Belgium, Georgia, Germany,
    # Netherlands, Poland, Portugal, Romania, Russia, Spain, Switzerland -
    # the superset across 2021-2026, since any one season only uses 8 of
    # these) and months {"01","02","03"} recovers it correctly.
    #
    # The real blocker was downstream, in roster-building, not here -
    # NOW FIXED (12f follow-up): Switzerland/Germany/Poland have ZERO
    # usable rugbydata player-level data (`fetch_team_matches` has their
    # match logs, but every match's `players` id list is empty - confirmed
    # live across 2022-2026), but a fresh live re-check (2026-11-16) found
    # all three DO have a standard `==Current squad==`/`==Squad==`
    # `{{nat rs player|...}}` section on Wikipedia after all (a prior pass
    # missed this - see `pool_builder.TIER2_WIKI_ONLY_TEAM_IDS` and
    # `wikipedia_squad.WIKI_UNION_PAGES` for the three new entries, plus
    # the `parse_current_squad` fix needed since two of the three pages use
    # a plain `[[Name]]` wikilink instead of `{{sortname|First|Last}}`, and
    # Germany's section heading is "==Squad==" not "==Current squad=="). So
    # all 8 real unions in this competition now resolve a real, named
    # roster - Georgia/Romania/Spain/Portugal from rugbydata box scores
    # (same as every other union), Netherlands/Belgium/Russia from their
    # existing `build_wikipedia_pool` fallback, Switzerland/Germany/Poland
    # from the same mechanism via their three new page entries. No union
    # in this block needs an invented archetype roster - every one of the
    # 8 unions' squads traces to a real, named, sourced listing.
    "rugby_europe_championship": TournamentTemplate(
        name="Rugby Europe Championship",
        teams={
            "Belgium", "Georgia", "Germany", "Netherlands", "Poland",
            "Portugal", "Romania", "Russia", "Spain", "Switzerland",
        },
        months={"01", "02", "03"},
    ),
}


def list_tournaments() -> List[str]:
    return list(TOURNAMENTS.keys())


def load_real_fixtures(tournament_key: str, season: str) -> List[RealFixture]:
    if tournament_key not in TOURNAMENTS:
        raise ValueError(f"Unknown tournament: {tournament_key}. Options: {list_tournaments()}")

    # One-off real-world calendar exception, NOT a permanent template change:
    # the real 2026 Rugby Championship did not run as a standalone SANZAAR
    # competition - it was squeezed off the calendar by the All Blacks'
    # Aug-Oct 2026 tour of South Africa, and its 4 unions instead only
    # played cross-hemisphere matches as part of the brand-new Nations
    # Championship (see `nations_championship_2026.py` / the
    # `"nations_championship"` template above). Confirmed live
    # (2026-11-16): without this guard, the team-set+month heuristic below
    # mislabels 3 real 2026 fixtures as "The Rugby Championship 2026" -
    # Argentina v South Africa (8 Aug), South Africa v New Zealand (22 Aug),
    # Argentina v Australia (29 Aug) - which are actually bilateral
    # tour/Test matches tied to that same All Blacks-South Africa tour
    # window, not standalone Rugby Championship rounds. The Rugby
    # Championship is expected to resume normally from 2027 onward, and
    # every other season this dataset covers (2018-2025) is unaffected by
    # this guard.
    if tournament_key == "rugby_championship" and season == "2026":
        return []
    template = TOURNAMENTS[tournament_key]

    index = fetch_season_fixture_index(season)
    if index is None or index.empty:
        # Narrow, documented fallback (NOT a general mechanism): the
        # rugbydata-backed index has no coverage at all for the 2026
        # Nations Championship (its 2026 data stops well before this
        # competition's July window even starts - see
        # `nations_championship_2026.py`'s module docstring for the full
        # story and the live-Wikipedia verification date). Scoped to
        # exactly this one tournament/season; every other tournament/
        # season still returns `[]` here exactly as before, and this patch
        # should be removed once rugbydata actually picks the data up.
        if tournament_key == "nations_championship" and season == "2026":
            return _load_nations_championship_2026_from_wikipedia()
        return []

    month = index["game_date"].astype(str).str.slice(4, 6)
    mask = (
        index["home_team"].isin(template.teams)
        & index["away_team"].isin(template.teams)
        & month.isin(template.months)
    )
    candidates = index[mask].copy()
    if candidates.empty:
        if tournament_key == "nations_championship" and season == "2026":
            return _load_nations_championship_2026_from_wikipedia()
        return []

    candidates["pair_key"] = candidates.apply(
        lambda r: tuple(sorted([r["home_team"], r["away_team"]])), axis=1
    )
    # Prefer rows that carry a real competition_id over untagged duplicates
    # of the same match, then keep the earliest-dated row per pair.
    candidates["has_competition"] = candidates["competition_id"].notna()
    candidates = candidates.sort_values(
        by=["pair_key", "has_competition", "game_date"],
        ascending=[True, False, True],
    )
    deduped = candidates.drop_duplicates(subset="pair_key", keep="first")
    deduped = deduped.sort_values("game_date")

    return [
        RealFixture(
            home=_canonical_name(row["home_team"]),
            away=_canonical_name(row["away_team"]),
            date=str(row["game_date"]),
            match_id=row["match_id"],
            competition_id=row["competition_id"] if row["competition_id"] == row["competition_id"] else None,
        )
        for _, row in deduped.iterrows()
    ]


def _load_nations_championship_2026_from_wikipedia() -> List[RealFixture]:
    """Narrow, documented fallback used only by `load_real_fixtures` for
    `("nations_championship", "2026")` when rugbydata has no rows for it -
    see the call site's comment and `nations_championship_2026.py`'s module
    docstring for why. `match_id`/`competition_id` aren't coming from
    rugbydata's own id scheme here, so they're synthetic-but-stable,
    clearly tagged as Wikipedia-sourced."""
    fixtures = fetch_nations_championship_2026_fixtures()
    return [
        RealFixture(
            home=fx.home,
            away=fx.away,
            date=fx.date,
            match_id=f"nc2026-r{fx.round_no}-{fx.home}-{fx.away}",
            competition_id="nations_championship_2026_wikipedia",
        )
        for fx in fixtures
    ]
