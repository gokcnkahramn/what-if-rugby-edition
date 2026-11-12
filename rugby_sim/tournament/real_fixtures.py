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

from ..data.sources.rugby_data_client import fetch_season_fixture_index


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
}


def list_tournaments() -> List[str]:
    return list(TOURNAMENTS.keys())


def load_real_fixtures(tournament_key: str, season: str) -> List[RealFixture]:
    if tournament_key not in TOURNAMENTS:
        raise ValueError(f"Unknown tournament: {tournament_key}. Options: {list_tournaments()}")
    template = TOURNAMENTS[tournament_key]

    index = fetch_season_fixture_index(season)
    if index is None or index.empty:
        return []

    month = index["game_date"].astype(str).str.slice(4, 6)
    mask = (
        index["home_team"].isin(template.teams)
        & index["away_team"].isin(template.teams)
        & month.isin(template.months)
    )
    candidates = index[mask].copy()
    if candidates.empty:
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
            home=row["home_team"],
            away=row["away_team"],
            date=str(row["game_date"]),
            match_id=row["match_id"],
            competition_id=row["competition_id"] if row["competition_id"] == row["competition_id"] else None,
        )
        for _, row in deduped.iterrows()
    ]
