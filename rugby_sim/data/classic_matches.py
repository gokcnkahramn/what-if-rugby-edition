""""Classic Matches" catalog - Tier A (25 real, sourced, historic/iconic/
surprising matches), per the roadmap's "Classic Matches mode" plan.

Same convention as `legends.py`/`rankings.py`'s `WR_RANKING_SEED`: a
curated, real, committed-to-the-repo catalog, not fetched/cached data.

Every `blurb`/`real_score`/date/story detail below is a real, sourced fact
(Rugby World Cup finals/classics researched via Wikipedia; Six Nations and
Rugby Championship 2018-2026 researched via live web search in the session
that built this file) - nothing here is invented. `real_score` is flavor
text only and is never fed into the engine. The two team pools for each
match are resolved from already-existing real data (see
`resolve_pools()` below) - drafting from that real pool is always free
("what if" - never locked to the real historical XV).

`objectives` thresholds (the numeric bars in `win_margin_at_least`,
`total_points_at_least`, etc.) are OUR OWN game-design choice layered on
top of the real facts, deliberately set at or beyond what actually
happened that day - they are not a claim about what really happened.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..engine.match_engine import MatchResult

# `Objective`/`ClassicMatch` and the generic objective-type vocabulary
# (`win`, `win_margin_at_least`, etc.) live in `classic_match_objectives`,
# NOT here, specifically so the Tier-B modules below (which also need
# them) don't have to import this module to get them - this module
# imports the Tier-B modules at module level (to merge their match lists
# into `CLASSIC_MATCHES`), so a Tier-B module importing this model back
# from here would be a genuine import cycle. Re-exported here unchanged
# for backward compatibility with any existing `from .classic_matches
# import ...` of these names.
from .classic_match_objectives import (  # noqa: F401
    ClassicMatch,
    Objective,
    no_cards,
    no_injuries,
    player_points_at_least,
    player_tries_at_least,
    team_drop_goals_at_least,
    team_tries_at_least,
    total_points_at_least,
    win,
    win_margin_at_least,
)

# ---------------------------------------------------------------------------
# The 25-entry Tier-A catalog.
# ---------------------------------------------------------------------------

CLASSIC_MATCHES: List[ClassicMatch] = [
    # -- Rugby World Cup (8) ------------------------------------------------
    ClassicMatch(
        id="rwc_1995_final", tournament="rwc", year=1995,
        display_name="1995 Rugby World Cup Final",
        date="1995-06-24", home_code="RSA", home_name="South Africa",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "The 'Mandela final' at Ellis Park - Nelson Mandela presented the "
            "trophy to Francois Pienaar wearing a Springbok jersey. Decided in "
            "extra time by Joel Stransky's drop goal."
        ),
        real_score="South Africa 15-12 New Zealand (after extra time)",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("South Africa"),
            win_margin_at_least("South Africa", 3),
            no_cards("South Africa"),
            team_drop_goals_at_least("South Africa", 2),  # real: 1 (Stransky's winner)
            total_points_at_least(30),  # real total: 27
        ],
    ),
    ClassicMatch(
        id="rwc_1999_sf", tournament="rwc", year=1999,
        display_name="1999 Rugby World Cup Semi-Final",
        date="1999-06-24", home_code="AUS", home_name="Australia",
        away_code="RSA", away_name="South Africa",
        blurb=(
            "Jannie de Beer's late penalty forced extra time at 18-18; "
            "Stephen Larkham - who kicked only two drop goals in a 102-Test "
            "career - sent Australia to the final with his."
        ),
        real_score="Australia 27-21 South Africa (after extra time)",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("Australia"),
            win_margin_at_least("Australia", 1),
            no_cards("Australia"),
            team_drop_goals_at_least("Australia", 1),
            total_points_at_least(50),  # real total: 48
        ],
    ),
    ClassicMatch(
        id="rwc_2003_final", tournament="rwc", year=2003,
        display_name="2003 Rugby World Cup Final",
        date="2003-11-22", home_code="AUS", home_name="Australia",
        away_code="ENG", away_name="England",
        blurb=(
            "Jonny Wilkinson's drop goal in the final minute of extra time in "
            "Sydney - one of the most iconic moments in World Cup history."
        ),
        real_score="Australia 17-20 England (after extra time)",
        focus_team="away",
        must_have_winner=True,
        objectives=[
            win("England"),
            win_margin_at_least("England", 1),
            no_cards("England"),
            team_drop_goals_at_least("England", 2),  # real: 1 (Wilkinson's winner)
            total_points_at_least(40),  # real total: 37
        ],
    ),
    ClassicMatch(
        id="rwc_2007_qf", tournament="rwc", year=2007,
        display_name="2007 Rugby World Cup Quarter-Final",
        date="2007-10-06", home_code="FRA", home_name="France",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "One of the biggest shocks in World Cup history - host nation "
            "France eliminated the tournament favourites in Cardiff."
        ),
        real_score="France 20-18 New Zealand",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("France"),
            win_margin_at_least("France", 1),
            no_cards("France"),
            team_tries_at_least("France", 3),  # real: 2
            total_points_at_least(40),  # real total: 38
        ],
    ),
    ClassicMatch(
        id="rwc_2011_pool", tournament="rwc", year=2011,
        display_name="2011 Rugby World Cup Pool Match",
        date="2011-10-01", home_code="TGA", home_name="Tonga",
        away_code="FRA", away_name="France",
        blurb=(
            "One of the tournament's biggest shocks: Tonga beat top-ranked "
            "France in Wellington, who still scraped through to the "
            "quarter-finals on a losing bonus point from a late try."
        ),
        real_score="Tonga 19-14 France",
        focus_team="home",
        objectives=[
            win("Tonga"),
            win_margin_at_least("Tonga", 1),
            no_cards("Tonga"),
            team_tries_at_least("Tonga", 2),  # real: 2
            total_points_at_least(35),  # real total: 33
        ],
    ),
    ClassicMatch(
        id="rwc_2015_pool", tournament="rwc", year=2015,
        display_name="2015 Rugby World Cup Pool Match (\"The Brighton Miracle\")",
        date="2015-09-19", home_code="JPN", home_name="Japan",
        away_code="RSA", away_name="South Africa",
        blurb=(
            "Widely considered the greatest upset in Rugby World Cup history. "
            "Karne Hesketh's last-minute try won it for Japan in Brighton."
        ),
        real_score="Japan 34-32 South Africa",
        focus_team="home",
        objectives=[
            win("Japan"),
            win_margin_at_least("Japan", 1),
            no_cards("Japan"),
            team_tries_at_least("Japan", 5),  # real: 5
            total_points_at_least(70),  # real total: 66
        ],
    ),
    ClassicMatch(
        id="rwc_2019_pool", tournament="rwc", year=2019,
        display_name="2019 Rugby World Cup Pool Match",
        date="2019-09-28", home_code="JPN", home_name="Japan",
        away_code="IRE", away_name="Ireland",
        blurb=(
            "Host nation Japan, 40/1 underdogs, stunned world no.1-ranked "
            "Ireland in Shizuoka - their second shock win over a tier-one "
            "nation in two World Cups (after 2015's South Africa)."
        ),
        real_score="Japan 19-12 Ireland",
        focus_team="home",
        objectives=[
            win("Japan"),
            win_margin_at_least("Japan", 1),
            no_cards("Japan"),
            team_tries_at_least("Japan", 3),  # real: 2
            total_points_at_least(35),  # real total: 31
        ],
    ),
    ClassicMatch(
        id="rwc_2023_final", tournament="rwc", year=2023,
        display_name="2023 Rugby World Cup Final",
        date="2023-10-28", home_code="RSA", home_name="South Africa",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "The closest Rugby World Cup final ever, in Paris - South "
            "Africa's 4th title."
        ),
        real_score="South Africa 12-11 New Zealand",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("South Africa"),
            win_margin_at_least("South Africa", 1),
            no_cards("South Africa"),
            team_tries_at_least("South Africa", 1),  # real: 1
            total_points_at_least(25),  # real total: 23
        ],
    ),
    # -- Rugby World Cup, additional classics (8) ---------------------------
    # Same low-risk expansion as the 8 above: every one of these reuses an
    # RWC year `historical_rwc.get_rwc_year_data()` already supports, so
    # `resolve_pools()` needs no new code. Team-name spellings below are
    # confirmed against the nations already used for the SAME year
    # elsewhere in this list (e.g. "England"/"New Zealand" for 1995,
    # "France"/"New Zealand" for 1999, "Wales"/"Ireland" for 2011, etc.).
    ClassicMatch(
        id="rwc_1995_sf", tournament="rwc", year=1995,
        display_name="1995 Rugby World Cup Semi-Final",
        date="1995-06-18", home_code="NZL", home_name="New Zealand",
        away_code="ENG", away_name="England",
        blurb=(
            "Jonah Lomu's defining, world-rugby-changing performance at "
            "Newlands, Cape Town - 4 tries, including the iconic run over "
            "Mike Catt. Zinzan Brooke added a long-range drop goal in the "
            "same match."
        ),
        real_score="New Zealand 45-29 England",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("New Zealand"),
            win_margin_at_least("New Zealand", 10),  # real margin: 16
            no_cards("New Zealand"),
            player_tries_at_least("New Zealand", "Left Wing", 5),  # real: 4 (Lomu)
            total_points_at_least(80),  # real total: 74
        ],
    ),
    ClassicMatch(
        id="rwc_1999_sf_fra_nz", tournament="rwc", year=1999,
        display_name="1999 Rugby World Cup Semi-Final (France's Great Escape)",
        date="1999-10-31", home_code="FRA", home_name="France",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "Widely regarded as one of the biggest upsets, and one of the "
            "best games, in World Cup history - France came back from well "
            "behind (reportedly around 24-10 down) to stun the All Blacks "
            "at Twickenham."
        ),
        real_score="France 43-31 New Zealand",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("France"),
            win_margin_at_least("France", 8),  # real margin: 12
            no_cards("France"),
            team_tries_at_least("France", 5),  # real: 4
            total_points_at_least(75),  # real total: 74
        ],
    ),
    ClassicMatch(
        id="rwc_2003_sf", tournament="rwc", year=2003,
        display_name="2003 Rugby World Cup Semi-Final",
        date="2003-11-15", home_code="AUS", home_name="Australia",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "The defending champions upset the All Blacks at Telstra "
            "Stadium, Sydney, to become the first team to reach back-to-back "
            "World Cup finals."
        ),
        real_score="Australia 22-10 New Zealand",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("Australia"),
            win_margin_at_least("Australia", 5),  # real margin: 12
            no_cards("Australia"),
            team_tries_at_least("Australia", 3),
            total_points_at_least(35),  # real total: 32
        ],
    ),
    ClassicMatch(
        id="rwc_2007_sf", tournament="rwc", year=2007,
        display_name="2007 Rugby World Cup Semi-Final",
        date="2007-10-13", home_code="ENG", home_name="England",
        away_code="FRA", away_name="France",
        blurb=(
            "A tight, drama-filled semi-final in Paris - Jonny Wilkinson's "
            "late penalty and drop goal sent defending champions England "
            "through to the final."
        ),
        real_score="England 14-9 France",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("England"),
            win_margin_at_least("England", 1),
            no_cards("England"),
            team_drop_goals_at_least("England", 1),
            total_points_at_least(28),  # real total: 23
        ],
    ),
    ClassicMatch(
        id="rwc_2011_qf", tournament="rwc", year=2011,
        display_name="2011 Rugby World Cup Quarter-Final",
        date="2011-10-08", home_code="WAL", home_name="Wales",
        away_code="IRE", away_name="Ireland",
        blurb=(
            "Ranked among the tournament's best games - Wales took control "
            "late to beat Ireland in Wellington and reach their first "
            "World Cup semi-final since 1987."
        ),
        real_score="Wales 22-10 Ireland",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("Wales"),
            win_margin_at_least("Wales", 5),  # real margin: 12
            no_cards("Wales"),
            team_tries_at_least("Wales", 3),
            total_points_at_least(35),  # real total: 32
        ],
    ),
    ClassicMatch(
        id="rwc_2015_qf", tournament="rwc", year=2015,
        display_name="2015 Rugby World Cup Quarter-Final",
        date="2015-10-17", home_code="RSA", home_name="South Africa",
        away_code="WAL", away_name="Wales",
        blurb=(
            "South Africa's 'great escape' at Twickenham - Fourie du Preez's "
            "75th-minute try snatched a win from Wales, who had led late on."
        ),
        real_score="South Africa 23-19 Wales",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("South Africa"),
            win_margin_at_least("South Africa", 1),
            no_cards("South Africa"),
            team_tries_at_least("South Africa", 2),
            total_points_at_least(45),  # real total: 42
        ],
    ),
    ClassicMatch(
        id="rwc_2019_sf", tournament="rwc", year=2019,
        display_name="2019 Rugby World Cup Semi-Final",
        date="2019-10-26", home_code="ENG", home_name="England",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "A comprehensive England win over the All Blacks in Yokohama, "
            "forcing 16 turnovers - made more dramatic in hindsight by "
            "England's shock final loss to South Africa the following week."
        ),
        real_score="England 19-7 New Zealand",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("England"),
            win_margin_at_least("England", 5),  # real margin: 12
            no_cards("England"),
            team_tries_at_least("England", 3),  # real: 2
            total_points_at_least(30),  # real total: 26
        ],
    ),
    ClassicMatch(
        id="rwc_2023_qf", tournament="rwc", year=2023,
        display_name="2023 Rugby World Cup Quarter-Final",
        date="2023-10-15", home_code="RSA", home_name="South Africa",
        away_code="FRA", away_name="France",
        blurb=(
            "A seven-try thriller at the Stade de France - the defending "
            "champions edged the hosts late to reach the semi-finals, in a "
            "match widely called the best of the tournament's knockout "
            "weekend."
        ),
        real_score="South Africa 29-28 France",
        focus_team="home",
        must_have_winner=True,
        objectives=[
            win("South Africa"),
            win_margin_at_least("South Africa", 1),
            no_cards("South Africa"),
            team_tries_at_least("South Africa", 4),
            total_points_at_least(60),  # real total: 57
        ],
    ),
    ClassicMatch(
        id="rwc_2007_pool_arg_fra", tournament="rwc", year=2007,
        display_name="2007 Rugby World Cup Pool Match (Opening Shock)",
        date="2007-09-07", home_code="ARG", home_name="Argentina",
        away_code="FRA", away_name="France",
        blurb=(
            "Argentina beat host nation France in the tournament's opening "
            "match at the Stade de France - only the second time a World "
            "Cup host had lost its opener (after England in 1991)."
        ),
        real_score="Argentina 17-12 France",
        focus_team="home",
        objectives=[
            win("Argentina"),
            win_margin_at_least("Argentina", 1),
            no_cards("Argentina"),
            team_tries_at_least("Argentina", 2),  # real: 1 (Corleto)
            total_points_at_least(32),  # real total: 29
        ],
    ),
    ClassicMatch(
        id="rwc_2007_pool_fij_wal", tournament="rwc", year=2007,
        display_name="2007 Rugby World Cup Pool Match (Nantes Thriller)",
        date="2007-09-29", home_code="FIJ", home_name="Fiji",
        away_code="WAL", away_name="Wales",
        blurb=(
            "One of the tournament's biggest pool-stage upsets - Fiji blew a "
            "25-3 lead but still held on to eliminate Wales at the Stade de "
            "la Beaujoire, Nantes, reaching the quarter-finals for the first "
            "time in 20 years."
        ),
        real_score="Fiji 38-34 Wales",
        focus_team="home",
        objectives=[
            win("Fiji"),
            win_margin_at_least("Fiji", 1),
            no_cards("Fiji"),
            team_tries_at_least("Fiji", 5),  # real: 5
            total_points_at_least(75),  # real total: 72
        ],
    ),
    ClassicMatch(
        id="rwc_2011_pool_ire_aus", tournament="rwc", year=2011,
        display_name="2011 Rugby World Cup Pool Match",
        date="2011-09-17", home_code="IRE", home_name="Ireland",
        away_code="AUS", away_name="Australia",
        blurb=(
            "Ireland's win over Australia at Eden Park was the tournament's "
            "first big shock, defying the form book and costing Australia "
            "top spot in their pool."
        ),
        real_score="Ireland 15-6 Australia",
        focus_team="home",
        objectives=[
            win("Ireland"),
            win_margin_at_least("Ireland", 1),
            no_cards("Ireland"),
            team_tries_at_least("Ireland", 1),
            total_points_at_least(25),  # real total: 21
        ],
    ),
    ClassicMatch(
        id="rwc_2023_pool_fij_aus", tournament="rwc", year=2023,
        display_name="2023 Rugby World Cup Pool Match",
        date="2023-09-17", home_code="FIJ", home_name="Fiji",
        away_code="AUS", away_name="Australia",
        blurb=(
            "Fiji's first win over Australia since 1954, in Saint-Etienne - "
            "the Wallabies' first-ever World Cup pool-stage loss to Fiji, "
            "and a result that helped set up Fiji's own historic quarter-"
            "final run."
        ),
        real_score="Fiji 22-15 Australia",
        focus_team="home",
        objectives=[
            win("Fiji"),
            win_margin_at_least("Fiji", 1),
            no_cards("Fiji"),
            team_tries_at_least("Fiji", 3),  # real: 2
            total_points_at_least(40),  # real total: 37
        ],
    ),
    # -- Six Nations 2018-2026 (9) ------------------------------------------
    ClassicMatch(
        id="six_nations_2018", tournament="six_nations", year=2018,
        display_name="2018 Six Nations, Final Round",
        date="2018-03-17", home_code="ENG", home_name="England",
        away_code="IRE", away_name="Ireland",
        blurb=(
            "Ireland's 3rd Grand Slam (after 1948 and 2009), sealed at "
            "Twickenham. Jacob Stockdale finished the campaign with a "
            "Six-Nations-era record 7 tries."
        ),
        real_score="England 15-24 Ireland",
        focus_team="away",
        objectives=[
            win("Ireland"),
            win_margin_at_least("Ireland", 5),
            no_cards("Ireland"),
            player_tries_at_least("Ireland", "Left Wing", 2),
            total_points_at_least(45),  # real total: 39
        ],
    ),
    ClassicMatch(
        id="six_nations_2019", tournament="six_nations", year=2019,
        display_name="2019 Six Nations, Final Round",
        date="2019-03-16", home_code="WAL", home_name="Wales",
        away_code="IRE", away_name="Ireland",
        blurb=(
            "Wales' 4th Six-Nations-era Grand Slam, completed at the "
            "Principality Stadium. Gareth Anscombe kicked 20 points."
        ),
        real_score="Wales 25-7 Ireland",
        focus_team="home",
        objectives=[
            win("Wales"),
            win_margin_at_least("Wales", 10),
            no_cards("Wales"),
            player_points_at_least("Wales", "Fly-half", 22),  # real: 20
            total_points_at_least(35),  # real total: 32
        ],
    ),
    ClassicMatch(
        id="six_nations_2020", tournament="six_nations", year=2020,
        display_name="2020 Six Nations, Pandemic-Delayed Finale",
        date="2020-10-31", home_code="ITA", home_name="Italy",
        away_code="ENG", away_name="England",
        blurb=(
            "Played 273 days after the tournament started, due to the "
            "pandemic. England won the title on points difference with this "
            "rout of Italy in Rome (France beat Ireland the same day)."
        ),
        real_score="Italy 5-34 England",
        focus_team="away",
        objectives=[
            win("England"),
            win_margin_at_least("England", 20),
            no_cards("England"),
            team_tries_at_least("England", 5),  # real: 5
            total_points_at_least(45),  # real total: 39
        ],
    ),
    ClassicMatch(
        id="six_nations_2021", tournament="six_nations", year=2021,
        display_name="2021 Six Nations, Final Round",
        date="2021-03-20", home_code="FRA", home_name="France",
        away_code="WAL", away_name="Wales",
        blurb=(
            "Brice Dulin's match-winning try after the 80th minute denied "
            "Wales a Grand Slam at the Stade de France - Wales still won the "
            "title on points, since Scotland beat France elsewhere that day."
        ),
        real_score="France 32-30 Wales",
        focus_team="home",
        objectives=[
            win("France"),
            win_margin_at_least("France", 1),
            no_cards("France"),
            total_points_at_least(65),  # real total: 62
            team_tries_at_least("France", 4),  # real: 4
        ],
    ),
    ClassicMatch(
        id="six_nations_2022", tournament="six_nations", year=2022,
        display_name="2022 Six Nations, Final Round",
        date="2022-03-19", home_code="FRA", home_name="France",
        away_code="ENG", away_name="England",
        blurb=(
            "France's first Grand Slam since 2010 (10th overall), sealed at "
            "the Stade de France."
        ),
        real_score="France 25-13 England",
        focus_team="home",
        objectives=[
            win("France"),
            win_margin_at_least("France", 10),
            no_cards("France"),
            team_tries_at_least("France", 3),  # real: 3
            total_points_at_least(42),  # real total: 38
        ],
    ),
    ClassicMatch(
        id="six_nations_2023", tournament="six_nations", year=2023,
        display_name="2023 Six Nations, Final Round",
        date="2023-03-18", home_code="IRE", home_name="Ireland",
        away_code="ENG", away_name="England",
        blurb=(
            "Ireland's 4th Grand Slam, and first ever won on home soil in "
            "Dublin. England were reduced to 14 men after Freddie Steward's "
            "red card; Johnny Sexton became Six Nations' all-time leading "
            "points scorer in this match."
        ),
        real_score="Ireland 29-16 England",
        focus_team="home",
        objectives=[
            win("Ireland"),
            win_margin_at_least("Ireland", 10),
            no_cards("Ireland"),
            player_points_at_least("Ireland", "Fly-half", 14),  # Sexton's role
            total_points_at_least(50),  # real total: 45
        ],
    ),
    ClassicMatch(
        id="six_nations_2024", tournament="six_nations", year=2024,
        display_name="2024 Six Nations, Final Round",
        date="2024-03-09", home_code="ENG", home_name="England",
        away_code="IRE", away_name="Ireland",
        blurb=(
            "Marcus Smith's injury-time drop goal - after Elliot Daly missed "
            "a long penalty - crushed Ireland's Grand Slam bid at Twickenham."
        ),
        real_score="England 23-22 Ireland",
        focus_team="home",
        objectives=[
            win("England"),
            win_margin_at_least("England", 1),
            no_cards("England"),
            team_drop_goals_at_least("England", 1),
            total_points_at_least(48),  # real total: 45
        ],
    ),
    ClassicMatch(
        id="six_nations_2025", tournament="six_nations", year=2025,
        display_name="2025 Six Nations, Final Round",
        date="2025-03-15", home_code="FRA", home_name="France",
        away_code="SCO", away_name="Scotland",
        blurb=(
            "Louis Bielle-Biarrey scored his then-record-breaking 8th try of "
            "the Championship (passing Jacob Stockdale's 7) as France won "
            "their first title since 2022."
        ),
        real_score="France 35-16 Scotland",
        focus_team="home",
        objectives=[
            win("France"),
            win_margin_at_least("France", 15),
            no_cards("France"),
            player_tries_at_least("France", "Left Wing", 2),
            total_points_at_least(55),  # real total: 51
        ],
    ),
    ClassicMatch(
        id="six_nations_2026", tournament="six_nations", year=2026,
        display_name="2026 Six Nations, Final Round",
        date="2026-03-14", home_code="FRA", home_name="France",
        away_code="ENG", away_name="England",
        blurb=(
            "A 13-try thriller at the Stade de France; Thomas Ramos kicked "
            "the title-winning penalty after the final hooter. Louis "
            "Bielle-Biarrey scored 4 tries in this match alone, finishing the "
            "championship with 9 (beating his own 2025 record of 8) - his "
            "10th consecutive Six Nations match scoring."
        ),
        real_score="France 48-46 England",
        focus_team="home",
        objectives=[
            win("France"),
            win_margin_at_least("France", 1),
            no_cards("France"),
            total_points_at_least(95),  # real total: 94
            player_tries_at_least("France", "Left Wing", 5),  # real: 4 (Bielle-Biarrey)
        ],
    ),
    # -- Six Nations, additional classics (6) --------------------------------
    # Same low-risk expansion as the RWC additions above - every one of
    # these is 2018+, so `resolve_pools()`'s generic
    # `pool_builder.build_union_pool(code, season=str(year))` branch covers
    # it directly, no new code needed. Team-name spellings confirmed
    # against `pool_builder.NATION_DISPLAY`/the spellings already used
    # elsewhere in this file for the same nations.
    ClassicMatch(
        id="six_nations_2018_calcutta", tournament="six_nations", year=2018,
        display_name="2018 Six Nations, Calcutta Cup",
        date="2018-02-24", home_code="SCO", home_name="Scotland",
        away_code="ENG", away_name="England",
        blurb=(
            "Scotland ended a 10-year wait to beat England, winning the "
            "Calcutta Cup at Murrayfield for the first time since 2008. "
            "Finn Russell was the catalyst, including a famous no-look pass "
            "that set up a try."
        ),
        real_score="Scotland 25-13 England",
        focus_team="home",
        objectives=[
            win("Scotland"),
            win_margin_at_least("Scotland", 15),  # real margin: 12
            no_cards("Scotland"),
            team_tries_at_least("Scotland", 3),  # real: 2
            total_points_at_least(45),  # real total: 38
        ],
    ),
    ClassicMatch(
        id="six_nations_2019_calcutta", tournament="six_nations", year=2019,
        display_name="2019 Six Nations, Calcutta Cup",
        date="2019-03-16", home_code="ENG", home_name="England",
        away_code="SCO", away_name="Scotland",
        blurb=(
            "One of the greatest comebacks in Six Nations history: Scotland "
            "trailed 31-0 early at Twickenham and fought all the way back, "
            "only for George Ford's last-minute try and conversion to deny "
            "them the outright win and force a 38-38 draw. NOTE on "
            "objectives: the real result was a draw, so (deliberately "
            "harder than reality, same convention as every other entry's "
            "thresholds) the base `win` objective here asks the player to "
            "go one better than history and win outright for Scotland, "
            "rather than just draw."
        ),
        real_score="England 38-38 Scotland",
        focus_team="away",
        objectives=[
            win("Scotland"),
            win_margin_at_least("Scotland", 1),  # real: a draw, no margin
            no_cards("Scotland"),
            team_tries_at_least("Scotland", 5),  # real: 4
            total_points_at_least(80),  # real total: 76
        ],
    ),
    ClassicMatch(
        id="six_nations_2022_italy", tournament="six_nations", year=2022,
        display_name="2022 Six Nations, Cardiff Shock",
        date="2022-03-19", home_code="WAL", home_name="Wales",
        away_code="ITA", away_name="Italy",
        blurb=(
            "Edoardo Padovani's last-minute try, set up by an Ange Capuozzo "
            "break, gave Italy their first Six Nations win since 2015 - "
            "against Wales in Cardiff."
        ),
        real_score="Wales 21-22 Italy",
        focus_team="away",
        objectives=[
            win("Italy"),
            win_margin_at_least("Italy", 3),  # real margin: 1
            no_cards("Italy"),
            team_tries_at_least("Italy", 3),  # real: 2
            total_points_at_least(48),  # real total: 43
        ],
    ),
    ClassicMatch(
        id="six_nations_2024_italy", tournament="six_nations", year=2024,
        display_name="2024 Six Nations, Rome",
        date="2024-03-09", home_code="ITA", home_name="Italy",
        away_code="SCO", away_name="Scotland",
        blurb=(
            "Italy's first Six Nations win in two years, at the Stadio "
            "Olimpico - Louis Lynagh scored a try on his Italy debut."
        ),
        real_score="Italy 31-29 Scotland",
        focus_team="home",
        objectives=[
            win("Italy"),
            win_margin_at_least("Italy", 5),  # real margin: 2
            no_cards("Italy"),
            team_tries_at_least("Italy", 4),  # real: 4
            total_points_at_least(65),  # real total: 60
        ],
    ),
    ClassicMatch(
        id="six_nations_2025_twickenham", tournament="six_nations", year=2025,
        display_name="2025 Six Nations, Twickenham Thriller",
        date="2025-02-08", home_code="ENG", home_name="England",
        away_code="FRA", away_name="France",
        blurb=(
            "England trailed 25-19 inside the final six minutes before "
            "Elliot Daly's late try and Fin Smith's conversion - on Smith's "
            "first Test start at fly-half - won it, denying France's Grand "
            "Slam bid."
        ),
        real_score="England 26-25 France",
        focus_team="home",
        objectives=[
            win("England"),
            win_margin_at_least("England", 3),  # real margin: 1
            no_cards("England"),
            team_tries_at_least("England", 4),  # real: 3
            total_points_at_least(55),  # real total: 51
        ],
    ),
    ClassicMatch(
        id="six_nations_2026_cardiff", tournament="six_nations", year=2026,
        display_name="2026 Six Nations, Cardiff Escape",
        date="2026-02-21", home_code="WAL", home_name="Wales",
        away_code="SCO", away_name="Scotland",
        blurb=(
            "Scotland trailed 23-12 with 22 minutes left in Cardiff before "
            "scoring 14 unanswered points - George Turner's 74th-minute try "
            "and Finn Russell's conversion completing the comeback and "
            "denying Wales a first Six Nations win since 2023."
        ),
        real_score="Wales 23-26 Scotland",
        focus_team="away",
        objectives=[
            win("Scotland"),
            win_margin_at_least("Scotland", 5),  # real margin: 3
            no_cards("Scotland"),
            team_tries_at_least("Scotland", 5),  # real: 4
            total_points_at_least(55),  # real total: 49
        ],
    ),
    # -- Rugby Championship 2018-2025 (8) ------------------------------------
    ClassicMatch(
        id="rugby_championship_2018", tournament="rugby_championship", year=2018,
        display_name="2018 Rugby Championship, Mendoza",
        date="2018-08-25", home_code="ARG", home_name="Argentina",
        away_code="RSA", away_name="South Africa",
        blurb=(
            "Ended an 11-match, 3-year Pumas losing streak in the "
            "competition. Nicolas Sanchez scored 17 points."
        ),
        real_score="Argentina 32-19 South Africa",
        focus_team="home",
        objectives=[
            win("Argentina"),
            win_margin_at_least("Argentina", 10),
            no_cards("Argentina"),
            player_points_at_least("Argentina", "Fly-half", 18),  # real: 17
            total_points_at_least(55),  # real total: 51
        ],
    ),
    ClassicMatch(
        id="rugby_championship_2019", tournament="rugby_championship", year=2019,
        display_name="2019 Rugby Championship, Salta",
        date="2019-08-10", home_code="RSA", home_name="South Africa",
        away_code="ARG", away_name="Argentina",
        blurb=(
            "Handre Pollard scored 31 points as South Africa won their first "
            "Rugby Championship title since the competition's 2012 "
            "four-team expansion."
        ),
        real_score="South Africa 46-13 Argentina",
        focus_team="home",
        objectives=[
            win("South Africa"),
            win_margin_at_least("South Africa", 25),
            no_cards("South Africa"),
            player_points_at_least("South Africa", "Fly-half", 32),  # real: 31
            total_points_at_least(62),  # real total: 59
        ],
    ),
    ClassicMatch(
        id="rugby_championship_2020", tournament="rugby_championship", year=2020,
        display_name="2020 Tri Nations, Sydney",
        date="2020-11-14", home_code="ARG", home_name="Argentina",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "Argentina's first-ever win over the All Blacks in 100 years of "
            "trying (30 previous losses since 1985), at Bankwest Stadium. "
            "Nicolas Sanchez scored all 25 points."
        ),
        real_score="Argentina 25-15 New Zealand",
        focus_team="home",
        objectives=[
            win("Argentina"),
            win_margin_at_least("Argentina", 5),
            no_cards("Argentina"),
            player_points_at_least("Argentina", "Fly-half", 26),  # real: 25 (Sanchez, all of it)
            total_points_at_least(45),  # real total: 40
        ],
    ),
    ClassicMatch(
        id="rugby_championship_2021", tournament="rugby_championship", year=2021,
        display_name="2021 Rugby Championship, Townsville",
        date="2021-09-25", home_code="NZL", home_name="New Zealand",
        away_code="RSA", away_name="South Africa",
        blurb=(
            "A title decider in Townsville - all four teams still had a "
            "mathematical shot entering the round."
        ),
        real_score="New Zealand 19-17 South Africa",
        focus_team="home",
        objectives=[
            win("New Zealand"),
            win_margin_at_least("New Zealand", 1),
            no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 2),  # real: 2
            total_points_at_least(40),  # real total: 36
        ],
    ),
    ClassicMatch(
        id="rugby_championship_2022", tournament="rugby_championship", year=2022,
        display_name="2022 Rugby Championship, Christchurch",
        date="2022-08-27", home_code="NZL", home_name="New Zealand",
        away_code="ARG", away_name="Argentina",
        blurb=(
            "Argentina's first-ever win over the All Blacks on New Zealand "
            "soil (only their second win over NZ overall). A late try from "
            "Juan Martin Gonzalez sealed it; Emiliano Boffelli kicked 6 "
            "penalties plus a conversion."
        ),
        real_score="New Zealand 18-25 Argentina",
        focus_team="away",
        objectives=[
            win("Argentina"),
            win_margin_at_least("Argentina", 5),
            no_cards("Argentina"),
            player_points_at_least("Argentina", "Fly-half", 20),  # Boffelli's haul was 20
            total_points_at_least(48),  # real total: 43
        ],
    ),
    ClassicMatch(
        id="rugby_championship_2023", tournament="rugby_championship", year=2023,
        display_name="2023 Rugby Championship, Melbourne",
        date="2023-07-29", home_code="AUS", home_name="Australia",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "New Zealand's 4th straight (20th overall) title - a dominant "
            "six-try rout at the MCG."
        ),
        real_score="Australia 7-38 New Zealand",
        focus_team="away",
        objectives=[
            win("New Zealand"),
            win_margin_at_least("New Zealand", 25),
            no_cards("New Zealand"),
            team_tries_at_least("New Zealand", 6),  # real: 6
            total_points_at_least(50),  # real total: 45
        ],
    ),
    ClassicMatch(
        id="rugby_championship_2024", tournament="rugby_championship", year=2024,
        display_name="2024 Rugby Championship, Mbombela",
        date="2024-09-28", home_code="RSA", home_name="South Africa",
        away_code="ARG", away_name="Argentina",
        blurb=(
            "South Africa's first title since 2019 - seven tries, with "
            "Argentina reduced to 13 men after three cards."
        ),
        real_score="South Africa 48-7 Argentina",
        focus_team="home",
        objectives=[
            win("South Africa"),
            win_margin_at_least("South Africa", 30),
            no_cards("South Africa"),
            team_tries_at_least("South Africa", 7),  # real: 7
            total_points_at_least(60),  # real total: 55
        ],
    ),
    ClassicMatch(
        id="rugby_championship_2025", tournament="rugby_championship", year=2025,
        display_name="2025 Rugby Championship, London",
        date="2025-10-04", home_code="RSA", home_name="South Africa",
        away_code="ARG", away_name="Argentina",
        blurb=(
            "A late Pumas try (Rodrigo Isgro) made it close, but South "
            "Africa won their 6th title at Twickenham - the first-ever Rugby "
            "Championship decided on points difference."
        ),
        real_score="South Africa 29-27 Argentina",
        focus_team="home",
        objectives=[
            win("South Africa"),
            win_margin_at_least("South Africa", 1),
            no_cards("South Africa"),
            total_points_at_least(60),  # real total: 56
            team_tries_at_least("South Africa", 3),
        ],
    ),
    # -- Rugby Championship, additional classics (3) -------------------------
    # Same 2018+ low-risk `build_union_pool` path as above.
    ClassicMatch(
        id="rugby_championship_2018_salta", tournament="rugby_championship", year=2018,
        display_name="2018 Rugby Championship, Salta Comeback",
        date="2018-10-06", home_code="ARG", home_name="Argentina",
        away_code="AUS", away_name="Australia",
        blurb=(
            "Argentina led 31-7 in Salta before Australia scored five "
            "unanswered tries in what was called the Wallabies' biggest-"
            "ever comeback win, in the Rugby Championship's final round."
        ),
        real_score="Argentina 34-45 Australia",
        focus_team="away",
        objectives=[
            win("Australia"),
            win_margin_at_least("Australia", 15),  # real margin: 11
            no_cards("Australia"),
            team_tries_at_least("Australia", 7),  # real: 6
            total_points_at_least(85),  # real total: 79
        ],
    ),
    ClassicMatch(
        id="rugby_championship_2025_argentina_nz", tournament="rugby_championship", year=2025,
        display_name="2025 Rugby Championship, Buenos Aires",
        date="2025-08-23", home_code="ARG", home_name="Argentina",
        away_code="NZL", away_name="New Zealand",
        blurb=(
            "Argentina's first-ever win over New Zealand on home soil, after "
            "16 previous attempts - Santiago Carreras kicked 13 points as "
            "Los Pumas held off a late All Blacks rally in Buenos Aires."
        ),
        real_score="Argentina 29-23 New Zealand",
        focus_team="home",
        objectives=[
            win("Argentina"),
            win_margin_at_least("Argentina", 8),  # real margin: 6
            no_cards("Argentina"),
            team_tries_at_least("Argentina", 3),  # real: 2
            total_points_at_least(55),  # real total: 52
        ],
    ),
    ClassicMatch(
        id="rugby_championship_2025_australia_rsa", tournament="rugby_championship", year=2025,
        display_name="2025 Rugby Championship, Ellis Park Shock",
        date="2025-08-16", home_code="RSA", home_name="South Africa",
        away_code="AUS", away_name="Australia",
        blurb=(
            "Australia trailed 22-0 after 29 minutes at Ellis Park but "
            "scored six straight tries to win - their first victory at the "
            "venue since 1963."
        ),
        real_score="South Africa 22-38 Australia",
        focus_team="away",
        objectives=[
            win("Australia"),
            win_margin_at_least("Australia", 18),  # real margin: 16
            no_cards("Australia"),
            team_tries_at_least("Australia", 7),  # real: 6
            total_points_at_least(65),  # real total: 60
        ],
    ),
]

# -- Tier B: pre-2018 Five/Six Nations and Tri Nations/Rugby Championship --
# matches (45 more, built in a separate session pass) - each one's lineups
# come from that SPECIFIC match's own Wikipedia coverage (no generic
# rugbydata/historical pipeline exists for these pre-2018, non-World-Cup
# years), so each tier-B module owns its own `resolve_pools` - see the
# dispatch in this file's own `resolve_pools()` below. Kept in separate
# modules (not merged into the literal list above) so each tournament's
# ~22-23 entries stay independently reviewable/maintainable.
from .classic_matches_tier_b_six_nations import TIER_B_SIX_NATIONS_MATCHES
from .classic_matches_tier_b_rugby_championship import TIER_B_RUGBY_CHAMPIONSHIP_MATCHES

CLASSIC_MATCHES += TIER_B_SIX_NATIONS_MATCHES + TIER_B_RUGBY_CHAMPIONSHIP_MATCHES


def group_by_tournament() -> Dict[str, List[ClassicMatch]]:
    """`{tournament: [ClassicMatch, ...]}`, each group sorted oldest-to-newest
    by year (ties broken by id for a stable order) - exactly what the
    frontend's collapsible-per-tournament list needs."""
    groups: Dict[str, List[ClassicMatch]] = {}
    for match in CLASSIC_MATCHES:
        groups.setdefault(match.tournament, []).append(match)
    for matches in groups.values():
        matches.sort(key=lambda m: (m.year, m.id))
    return groups


def get_classic_match(match_id: str) -> ClassicMatch | None:
    for match in CLASSIC_MATCHES:
        if match.id == match_id:
            return match
    return None


def resolve_pools(match: ClassicMatch) -> Tuple[list, list]:
    """Returns `(home_pool, away_pool)` - the two real player pools a
    classic match's teams are drafted from, per the plan's "Team-pool
    resolution" rule. RWC matches use `historical_rwc.get_rwc_year_data`'s
    real Wikipedia-sourced squads; Six Nations/Rugby Championship matches
    (2018+) build directly from rugbydata via
    `pool_builder.build_union_pool`, bypassing `real_fixtures.py` entirely
    (confirmed safe for an arbitrary one-off match, not just a whole-
    tournament replay). Tier-B matches (pre-2018, no generic pipeline -
    see the module docstring note above `CLASSIC_MATCHES +=`) dispatch to
    their own module's `resolve_pools`, keyed by id prefix."""
    if match.id in {m.id for m in TIER_B_SIX_NATIONS_MATCHES}:
        from .classic_matches_tier_b_six_nations import resolve_pools as _resolve_six_nations_tb
        return _resolve_six_nations_tb(match)

    if match.id in {m.id for m in TIER_B_RUGBY_CHAMPIONSHIP_MATCHES}:
        from .classic_matches_tier_b_rugby_championship import resolve_pools as _resolve_rugby_championship_tb
        return _resolve_rugby_championship_tb(match)

    if match.tournament == "rwc":
        from .sources.historical_rwc import get_rwc_year_data
        _pools, squads = get_rwc_year_data(match.year)
        return squads[match.home_name], squads[match.away_name]

    from .sources.pool_builder import build_union_pool
    home_pool = build_union_pool(match.home_code, season=str(match.year))
    away_pool = build_union_pool(match.away_code, season=str(match.year))
    return home_pool, away_pool
