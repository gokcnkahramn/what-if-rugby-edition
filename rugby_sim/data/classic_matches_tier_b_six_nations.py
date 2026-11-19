""""Classic Matches" catalog - Tier B, Six Nations/Five Nations half (one real,
notable match from every Five Nations (1995-1999) / Six Nations (2000-2017)
edition - 23 years total), per the roadmap's "Classic Matches mode" plan,
Tier-B extension.

DELIBERATELY SEPARATE from `classic_matches.py` (which still owns `CLASSIC_MATCHES`,
the Tier-A 25-entry catalog, and the generic `Objective`/checker vocabulary) -
this module only IMPORS that vocabulary, it never redefines or edits it. A
parallel effort is building the other Tier-B tournament's matches in its own
separate file; the two get merged into the main catalog by hand later.

Why these 23 matches needed their OWN sourcing pipeline (see the module
docstring in `rugby_sim/data/sources/historical_rwc.py` for the parallel
RWC-years story): `rugbydata` (this project's primary stat source) only
covers 2018+, and Five/Six Nations editions outside Rugby World Cup years
have no dedicated "historical squad" Wikipedia page in the
`{{nat rs player}}` template `historical_rwc.py` depends on. What each
`<year> Six/Five Nations Championship` Wikipedia page DOES have, for every
single match played from 2000 onward, is a `{{rugbybox|...}}`-templated
match report immediately followed by a REAL, match-specific two-team
starting-XV-plus-bench lineup table (position code, squad number, player
name - `FB/RW/OC/IC/LW/FH/SH/N8/OF/BF/RL/LL/TP/HK/LP`, a direct 1:1 mapping
onto this project's own `Position` enum). That is a strictly BETTER source
than the Tier-A RWC pipeline's whole-tournament-squad pages (it's the real
starting XV + bench for THAT SPECIFIC MATCH, not just "was in the squad
that year") - confirmed live for all 18 target matches below, 2000-2017
(see `_MATCH_LINEUPS`, each entry fetched from its own year's
"<year> Six Nations Championship" Wikipedia article's own `{{rugbybox}}`
block for that exact date/fixture via `wikipedia_squad.fetch_wikitext`,
parsed straight off that table's own position-code column - nothing
guessed, nothing invented).

The five 1995-1999 (Five Nations, pre-Six-Nations-era) matches are the one
documented exception: those years' Wikipedia tournament pages have match
reports and try/kick scorers by name, but NO per-match lineup table (that
template convention only starts with the 2000 Six Nations page). What DOES
exist for every 1995-1999 edition is a "<year> Five Nations Championship
squads" Wikipedia page - the same kind of real, Wikipedia-sourced,
whole-tournament squad list the Tier-A RWC pipeline already relies on (not
a match-day XV, honestly flagged as such below). That page's template has
NO position code at all (unlike the RWC squads page), so each of those ~18
players per team is tagged with ITS REAL, well-documented position from
the broader rugby historical record (every name involved is a capped
international whose position is public record, e.g. "Gavin Hastings -
fullback", "Jonny Wilkinson - fly-half") - assigned here by hand, not
scraped, and called out plainly in `_LEGACY_SQUADS`'s own comment and in
each resulting `Player.notes`.

Every player name below was fetched and read from a real Wikipedia page in
this session - see `_MATCH_LINEUPS` (2000-2017, from each year's
`{{rugbybox}}` match-specific lineup table) and `_LEGACY_SQUADS` (1995-1999,
from each year's "... squads" page). `real_score`/blurb/date facts are the
pre-researched ground truth this module was commissioned with. `objectives`
thresholds are this project's own game-design choice (same convention as
`classic_matches.py`), not a claim about what really happened.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..models.player import Player
from ..models.position import Position
from .classic_match_objectives import (
    ClassicMatch,
    no_cards,
    player_points_at_least,
    player_tries_at_least,
    team_drop_goals_at_least,
    team_tries_at_least,
    total_points_at_least,
    win,
    win_margin_at_least,
)
from .sources.attribute_mapping import DEFAULT_UNION_STRENGTH, UNION_STRENGTH, scale_to_union_strength
from .sources.wikipedia_squad import _archetype_attributes, _cross_reference_attributes

# ---------------------------------------------------------------------------
# Position-code -> our Position enum. Six/Five Nations match-lineup tables
# use a DIFFERENT (more granular) code set than the `{{nat rs player}}`
# current-squad template `wikipedia_squad.POS_CODE_MAP` handles (that one
# only has one slot each for lock/flanker/centre/wing) - this is a direct,
# unambiguous 1:1 mapping confirmed against every `<year> Six Nations
# Championship` match lineup table fetched for this module.
MATCH_POS_CODE_MAP: Dict[str, Position] = {
    "FB": Position.FULLBACK,
    "RW": Position.RIGHT_WING,
    "OC": Position.OUTSIDE_CENTRE,
    "IC": Position.INSIDE_CENTRE,
    "LW": Position.LEFT_WING,
    "FH": Position.FLY_HALF,
    "SH": Position.SCRUM_HALF,
    "N8": Position.NUMBER_8,
    "OF": Position.OPENSIDE_FLANKER,
    "BF": Position.BLINDSIDE_FLANKER,
    "RL": Position.LOCK_2,
    "LL": Position.LOCK_1,
    "TP": Position.TIGHTHEAD_PROP,
    "HK": Position.HOOKER,
    "LP": Position.LOOSEHEAD_PROP,
    # A handful of bench replacements are listed on these pages with the
    # looser `{{nat rs player}}`-style codes instead (a sub coming on to
    # cover more than one specialist position bucket) - same codes
    # `wikipedia_squad.POS_CODE_MAP` already handles, mapped the same way.
    "PR": Position.LOOSEHEAD_PROP,
    "LK": Position.LOCK_1,
    "FL": Position.BLINDSIDE_FLANKER,
    "CE": Position.INSIDE_CENTRE,
    "WG": Position.LEFT_WING,
    "C": Position.INSIDE_CENTRE,
    "W": Position.LEFT_WING,
}

_NATION_TO_STRENGTH_CODE = {
    "England": "ENG", "France": "FRA", "Ireland": "IRE",
    "Italy": "ITA", "Scotland": "SCO", "Wales": "WAL",
}

_CODE_TO_NATION = {
    "ENG": "England", "FRA": "France", "IRE": "Ireland",
    "ITA": "Italy", "SCO": "Scotland", "WAL": "Wales",
}

# ---------------------------------------------------------------------------
# Real, match-specific starting-XV + bench lineups, 2000-2017 - each entry
# (pos_code, player_name, is_starter) fetched verbatim from that year's
# "<year> Six Nations Championship" Wikipedia page's own `{{rugbybox}}`
# lineup table for the exact fixture named in `TIER_B_SIX_NATIONS_MATCHES`
# below (confirmed e.g. Ronan O'Gara at fly-half for the 2009 Ireland
# lineup, Jonny Wilkinson at fly-half for the 2000/2001/2003/2004 England
# lineups - spot-checked against well-known real facts).
# ---------------------------------------------------------------------------

_MATCH_LINEUPS: Dict[str, dict] = {
    "2000": {"home_code": "SCO", "away_code": "ENG", "home": [["FB", "Chris Paterson", True], ["RW", "Craig Moir", True], ["OC", "Gregor Townsend", True], ["IC", "James McLaren", True], ["LW", "Glenn Metcalfe", True], ["FH", "Duncan Hodge", True], ["SH", "Andy Nicol", True], ["N8", "Martin Leslie", True], ["OF", "Budge Pountney", True], ["BF", "Jason White", True], ["RL", "Richard Metcalfe", True], ["LL", "Scott Murray", True], ["TP", "Mattie Stewart", True], ["HK", "Steve Brotherstone", True], ["LP", "Tom Smith", True], ["HK", "Gavin Scott", False], ["PR", "Gordon McIlwham", False], ["LK", "Stuart Grimes", False], ["FL", "Stuart Reid", False], ["SH", "Bryan Redpath", False], ["CE", "Graham Shiel", False], ["CE", "Alan Bulloch", False]], "away": [["FB", "Matt Perry", True], ["RW", "Austin Healey", True], ["OC", "Mike Tindall", True], ["IC", "Mike Catt", True], ["LW", "Ben Cohen", True], ["FH", "Jonny Wilkinson", True], ["SH", "Matt Dawson", True], ["N8", "Lawrence Dallaglio", True], ["OF", "Neil Back", True], ["BF", "Richard Hill", True], ["RL", "Simon Shaw", True], ["LL", "Garath Archer", True], ["TP", "Phil Vickery", True], ["HK", "Phil Greening", True], ["LP", "Jason Leonard", True], ["HK", "Neil McCarthy", False], ["PR", "Trevor Woodman", False], ["N8", "Martin Corry", False], ["FL", "Joe Worsley", False], ["SH", "Andy Gomarsall", False], ["FH", "Alex King", False], ["FB", "Iain Balshaw", False]]},
    "2001": {"home_code": "IRE", "away_code": "ENG", "home": [["FB", "Girvan Dempsey", True], ["RW", "Shane Horgan", True], ["OC", "Brian O'Driscoll", True], ["IC", "Kevin Maggs", True], ["LW", "Denis Hickie", True], ["FH", "David Humphreys", True], ["SH", "Peter Stringer", True], ["N8", "Anthony Foley", True], ["OF", "David Wallace", True], ["BF", "Eric Miller", True], ["RL", "Malcolm O'Kelly", True], ["LL", "Mick Galwey", True], ["TP", "John Hayes", True], ["HK", "Keith Wood", True], ["LP", "Peter Clohessy", True], ["HK", "Frankie Sheahan", False], ["PR", "Emmet Byrne", False], ["LK", "Trevor Brennan", False], ["FL", "Kieron Dawson", False], ["SH", "Guy Easterby", False], ["FH", "Ronan O'Gara", False], ["CE", "Mike Mullins", False]], "away": [["FB", "Iain Balshaw", True], ["RW", "Dan Luger", True], ["OC", "Will Greenwood", True], ["IC", "Mike Catt", True], ["LW", "Jason Robinson", True], ["FH", "Jonny Wilkinson", True], ["SH", "Matt Dawson", True], ["N8", "Richard Hill", True], ["OF", "Neil Back", True], ["BF", "Martin Corry", True], ["RL", "Danny Grewcock", True], ["LL", "Simon Shaw", True], ["TP", "Julian White", True], ["HK", "Phil Greening", True], ["LP", "Jason Leonard", True], ["HK", "Dorian West", False], ["PR", "Graham Rowntree", False], ["LK", "Steve Borthwick", False], ["FL", "Lewis Moody", False], ["SH", "Kyran Bracken", False], ["WG", "Austin Healey", False], ["FB", "Matt Perry", False]]},
    "2002": {"home_code": "FRA", "away_code": "IRE", "home": [["FB", "Nicolas Brusque", True], ["RW", "Aurélien Rougerie", True], ["OC", "Tony Marsh", True], ["IC", "Damien Traille", True], ["LW", "David Bory", True], ["FH", "Gérald Merceron", True], ["SH", "Fabien Galthié", True], ["N8", "Imanol Harinordoquy", True], ["OF", "Olivier Magne", True], ["BF", "Serge Betsen", True], ["RL", "Olivier Brouzet", True], ["LL", "Fabien Pelous", True], ["TP", "Pieter de Villiers", True], ["HK", "Raphaël Ibañez", True], ["LP", "Jean-Jacques Crenca", True], ["HK", "Olivier Azam", False], ["PR", "Jean-Baptiste Poux", False], ["LK", "David Auradou", False], ["FL", "Rémy Martin", False], ["SH", "Pierre Mignoni", False], ["FH", "François Gelez", False], ["FB", "Jimmy Marlu", False]], "away": [["FB", "Girvan Dempsey", True], ["RW", "Shane Horgan", True], ["OC", "Brian O'Driscoll", True], ["IC", "Rob Henderson", True], ["LW", "Denis Hickie", True], ["FH", "David Humphreys", True], ["SH", "Peter Stringer", True], ["N8", "Anthony Foley", True], ["OF", "David Wallace", True], ["BF", "Simon Easterby", True], ["RL", "Malcolm O'Kelly", True], ["LL", "Gary Longwell", True], ["TP", "John Hayes", True], ["HK", "Keith Wood", True], ["LP", "Peter Clohessy", True], ["HK", "Shane Byrne", False], ["PR", "Paul Wallace", False], ["LK", "Paul O'Connell", False], ["FL", "Keith Gleeson", False], ["SH", "Guy Easterby", False], ["FH", "Ronan O'Gara", False], ["WG", "John Kelly", False]]},
    "2003": {"home_code": "IRE", "away_code": "ENG", "home": [["FB", "Geordan Murphy", True], ["RW", "Justin Bishop", True], ["OC", "Brian O'Driscoll", True], ["IC", "Kevin Maggs", True], ["LW", "Denis Hickie", True], ["FH", "David Humphreys", True], ["SH", "Peter Stringer", True], ["N8", "Anthony Foley", True], ["OF", "Keith Gleeson", True], ["BF", "Victor Costello", True], ["RL", "Malcolm O'Kelly", True], ["LL", "Gary Longwell", True], ["TP", "John Hayes", True], ["HK", "Shane Byrne", True], ["LP", "Marcus Horan", True], ["HK", "Frankie Sheahan", False], ["PR", "Justin Fitzpatrick", False], ["LK", "Paul O'Connell", False], ["FL", "Alan Quinlan", False], ["SH", "Guy Easterby", False], ["FH", "Ronan O'Gara", False], ["FB", "Girvan Dempsey", False]], "away": [["FB", "Josh Lewsey", True], ["RW", "Jason Robinson", True], ["OC", "Mike Tindall", True], ["IC", "Will Greenwood", True], ["LW", "Ben Cohen", True], ["FH", "Jonny Wilkinson", True], ["SH", "Matt Dawson", True], ["N8", "Lawrence Dallaglio", True], ["OF", "Neil Back", True], ["BF", "Richard Hill", True], ["RL", "Ben Kay", True], ["LL", "Martin Johnson", True], ["TP", "Jason Leonard", True], ["HK", "Steve Thompson", True], ["LP", "Graham Rowntree", True], ["HK", "Dorian West", False], ["PR", "Trevor Woodman", False], ["LK", "Danny Grewcock", False], ["FL", "Joe Worsley", False], ["SH", "Kyran Bracken", False], ["FH", "Paul Grayson", False], ["WG", "Dan Luger", False]]},
    "2004": {"home_code": "FRA", "away_code": "ENG", "home": [["FB", "Nicolas Brusque", True], ["RW", "Pépito Elhorga", True], ["OC", "Yannick Jauzion", True], ["IC", "Damien Traille", True], ["LW", "Christophe Dominici", True], ["FH", "Frédéric Michalak", True], ["SH", "Dimitri Yachvili", True], ["N8", "Imanol Harinordoquy", True], ["OF", "Olivier Magne", True], ["BF", "Serge Betsen", True], ["RL", "Pascal Papé", True], ["LL", "Fabien Pelous", True], ["TP", "Pieter de Villiers", True], ["HK", "William Servat", True], ["LP", "Sylvain Marconnet", True], ["HK", "Yannick Bru", False], ["PR", "Jean-Jacques Crenca", False], ["LK", "David Auradou", False], ["N8", "Thomas Lièvremont", False], ["SH", "Pierre Mignoni", False], ["FH", "Julien Peyrelongue", False], ["FB", "Clément Poitrenaud", False]], "away": [["FB", "Jason Robinson", True], ["RW", "Josh Lewsey", True], ["OC", "Mike Tindall", True], ["IC", "Will Greenwood", True], ["LW", "Ben Cohen", True], ["FH", "Olly Barkley", True], ["SH", "Matt Dawson", True], ["N8", "Lawrence Dallaglio", True], ["OF", "Richard Hill", True], ["BF", "Joe Worsley", True], ["RL", "Ben Kay", True], ["LL", "Danny Grewcock", True], ["TP", "Phil Vickery", True], ["HK", "Steve Thompson", True], ["LP", "Trevor Woodman", True], ["HK", "Mark Regan", False], ["PR", "Julian White", False], ["LK", "Steve Borthwick", False], ["FL", "Chris Jones", False], ["SH", "Andy Gomarsall", False], ["CE", "Mike Catt", False], ["WG", "James Simpson-Daniel", False]]},
    "2005": {"home_code": "WAL", "away_code": "IRE", "home": [["FB", "Kevin Morgan", True], ["RW", "Mark Taylor", True], ["OC", "Tom Shanklin", True], ["IC", "Gavin Henson", True], ["LW", "Shane Williams", True], ["FH", "Stephen Jones", True], ["SH", "Dwayne Peel", True], ["N8", "Michael Owen", True], ["OF", "Martyn Williams", True], ["BF", "Ryan Jones", True], ["RL", "Robert Sidoli", True], ["LL", "Brent Cockbain", True], ["TP", "Adam Jones", True], ["HK", "Mefin Davies", True], ["LP", "Gethin Jenkins", True], ["HK", "Robin McBryde", False], ["PR", "John Yapp", False], ["FL", "Jonathan Thomas", False], ["FL", "Robin Sowden-Taylor", False], ["SH", "Mike Phillips", False], ["FH", "Ceri Sweeney", False], ["WG", "Hal Luscombe", False]], "away": [["FB", "Geordan Murphy", True], ["RW", "Girvan Dempsey", True], ["OC", "Brian O'Driscoll", True], ["IC", "Kevin Maggs", True], ["LW", "Denis Hickie", True], ["FH", "Ronan O'Gara", True], ["SH", "Peter Stringer", True], ["N8", "Anthony Foley", True], ["OF", "Johnny O'Connor", True], ["BF", "Simon Easterby", True], ["RL", "Paul O'Connell", True], ["LL", "Malcolm O'Kelly", True], ["TP", "John Hayes", True], ["HK", "Shane Byrne", True], ["LP", "Reggie Corrigan", True], ["HK", "Frankie Sheahan", False], ["PR", "Marcus Horan", False], ["LK", "Donncha O'Callaghan", False], ["N8", "Eric Miller", False], ["SH", "Guy Easterby", False], ["FH", "David Humphreys", False], ["FB", "Gavin Duffy", False]]},
    "2006": {"home_code": "SCO", "away_code": "FRA", "home": [["FB", "Hugo Southwell", True], ["RW", "Chris Paterson", True], ["OC", "Marcus Di Rollo", True], ["IC", "Andrew Henderson", True], ["LW", "Sean Lamont", True], ["FH", "Dan Parks", True], ["SH", "Mike Blair", True], ["N8", "Simon Taylor", True], ["OF", "Ally Hogg", True], ["BF", "Jason White", True], ["RL", "Scott Murray", True], ["LL", "Alastair Kellock", True], ["TP", "Bruce Douglas", True], ["HK", "Dougie Hall", True], ["LP", "Gavin Kerr", True], ["HK", "Scott Lawson", False], ["PR", "Craig Smith", False], ["LK", "Scott MacLeod", False], ["FL", "Jon Petrie", False], ["SH", "Chris Cusiter", False], ["FH", "Gordon Ross", False], ["WG", "Simon Webster", False]], "away": [["FB", "Nicolas Brusque", True], ["RW", "Cédric Heymans", True], ["OC", "Florian Fritz", True], ["IC", "Ludovic Valbon", True], ["LW", "Christophe Dominici", True], ["FH", "Frédéric Michalak", True], ["SH", "Jean-Baptiste Élissalde", True], ["N8", "Julien Bonnaire", True], ["OF", "Rémy Martin", True], ["BF", "Yannick Nyanga", True], ["RL", "Jérôme Thion", True], ["LL", "Fabien Pelous", True], ["TP", "Pieter de Villiers", True], ["HK", "Dimitri Szarzewski", True], ["LP", "Sylvain Marconnet", True], ["HK", "Sébastien Bruno", False], ["PR", "Olivier Milloud", False], ["LK", "Lionel Nallet", False], ["N8", "Thomas Lièvremont", False], ["SH", "Dimitri Yachvili", False], ["FH", "Benjamin Boyet", False], ["CE", "Guillaume Boussès", False]]},
    "2007": {"home_code": "IRE", "away_code": "FRA", "home": [["FB", "Girvan Dempsey", True], ["RW", "Geordan Murphy", True], ["OC", "Gordon D'Arcy", True], ["IC", "Shane Horgan", True], ["LW", "Denis Hickie", True], ["FH", "Ronan O'Gara", True], ["SH", "Isaac Boss", True], ["N8", "Denis Leamy", True], ["OF", "David Wallace", True], ["BF", "Simon Easterby", True], ["RL", "Paul O'Connell", True], ["LL", "Donncha O'Callaghan", True], ["TP", "John Hayes", True], ["HK", "Rory Best", True], ["LP", "Marcus Horan", True], ["HK", "Jerry Flannery", False], ["PR", "Simon Best", False], ["LK", "Mick O'Driscoll", False], ["FL", "Neil Best", False], ["SH", "Eoin Reddan", False], ["FH", "Paddy Wallace", False], ["WG", "Andrew Trimble", False]], "away": [["FB", "Clément Poitrenaud", True], ["RW", "Vincent Clerc", True], ["OC", "David Marty", True], ["IC", "Yannick Jauzion", True], ["LW", "Christophe Dominici", True], ["FH", "David Skrela", True], ["SH", "Pierre Mignoni", True], ["N8", "Sébastien Chabal", True], ["OF", "Imanol Harinordoquy", True], ["BF", "Serge Betsen", True], ["RL", "Pascal Papé", True], ["LL", "Lionel Nallet", True], ["TP", "Pieter de Villiers", True], ["HK", "Raphaël Ibañez", True], ["LP", "Sylvain Marconnet", True], ["HK", "Yannick Bru", False], ["PR", "Olivier Milloud", False], ["LK", "Jérôme Thion", False], ["FL", "Julien Bonnaire", False], ["SH", "Dimitri Yachvili", False], ["FH", "Lionel Beauxis", False], ["FB", "Cédric Heymans", False]]},
    "2008": {"home_code": "WAL", "away_code": "FRA", "home": [["FB", "Lee Byrne", True], ["RW", "Mark Jones", True], ["OC", "Tom Shanklin", True], ["IC", "Gavin Henson", True], ["LW", "Shane Williams", True], ["FH", "James Hook", True], ["SH", "Mike Phillips", True], ["N8", "Ryan Jones", True], ["OF", "Martyn Williams", True], ["BF", "Jonathan Thomas", True], ["RL", "Alun Wyn Jones", True], ["LL", "Ian Gough", True], ["TP", "Adam Jones", True], ["HK", "Huw Bennett", True], ["LP", "Gethin Jenkins", True], ["HK", "Matthew Rees", False], ["PR", "Duncan Jones", False], ["LK", "Ian Evans", False], ["N8", "Gareth Delve", False], ["SH", "Dwayne Peel", False], ["FH", "Stephen Jones", False], ["CE", "Sonny Parker", False]], "away": [["FB", "Anthony Floch", True], ["RW", "Vincent Clerc", True], ["OC", "Yannick Jauzion", True], ["IC", "Damien Traille", True], ["LW", "Julien Malzieu", True], ["FH", "David Skrela", True], ["SH", "Jean-Baptiste Élissalde", True], ["N8", "Julien Bonnaire", True], ["OF", "Fulgence Ouedraogo", True], ["BF", "Thierry Dusautoir", True], ["RL", "Jérôme Thion", True], ["LL", "Lionel Nallet", True], ["TP", "Nicolas Mas", True], ["HK", "Dimitri Szarzewski", True], ["LP", "Fabien Barcella", True], ["HK", "William Servat", False], ["PR", "Jean-Baptiste Poux", False], ["LK", "Arnaud Méla", False], ["N8", "Elvis Vermeulen", False], ["SH", "Dimitri Yachvili", False], ["FH", "François Trinh-Duc", False], ["FB", "Cédric Heymans", False]]},
    "2009": {"home_code": "WAL", "away_code": "IRE", "home": [["FB", "Lee Byrne", True], ["RW", "Mark Jones", True], ["OC", "Tom Shanklin", True], ["IC", "Gavin Henson", True], ["LW", "Shane Williams", True], ["FH", "Stephen Jones", True], ["SH", "Mike Phillips", True], ["N8", "Ryan Jones", True], ["OF", "Martyn Williams", True], ["BF", "Dafydd Jones", True], ["RL", "Alun Wyn Jones", True], ["LL", "Ian Gough", True], ["TP", "Adam Jones", True], ["HK", "Matthew Rees", True], ["LP", "Gethin Jenkins", True], ["HK", "Huw Bennett", False], ["PR", "John Yapp", False], ["LK", "Luke Charteris", False], ["FL", "Jonathan Thomas", False], ["SH", "Warren Fury", False], ["FH", "James Hook", False], ["CE", "Jamie Roberts", False]], "away": [["FB", "Rob Kearney", True], ["RW", "Tommy Bowe", True], ["OC", "Brian O'Driscoll", True], ["IC", "Gordon D'Arcy", True], ["LW", "Luke Fitzgerald", True], ["FH", "Ronan O'Gara", True], ["SH", "Tomás O'Leary", True], ["N8", "Jamie Heaslip", True], ["OF", "David Wallace", True], ["BF", "Stephen Ferris", True], ["RL", "Paul O'Connell", True], ["LL", "Donncha O'Callaghan", True], ["TP", "John Hayes", True], ["HK", "Jerry Flannery", True], ["LP", "Marcus Horan", True], ["HK", "Rory Best", False], ["PR", "Tom Court", False], ["LK", "Mick O'Driscoll", False], ["FL", "Denis Leamy", False], ["SH", "Peter Stringer", False], ["CE", "Paddy Wallace", False], ["FB", "Geordan Murphy", False]]},
    "2010": {"home_code": "FRA", "away_code": "ENG", "home": [["FB", "Clément Poitrenaud", True], ["RW", "Marc Andreu", True], ["OC", "Mathieu Bastareaud", True], ["IC", "Yannick Jauzion", True], ["LW", "Alexis Palisson", True], ["FH", "François Trinh-Duc", True], ["SH", "Morgan Parra", True], ["N8", "Imanol Harinordoquy", True], ["OF", "Julien Bonnaire", True], ["BF", "Thierry Dusautoir", True], ["RL", "Julien Pierre", True], ["LL", "Lionel Nallet", True], ["TP", "Nicolas Mas", True], ["HK", "William Servat", True], ["LP", "Thomas Domingo", True], ["HK", "Dimitri Szarzewski", False], ["PR", "Jean-Baptiste Poux", False], ["LK", "Sébastien Chabal", False], ["FL", "Alexandre Lapandry", False], ["SH", "Dimitri Yachvili", False], ["CE", "David Marty", False], ["WG", "Julien Malzieu", False]], "away": [["FB", "Ben Foden", True], ["RW", "Mark Cueto", True], ["OC", "Mike Tindall", True], ["IC", "Riki Flutey", True], ["LW", "Chris Ashton", True], ["FH", "Toby Flood", True], ["SH", "Danny Care", True], ["N8", "Nick Easter", True], ["OF", "Lewis Moody", True], ["BF", "Joe Worsley", True], ["RL", "Louis Deacon", True], ["LL", "Simon Shaw", True], ["TP", "Dan Cole", True], ["HK", "Dylan Hartley", True], ["LP", "Tim Payne", True], ["HK", "Steve Thompson", False], ["PR", "David Wilson", False], ["LK", "Tom Palmer", False], ["FL", "James Haskell", False], ["SH", "Ben Youngs", False], ["FH", "Jonny Wilkinson", False], ["CE", "Mathew Tait", False]]},
    "2011": {"home_code": "ITA", "away_code": "FRA", "home": [["FB", "Andrea Masi", True], ["RW", "Tommaso Benvenuti", True], ["OC", "Gonzalo Canale", True], ["IC", "Gonzalo García", True], ["LW", "Mirco Bergamasco", True], ["FH", "Luciano Orquera", True], ["SH", "Fabio Semenzato", True], ["N8", "Sergio Parisse", True], ["OF", "Robert Barbieri", True], ["BF", "Alessandro Zanni", True], ["RL", "Carlo Del Fava", True], ["LL", "Santiago Dellapè", True], ["TP", "Martin Castrogiovanni", True], ["HK", "Carlo Festuccia", True], ["LP", "Andrea Lo Cicero", True], ["HK", "Leonardo Ghiraldini", False], ["PR", "Salvatore Perugini", False], ["LK", "Quintin Geldenhuys", False], ["FL", "Paul Derbyshire", False], ["SH", "Pablo Canavosio", False], ["FH", "Kris Burton", False], ["FB", "Luke McLean", False]], "away": [["FB", "Maxime Médard", True], ["RW", "Yoann Huget", True], ["OC", "Aurélien Rougerie", True], ["IC", "Yannick Jauzion", True], ["LW", "Vincent Clerc", True], ["FH", "François Trinh-Duc", True], ["SH", "Morgan Parra", True], ["N8", "Sébastien Chabal", True], ["OF", "Julien Bonnaire", True], ["BF", "Thierry Dusautoir", True], ["RL", "Lionel Nallet", True], ["LL", "Julien Pierre", True], ["TP", "Nicolas Mas", True], ["HK", "William Servat", True], ["LP", "Sylvain Marconnet", True], ["HK", "Guilhem Guirado", False], ["PR", "Luc Ducalcon", False], ["LK", "Jérôme Thion", False], ["N8", "Imanol Harinordoquy", False], ["SH", "Julien Tomas", False], ["CE", "Damien Traille", False], ["FB", "Clément Poitrenaud", False]]},
    "2012": {"home_code": "WAL", "away_code": "FRA", "home": [["FB", "Leigh Halfpenny", True], ["RW", "Alex Cuthbert", True], ["OC", "Jonathan Davies", True], ["IC", "Jamie Roberts", True], ["LW", "George North", True], ["FH", "Rhys Priestland", True], ["SH", "Mike Phillips", True], ["N8", "Taulupe Faletau", True], ["OF", "Sam Warburton", True], ["BF", "Dan Lydiate", True], ["RL", "Ian Evans", True], ["LL", "Alun Wyn Jones", True], ["TP", "Adam Jones", True], ["HK", "Matthew Rees", True], ["LP", "Gethin Jenkins", True], ["HK", "Ken Owens", False], ["PR", "Paul James", False], ["LK", "Luke Charteris", False], ["FL", "Ryan Jones", False], ["SH", "Lloyd Williams", False], ["FH", "James Hook", False], ["CE", "Scott Williams", False]], "away": [["FB", "Clément Poitrenaud", True], ["RW", "Wesley Fofana", True], ["OC", "Aurélien Rougerie", True], ["IC", "Florian Fritz", True], ["LW", "Alexis Palisson", True], ["FH", "Lionel Beauxis", True], ["SH", "Dimitri Yachvili", True], ["N8", "Imanol Harinordoquy", True], ["OF", "Julien Bonnaire", True], ["BF", "Thierry Dusautoir", True], ["RL", "Yoann Maestri", True], ["LL", "Pascal Papé", True], ["TP", "David Attoub", True], ["HK", "William Servat", True], ["LP", "Jean-Baptiste Poux", True], ["HK", "Dimitri Szarzewski", False], ["PR", "Vincent Debaty", False], ["LK", "Julien Pierre", False], ["N8", "Louis Picamoles", False], ["SH", "Morgan Parra", False], ["FH", "François Trinh-Duc", False], ["WG", "Jean-Marcellin Buttin", False]]},
    "2013": {"home_code": "WAL", "away_code": "ENG", "home": [["FB", "Leigh Halfpenny", True], ["RW", "Alex Cuthbert", True], ["OC", "Jonathan Davies", True], ["IC", "Jamie Roberts", True], ["LW", "George North", True], ["FH", "Dan Biggar", True], ["SH", "Mike Phillips", True], ["N8", "Taulupe Faletau", True], ["OF", "Justin Tipuric", True], ["BF", "Sam Warburton", True], ["RL", "Ian Evans", True], ["LL", "Alun Wyn Jones", True], ["TP", "Adam Jones", True], ["HK", "Richard Hibbard", True], ["LP", "Gethin Jenkins", True], ["HK", "Ken Owens", False], ["PR", "Paul James", False], ["PR", "Scott Andrews", False], ["LK", "Andrew Coombs", False], ["FL", "Aaron Shingler", False], ["SH", "Lloyd Williams", False], ["FH", "James Hook", False], ["CE", "Scott Williams", False]], "away": [["FB", "Alex Goode", True], ["RW", "Chris Ashton", True], ["OC", "Manu Tuilagi", True], ["IC", "Brad Barritt", True], ["LW", "Mike Brown", True], ["FH", "Owen Farrell", True], ["SH", "Ben Youngs", True], ["N8", "Tom Wood", True], ["OF", "Chris Robshaw", True], ["BF", "Tom Croft", True], ["RL", "Geoff Parling", True], ["LL", "Joe Launchbury", True], ["TP", "Dan Cole", True], ["HK", "Tom Youngs", True], ["LP", "Joe Marler", True], ["HK", "Dylan Hartley", False], ["PR", "David Wilson", False], ["PR", "Mako Vunipola", False], ["LK", "Courtney Lawes", False], ["FL", "James Haskell", False], ["SH", "Danny Care", False], ["FH", "Toby Flood", False], ["CE", "Billy Twelvetrees", False]]},
    "2014": {"home_code": "FRA", "away_code": "IRE", "home": [["FB", "Brice Dulin", True], ["RW", "Yoann Huget", True], ["OC", "Mathieu Bastareaud", True], ["IC", "Gaël Fickou", True], ["LW", "Maxime Médard", True], ["FH", "Rémi Talès", True], ["SH", "Maxime Machenaud", True], ["N8", "Damien Chouly", True], ["OF", "Alexandre Lapandry", True], ["BF", "Louis Picamoles", True], ["RL", "Yoann Maestri", True], ["LL", "Pascal Papé", True], ["TP", "Nicolas Mas", True], ["HK", "Dimitri Szarzewski", True], ["LP", "Thomas Domingo", True], ["HK", "Guilhem Guirado", False], ["PR", "Vincent Debaty", False], ["PR", "Rabah Slimani", False], ["LK", "Alexandre Flanquart", False], ["LK", "Sébastien Vahaamahina", False], ["FL", "Wenceslas Lauret", False], ["SH", "Jean-Marc Doussain", False], ["CE", "Maxime Mermoz", False]], "away": [["FB", "Rob Kearney", True], ["RW", "Andrew Trimble", True], ["OC", "Brian O'Driscoll", True], ["IC", "Gordon D'Arcy", True], ["LW", "David Kearney", True], ["FH", "Johnny Sexton", True], ["SH", "Conor Murray", True], ["N8", "Jamie Heaslip", True], ["OF", "Chris Henry", True], ["BF", "Peter O'Mahony", True], ["RL", "Paul O'Connell", True], ["LL", "Devin Toner", True], ["TP", "Mike Ross", True], ["HK", "Rory Best", True], ["LP", "Cian Healy", True], ["HK", "Seán Cronin", False], ["PR", "Jack McGrath", False], ["PR", "Martin Moore", False], ["LK", "Iain Henderson", False], ["FL", "Jordi Murphy", False], ["SH", "Eoin Reddan", False], ["FH", "Ian Madigan", False], ["WG", "Fergus McFadden", False]]},
    "2015": {"home_code": "ENG", "away_code": "FRA", "home": [["FB", "Mike Brown", True], ["RW", "Anthony Watson", True], ["OC", "Jonathan Joseph", True], ["IC", "Luther Burrell", True], ["LW", "Jack Nowell", True], ["FH", "George Ford", True], ["SH", "Ben Youngs", True], ["N8", "Billy Vunipola", True], ["OF", "Chris Robshaw", True], ["BF", "James Haskell", True], ["RL", "Courtney Lawes", True], ["LL", "Geoff Parling", True], ["TP", "Dan Cole", True], ["HK", "Dylan Hartley", True], ["LP", "Joe Marler", True], ["HK", "Tom Youngs", False], ["PR", "Mako Vunipola", False], ["PR", "Kieran Brookes", False], ["N8", "Nick Easter", False], ["FL", "Tom Wood", False], ["SH", "Richard Wigglesworth", False], ["FH", "Danny Cipriani", False], ["CE", "Billy Twelvetrees", False]], "away": [["FB", "Scott Spedding", True], ["RW", "Yoann Huget", True], ["OC", "Gaël Fickou", True], ["IC", "Maxime Mermoz", True], ["LW", "Noa Nakaitaci", True], ["FH", "Jules Plisson", True], ["SH", "Sébastien Tillous-Borde", True], ["N8", "Loann Goujon", True], ["OF", "Bernard Le Roux", True], ["BF", "Thierry Dusautoir", True], ["RL", "Yoann Maestri", True], ["LL", "Alexandre Flanquart", True], ["TP", "Nicolas Mas", True], ["HK", "Guilhem Guirado", True], ["LP", "Vincent Debaty", True], ["HK", "Benjamin Kayser", False], ["PR", "Rabah Slimani", False], ["PR", "Uini Atonio", False], ["LK", "Romain Taofifénua", False], ["N8", "Damien Chouly", False], ["SH", "Rory Kockott", False], ["FH", "Rémi Talès", False], ["CE", "Mathieu Bastareaud", False]]},
    "2016": {"home_code": "FRA", "away_code": "ENG", "home": [["FB", "Scott Spedding", True], ["RW", "Wesley Fofana", True], ["OC", "Gaël Fickou", True], ["IC", "Maxime Mermoz", True], ["LW", "Virimi Vakatawa", True], ["FH", "François Trinh-Duc", True], ["SH", "Maxime Machenaud", True], ["N8", "Loann Goujon", True], ["OF", "Bernard Le Roux", True], ["BF", "Damien Chouly", True], ["RL", "Yoann Maestri", True], ["LL", "Alexandre Flanquart", True], ["TP", "Rabah Slimani", True], ["HK", "Guilhem Guirado", True], ["LP", "Jefferson Poirot", True], ["HK", "Camille Chat", False], ["PR", "Uini Atonio", False], ["PR", "Xavier Chiocci", False], ["LK", "Paul Jedrasiak", False], ["FL", "Wenceslas Lauret", False], ["SH", "Sébastien Bezy", False], ["FH", "Jules Plisson", False], ["WG", "Maxime Médard", False]], "away": [["FB", "Mike Brown", True], ["RW", "Anthony Watson", True], ["OC", "Jonathan Joseph", True], ["IC", "Owen Farrell", True], ["LW", "Jack Nowell", True], ["FH", "George Ford", True], ["SH", "Danny Care", True], ["N8", "Billy Vunipola", True], ["OF", "James Haskell", True], ["BF", "Chris Robshaw", True], ["RL", "George Kruis", True], ["LL", "Maro Itoje", True], ["TP", "Dan Cole", True], ["HK", "Dylan Hartley", True], ["LP", "Mako Vunipola", True], ["HK", "Luke Cowan-Dickie", False], ["PR", "Joe Marler", False], ["PR", "Kieran Brookes", False], ["LK", "Joe Launchbury", False], ["FL", "Jack Clifford", False], ["SH", "Ben Youngs", False], ["CE", "Manu Tuilagi", False], ["CE", "Elliot Daly", False]]},
    "2017": {"home_code": "IRE", "away_code": "ENG", "home": [["FB", "Jared Payne", True], ["RW", "Keith Earls", True], ["OC", "Garry Ringrose", True], ["IC", "Robbie Henshaw", True], ["LW", "Simon Zebo", True], ["FH", "Johnny Sexton", True], ["SH", "Kieran Marmion", True], ["N8", "CJ Stander", True], ["OF", "Seán O'Brien", True], ["BF", "Peter O'Mahony", True], ["RL", "Iain Henderson", True], ["LL", "Donnacha Ryan", True], ["TP", "Tadhg Furlong", True], ["HK", "Rory Best", True], ["LP", "Jack McGrath", True], ["HK", "Niall Scannell", False], ["PR", "Cian Healy", False], ["PR", "John Ryan", False], ["LK", "Devin Toner", False], ["FL", "Dan Leavy", False], ["SH", "Luke McGrath", False], ["FH", "Paddy Jackson", False], ["WG", "Andrew Conway", False]], "away": [["FB", "Mike Brown", True], ["RW", "Anthony Watson", True], ["OC", "Jonathan Joseph", True], ["IC", "Owen Farrell", True], ["LW", "Elliot Daly", True], ["FH", "George Ford", True], ["SH", "Ben Youngs", True], ["N8", "Billy Vunipola", True], ["OF", "James Haskell", True], ["BF", "Maro Itoje", True], ["RL", "Courtney Lawes", True], ["LL", "Joe Launchbury", True], ["TP", "Dan Cole", True], ["HK", "Dylan Hartley", True], ["LP", "Joe Marler", True], ["HK", "Jamie George", False], ["PR", "Mako Vunipola", False], ["PR", "Kyle Sinckler", False], ["FL", "Tom Wood", False], ["N8", "Nathan Hughes", False], ["SH", "Danny Care", False], ["CE", "Ben Te'o", False], ["WG", "Jack Nowell", False]]},
}

# ---------------------------------------------------------------------------
# 1995-1999 (Five Nations, pre-dedicated-lineup-template era): real,
# Wikipedia-sourced ("<year> Five Nations Championship squads") WHOLE-SQUAD
# lists (not a match-day XV - that page format has no per-match lineup, see
# module docstring), each player tagged with their real, well-documented
# position by hand (every name below really did play in that tournament
# for that team, per the fetched squads page - only the position label is
# hand-assigned rather than scraped, since the source page carries no
# position code for this era).
# ---------------------------------------------------------------------------

_LEGACY_SQUADS: Dict[str, Dict[str, List[Tuple[str, str]]]] = {
    "1995": {
        "Scotland": [
            ("LL", "Stewart Campbell"), ("FH", "Craig Chalmers"), ("LL", "Damian Cronin"),
            ("FB", "Gavin Hastings"), ("OC", "Scott Hastings"), ("LP", "Dave Hilton"),
            ("IC", "Ian Jardine"), ("RW", "Craig Joiner"), ("LW", "Kenny Logan"),
            ("BF", "John Manson"), ("HK", "Kenny Milne"), ("OF", "Iain Morrison"),
            ("N8", "Eric Peters"), ("SH", "Bryan Redpath"), ("FH", "Gregor Townsend"),
            ("N8", "Rob Wainwright"), ("RL", "Doddie Weir"), ("TP", "Peter Wright"),
        ],
        "France": [
            ("HK", "Guy Accoceberry"), ("LP", "Louis Armary"), ("RL", "Abdelatif Benazzi"),
            ("BF", "Philippe Benetton"), ("LP", "Laurent Benezech"), ("RW", "Philippe Bernat-Salles"),
            ("LL", "Olivier Brouzet"), ("OF", "Laurent Cabannes"), ("TP", "Christian Califano"),
            ("N8", "Marc Cecillon"), ("IC", "Marc de Rougemont"), ("FH", "Yann Delaigue"),
            ("FH", "Christophe Deylaud"), ("TP", "Philippe Gallart"), ("TP", "Jean-Michel Gonzales"),
            ("FH", "Thierry Lacroix"), ("RL", "Olivier Merle"), ("IC", "Franck Mesnel"),
            ("LW", "Émile Ntamack"), ("LL", "Olivier Roumat"), ("FB", "Jean-Luc Sadourny"),
            ("LW", "Philippe Saint-André"), ("LP", "Laurent Seigne"), ("OC", "Philippe Sella"),
            ("RW", "Sébastien Viars"),
        ],
    },
    "1996": {
        "Scotland": [
            ("LL", "Stewart Campbell"), ("FB", "Michael Dods"), ("OC", "Scott Hastings"),
            ("LP", "Dave Hilton"), ("IC", "Ian Jardine"), ("RW", "Craig Joiner"),
            ("LW", "Kenny Logan"), ("TP", "Kevin McKenzie"), ("N8", "Eric Peters"),
            ("SH", "Bryan Redpath"), ("FB", "Rowen Shepherd"), ("RL", "Ian Smith"),
            ("FH", "Gregor Townsend"), ("N8", "Rob Wainwright"), ("RL", "Doddie Weir"),
            ("TP", "Peter Wright"),
        ],
        "England": [
            ("RL", "Garath Archer"), ("LL", "Martin Bayfield"), ("SH", "Kyran Bracken"),
            ("FB", "Jonathan Callard"), ("IC", "Will Carling"), ("FB", "Mike Catt"),
            ("BF", "Ben Clarke"), ("N8", "Lawrence Dallaglio"), ("HK", "Graham Dawe"),
            ("SH", "Matt Dawson"), ("OC", "Phil de Glanville"), ("FH", "Paul Grayson"),
            ("OC", "Jeremy Guscott"), ("LL", "Martin Johnson"), ("LP", "Jason Leonard"),
            ("N8", "Steve Ojomoh"), ("HK", "Mark Regan"), ("BF", "Dean Richards"),
            ("OF", "Tim Rodber"), ("LP", "Graham Rowntree"), ("RW", "Jon Sleightholme"),
            ("TP", "Victor Ubogu"), ("LW", "Rory Underwood"),
        ],
    },
    "1997": {
        "England": [
            ("FH", "Rob Andrew"), ("IC", "Will Carling"), ("FB", "Mike Catt"),
            ("BF", "Ben Clarke"), ("N8", "Lawrence Dallaglio"), ("OC", "Phil de Glanville"),
            ("TP", "Darren Garforth"), ("SH", "Andy Gomarsall"), ("FH", "Paul Grayson"),
            ("HK", "Phil Greening"), ("OC", "Jeremy Guscott"), ("RW", "Austin Healey"),
            ("OF", "Richard Hill"), ("LL", "Martin Johnson"), ("LP", "Jason Leonard"),
            ("HK", "Mark Regan"), ("BF", "Tim Rodber"), ("LP", "Graham Rowntree"),
            ("RL", "Simon Shaw"), ("N8", "Chris Sheasby"), ("RW", "Jon Sleightholme"),
            ("FB", "Tim Stimpson"), ("LW", "Tony Underwood"),
        ],
        "France": [
            ("HK", "Guy Accoceberry"), ("FH", "David Aucagne"), ("RL", "Abdelatif Benazzi"),
            ("BF", "Philippe Benetton"), ("LP", "Pierre Bondouy"), ("TP", "Christian Califano"),
            ("SH", "Philippe Carbonneau"), ("FH", "Thomas Castaignède"), ("LP", "Richard Castel"),
            ("HK", "Marc Dal Maso"), ("IC", "Marc de Rougemont"), ("IC", "Richard Dourthe"),
            ("SH", "Fabien Galthié"), ("OC", "Stéphane Glas"), ("HK", "Raphaël Ibañez"),
            ("LL", "Jean-Louis Jordana"), ("FH", "Christophe Lamaison"), ("LP", "Laurent Leflamand"),
            ("OF", "Olivier Magne"), ("RL", "Olivier Merle"), ("BF", "Hugues Miorin"),
            ("RW", "Ugo Mola"), ("LW", "Émile Ntamack"), ("LL", "Fabien Pelous"),
            ("OC", "Alain Penaud"), ("FB", "Jean-Luc Sadourny"), ("LP", "Franck Tournaire"),
            ("RW", "David Venditti"),
        ],
    },
    "1998": {
        "England": [
            ("RW", "Adedayo Adebayo"), ("RL", "Garath Archer"), ("OF", "Neil Back"),
            ("TP", "Scott Benton"), ("SH", "Kyran Bracken"), ("FB", "Mike Catt"),
            ("HK", "Richard Cockerill"), ("N8", "Lawrence Dallaglio"), ("SH", "Matt Dawson"),
            ("OC", "Phil de Glanville"), ("BF", "Tony Diprose"), ("TP", "Darren Garforth"),
            ("FH", "Paul Grayson"), ("IC", "Will Greenwood"), ("RL", "Danny Grewcock"),
            ("OC", "Jeremy Guscott"), ("RW", "Austin Healey"), ("OF", "Richard Hill"),
            ("LL", "Martin Johnson"), ("LP", "Jason Leonard"), ("FB", "Matt Perry"),
            ("LW", "David Rees"), ("HK", "Mark Regan"), ("LP", "Graham Rowntree"),
            ("N8", "Dean Ryan"), ("TP", "Phil Vickery"), ("HK", "Dorian West"),
            ("FH", "Jonny Wilkinson"),
        ],
        "Wales": [
            ("BF", "Rob Appleyard"), ("IC", "Allan Bateman"), ("IC", "Neil Boobyer"),
            ("OF", "Colin Charvis"), ("OC", "Leigh Davies"), ("N8", "Stuart Davies"),
            ("IC", "Scott Gibbs"), ("HK", "Byron Hayward"), ("SH", "Rob Howley"),
            ("HK", "Jonathan Humphreys"), ("RW", "Dafydd James"), ("HK", "Garin Jenkins"),
            ("FH", "Neil Jenkins"), ("SH", "Paul John"), ("BF", "Kingsley Jones"),
            ("LP", "Andrew Lewis"), ("LL", "Gareth Llewellyn"), ("SH", "Andy Moore"),
            ("FB", "Kevin Morgan"), ("TP", "Lyndon Mustoe"), ("RW", "Wayne Proctor"),
            ("N8", "Scott Quinnell"), ("TP", "Stuart Roy"), ("TP", "Chris Stephens"),
            ("FH", "Arwel Thomas"), ("LW", "Gareth Thomas"), ("RL", "Mike Voyle"),
            ("LW", "Nigel Walker"), ("HK", "Barry Williams"), ("OF", "Martyn Williams"),
            ("LP", "David Young"),
        ],
    },
    "1999": {
        "England": [
            ("RL", "Garath Archer"), ("OF", "Neil Back"), ("RW", "Nick Beal"),
            ("SH", "Kyran Bracken"), ("FB", "Mike Catt"), ("HK", "Richard Cockerill"),
            ("OF", "Martin Corry"), ("N8", "Lawrence Dallaglio"), ("SH", "Matt Dawson"),
            ("TP", "Darren Garforth"), ("FH", "Paul Grayson"), ("RL", "Danny Grewcock"),
            ("OC", "Jeremy Guscott"), ("RW", "Steve Hanley"), ("RW", "Austin Healey"),
            ("OF", "Richard Hill"), ("LL", "Martin Johnson"), ("LP", "Jason Leonard"),
            ("LW", "Dan Luger"), ("IC", "Barrie-Jon Mather"), ("TP", "Neil McCarthy"),
            ("FB", "Matt Perry"), ("LW", "David Rees"), ("BF", "Tim Rodber"),
            ("LP", "Graham Rowntree"), ("TP", "Victor Ubogu"), ("LW", "Tony Underwood"),
            ("FH", "Jonny Wilkinson"),
        ],
        "Wales": [
            ("TP", "Chris Anthony"), ("IC", "Allan Bateman"), ("IC", "Neil Boobyer"),
            ("OF", "Colin Charvis"), ("OC", "Leigh Davies"), ("TP", "Ben Evans"),
            ("IC", "Scott Gibbs"), ("RL", "Ian Gough"), ("RW", "Shane Howarth"),
            ("SH", "Rob Howley"), ("HK", "Jonathan Humphreys"), ("RW", "Dafydd James"),
            ("HK", "Garin Jenkins"), ("FH", "Neil Jenkins"), ("LP", "Andrew Lewis"),
            ("BF", "Geraint Lewis"), ("FB", "David Llewellyn"), ("FB", "Kevin Morgan"),
            ("LP", "Darren Morris"), ("RL", "Craig Quinnell"), ("N8", "Scott Quinnell"),
            ("IC", "Matthew Robinson"), ("LP", "Peter Rogers"), ("OF", "Brett Sinkinson"),
            ("OC", "Mark Taylor"), ("LW", "Gareth Thomas"), ("RL", "Mike Voyle"),
            ("LW", "Nick Walne"), ("HK", "Barry Williams"), ("OF", "Martyn Williams"),
            ("RL", "Chris Wyatt"), ("LP", "David Young"),
        ],
    },
}


def _build_pool(entries: List[Tuple[str, str, bool]] | List[Tuple[str, str]], nation: str, era: str) -> List[Player]:
    """Shared build step for both the match-lineup (2000-2017, 3-tuples with
    a `starter` flag) and legacy-squad (1995-1999, 2-tuples) paths - same
    cross-reference-then-archetype-then-union-scale pipeline
    `historical_rwc.build_historical_pool` already established."""
    strength_code = _NATION_TO_STRENGTH_CODE.get(nation)
    strength = UNION_STRENGTH.get(strength_code, DEFAULT_UNION_STRENGTH) if strength_code else DEFAULT_UNION_STRENGTH

    from .sources.pool_builder import _global_reference_peer_proxies
    peer_proxies_by_position = _global_reference_peer_proxies("2026")

    pool: List[Player] = []
    seen: set = set()
    for entry in entries:
        pos_code, name = entry[0], entry[1]
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        position = MATCH_POS_CODE_MAP.get(pos_code)
        if position is None:
            continue
        attrs, source = _cross_reference_attributes(
            name, peer_proxies=peer_proxies_by_position.get(position)
        )
        if attrs is None:
            attrs = _archetype_attributes(position)
        if source != "legends_curated":
            attrs = scale_to_union_strength(attrs, strength)
        data_source = (
            "legends_curated" if source == "legends_curated" else
            "historical_wikipedia" if source == "wikipedia" else "historical_archetype"
        )
        pool.append(Player(
            name=name,
            nation=nation,
            natural_position=position,
            attributes=attrs,
            era=era,
            notes=(
                f"Six Nations Tier-B classic match pool ({era}). "
                + ("World Rugby Hall of Fame - hand-tuned curated rating from "
                   "legends.CURATED_LEGENDS, not a Wikipedia/archetype estimate."
                   if source == "legends_curated" else
                   "Attributes from real rugbydata career stats (cross-referenced by "
                   "name) - likely a career that extended into rugbydata's 2018+ "
                   "coverage." if source == "wikipedia" else
                   "No rugbydata history found for this era/name, so attributes are "
                   "a generic position-archetype estimate, not a scouted rating.")
            ),
            data_source=data_source,
        ))
    return pool


_POOL_CACHE: Dict[Tuple[str, str], List[Player]] = {}


def resolve_pools(match: ClassicMatch) -> Tuple[List[Player], List[Player]]:
    """Returns `(home_pool, away_pool)` for one Tier-B Six Nations
    `ClassicMatch`, built from this module's own real Wikipedia-sourced
    lineups/squads (`_MATCH_LINEUPS`/`_LEGACY_SQUADS`) - the Tier-B
    equivalent of `classic_matches.resolve_pools`, kept separate per this
    module's brief (the caller is responsible for wiring the two together,
    e.g. dispatching on `match.id`'s `"six_nations_tier_b_"` prefix)."""
    year = str(match.year)
    era = f"'{year[-2:]}"

    if year in _MATCH_LINEUPS:
        data = _MATCH_LINEUPS[year]
        home_nation = _CODE_TO_NATION[data["home_code"]]
        away_nation = _CODE_TO_NATION[data["away_code"]]
        cache_key_home = (year, "home")
        cache_key_away = (year, "away")
        if cache_key_home not in _POOL_CACHE:
            _POOL_CACHE[cache_key_home] = _build_pool(data["home"], home_nation, era)
        if cache_key_away not in _POOL_CACHE:
            _POOL_CACHE[cache_key_away] = _build_pool(data["away"], away_nation, era)
        return _POOL_CACHE[cache_key_home], _POOL_CACHE[cache_key_away]

    squads = _LEGACY_SQUADS[year]
    cache_key_home = (year, match.home_name)
    cache_key_away = (year, match.away_name)
    if cache_key_home not in _POOL_CACHE:
        _POOL_CACHE[cache_key_home] = _build_pool(squads[match.home_name], match.home_name, era)
    if cache_key_away not in _POOL_CACHE:
        _POOL_CACHE[cache_key_away] = _build_pool(squads[match.away_name], match.away_name, era)
    return _POOL_CACHE[cache_key_home], _POOL_CACHE[cache_key_away]


# ---------------------------------------------------------------------------
# The 23-entry Tier-B catalog (one per Five/Six Nations edition, 1995-2017).
# ---------------------------------------------------------------------------

TIER_B_SIX_NATIONS_MATCHES: List[ClassicMatch] = [
    ClassicMatch(
        id="six_nations_tier_b_1995", tournament="six_nations", year=1995,
        display_name="1995 Five Nations, Round 3 (\"The Toony Flip\")",
        date="1995-02-18", home_code="SCO", home_name="Scotland",
        away_code="FRA", away_name="France",
        blurb=(
            "Gregor Townsend's no-look 'Toony flip' pass at Murrayfield set up "
            "Gavin Hastings for the winning try."
        ),
        real_score="Scotland 23-21 France",
        focus_team="home",
        objectives=[
            win("Scotland"),
            win_margin_at_least("Scotland", 1),
            no_cards("Scotland"),
            player_tries_at_least("Scotland", "Fullback", 1),
            total_points_at_least(50),  # real total: 44
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_1996", tournament="six_nations", year=1996,
        display_name="1996 Five Nations, Grand Slam Decider",
        date="1996-03-02", home_code="SCO", home_name="Scotland",
        away_code="ENG", away_name="England",
        blurb=(
            "England's Grand Slam bid was denied at Murrayfield - Scotland won "
            "the Calcutta Cup to spoil the party."
        ),
        real_score="Scotland 9-18 England",
        focus_team="away",
        objectives=[
            win("England"),
            win_margin_at_least("England", 5),
            no_cards("England"),
            team_tries_at_least("England", 2),
            total_points_at_least(30),  # real total: 27
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_1997", tournament="six_nations", year=1997,
        display_name="1997 Five Nations, Round 2",
        date="1997-03-01", home_code="ENG", home_name="England",
        away_code="FRA", away_name="France",
        blurb=(
            "England led 20-6 before collapsing at Twickenham - Christophe "
            "Lamaison scored 20 points as France went on to a Grand Slam."
        ),
        real_score="England 20-23 France",
        focus_team="away",
        objectives=[
            win("France"),
            win_margin_at_least("France", 1),
            no_cards("France"),
            player_points_at_least("France", "Fly-half", 21),  # real: 20 (Lamaison)
            total_points_at_least(48),  # real total: 43
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_1998", tournament="six_nations", year=1998,
        display_name="1998 Five Nations, Round 3",
        date="1998-02-21", home_code="ENG", home_name="England",
        away_code="WAL", away_name="Wales",
        blurb=(
            "The highest-scoring Five Nations match ever at the time, at "
            "Twickenham."
        ),
        real_score="England 60-26 Wales",
        focus_team="home",
        objectives=[
            win("England"),
            win_margin_at_least("England", 30),
            no_cards("England"),
            team_tries_at_least("England", 8),  # real: 8
            total_points_at_least(90),  # real total: 86
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_1999", tournament="six_nations", year=1999,
        display_name="1999 Five Nations, Final Round (last-ever Five Nations match)",
        date="1999-04-11", home_code="ENG", home_name="England",
        away_code="WAL", away_name="Wales",
        blurb=(
            "Scott Gibbs' famous late try - converted by Neil Jenkins - denied "
            "England the Grand Slam at Wembley, in the last match the "
            "Five Nations ever played."
        ),
        real_score="England 31-32 Wales",
        focus_team="away",
        objectives=[
            win("Wales"),
            win_margin_at_least("Wales", 1),
            no_cards("Wales"),
            player_tries_at_least("Wales", "Inside Centre", 1),
            total_points_at_least(65),  # real total: 63
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2000", tournament="six_nations", year=2000,
        display_name="2000 Six Nations, Final Round (first-ever Six Nations)",
        date="2000-04-02", home_code="SCO", home_name="Scotland",
        away_code="ENG", away_name="England",
        blurb=(
            "Scotland denied England's Grand Slam bid at Murrayfield, in the "
            "first-ever Six Nations Championship."
        ),
        real_score="Scotland 19-13 England",
        focus_team="home",
        objectives=[
            win("Scotland"),
            win_margin_at_least("Scotland", 1),
            no_cards("Scotland"),
            team_tries_at_least("Scotland", 2),  # real: 2
            total_points_at_least(35),  # real total: 32
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2001", tournament="six_nations", year=2001,
        display_name="2001 Six Nations, Rescheduled Finale",
        date="2001-10-20", home_code="IRE", home_name="Ireland",
        away_code="ENG", away_name="England",
        blurb=(
            "Played 8 months late due to the foot-and-mouth crisis - Keith "
            "Wood's try at Lansdowne Road denied England the Grand Slam."
        ),
        real_score="Ireland 20-14 England",
        focus_team="home",
        objectives=[
            win("Ireland"),
            win_margin_at_least("Ireland", 1),
            no_cards("Ireland"),
            player_tries_at_least("Ireland", "Hooker", 1),
            total_points_at_least(38),  # real total: 34
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2002", tournament="six_nations", year=2002,
        display_name="2002 Six Nations, Final Round",
        date="2002-04-06", home_code="FRA", home_name="France",
        away_code="IRE", away_name="Ireland",
        blurb=(
            "France's first Six-Nations-era Grand Slam, sealed with a rout of "
            "Ireland at the Stade de France."
        ),
        real_score="France 44-5 Ireland",
        focus_team="home",
        objectives=[
            win("France"),
            win_margin_at_least("France", 30),
            no_cards("France"),
            team_tries_at_least("France", 5),  # real: 5
            total_points_at_least(55),  # real total: 49
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2003", tournament="six_nations", year=2003,
        display_name="2003 Six Nations, Grand Slam Decider",
        date="2003-03-30", home_code="IRE", home_name="Ireland",
        away_code="ENG", away_name="England",
        blurb=(
            "England's Grand Slam, sealed at Lansdowne Road - Jonny Wilkinson "
            "kicked 3 drop goals among his points."
        ),
        real_score="Ireland 6-42 England",
        focus_team="away",
        objectives=[
            win("England"),
            win_margin_at_least("England", 25),
            no_cards("England"),
            team_drop_goals_at_least("England", 3),  # real: 3 (Wilkinson)
            total_points_at_least(50),  # real total: 48
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2004", tournament="six_nations", year=2004,
        display_name="2004 Six Nations, Final Round",
        date="2004-03-27", home_code="FRA", home_name="France",
        away_code="ENG", away_name="England",
        blurb=(
            "France's 2nd Grand Slam in 3 years, completed at the Stade de "
            "France against the reigning world champions."
        ),
        real_score="France 24-21 England",
        focus_team="home",
        objectives=[
            win("France"),
            win_margin_at_least("France", 1),
            no_cards("France"),
            team_tries_at_least("France", 2),  # real: 2
            total_points_at_least(50),  # real total: 45
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2005", tournament="six_nations", year=2005,
        display_name="2005 Six Nations, Grand Slam Decider",
        date="2005-03-19", home_code="WAL", home_name="Wales",
        away_code="IRE", away_name="Ireland",
        blurb=(
            "Wales' first Grand Slam since 1978, completed at the Millennium "
            "Stadium."
        ),
        real_score="Wales 32-20 Ireland",
        focus_team="home",
        objectives=[
            win("Wales"),
            win_margin_at_least("Wales", 10),
            no_cards("Wales"),
            team_tries_at_least("Wales", 3),  # real: 3
            total_points_at_least(55),  # real total: 52
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2006", tournament="six_nations", year=2006,
        display_name="2006 Six Nations, Opening Round Shock",
        date="2006-02-05", home_code="SCO", home_name="Scotland",
        away_code="FRA", away_name="France",
        blurb=(
            "A shock Murrayfield upset - France were tournament favourites "
            "and Grand Slam contenders."
        ),
        real_score="Scotland 20-16 France",
        focus_team="home",
        objectives=[
            win("Scotland"),
            win_margin_at_least("Scotland", 1),
            no_cards("Scotland"),
            team_tries_at_least("Scotland", 2),  # real: 2
            total_points_at_least(40),  # real total: 36
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2007", tournament="six_nations", year=2007,
        display_name="2007 Six Nations, Historic Croke Park Test",
        date="2007-02-11", home_code="IRE", home_name="Ireland",
        away_code="FRA", away_name="France",
        blurb=(
            "The first-ever rugby Test at Croke Park - Vincent Clerc's "
            "79th-minute try won it for France."
        ),
        real_score="Ireland 17-20 France",
        focus_team="away",
        objectives=[
            win("France"),
            win_margin_at_least("France", 1),
            no_cards("France"),
            player_tries_at_least("France", "Right Wing", 1),
            total_points_at_least(40),  # real total: 37
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2008", tournament="six_nations", year=2008,
        display_name="2008 Six Nations, Grand Slam Decider",
        date="2008-03-15", home_code="WAL", home_name="Wales",
        away_code="FRA", away_name="France",
        blurb=(
            "Wales' 2nd Grand Slam in 4 years, in front of a record "
            "75,000-strong Millennium Stadium crowd."
        ),
        real_score="Wales 29-12 France",
        focus_team="home",
        objectives=[
            win("Wales"),
            win_margin_at_least("Wales", 15),
            no_cards("Wales"),
            team_tries_at_least("Wales", 3),  # real: 3
            total_points_at_least(45),  # real total: 41
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2009", tournament="six_nations", year=2009,
        display_name="2009 Six Nations, Grand Slam Decider",
        date="2009-03-21", home_code="WAL", home_name="Wales",
        away_code="IRE", away_name="Ireland",
        blurb=(
            "Ronan O'Gara's late drop goal won Ireland's first Grand Slam in "
            "61 years at the Millennium Stadium."
        ),
        real_score="Wales 15-17 Ireland",
        focus_team="away",
        objectives=[
            win("Ireland"),
            win_margin_at_least("Ireland", 1),
            no_cards("Ireland"),
            team_drop_goals_at_least("Ireland", 1),  # real: 1 (O'Gara's winner)
            total_points_at_least(38),  # real total: 32
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2010", tournament="six_nations", year=2010,
        display_name="2010 Six Nations, Grand Slam Decider",
        date="2010-03-20", home_code="FRA", home_name="France",
        away_code="ENG", away_name="England",
        blurb=(
            "France's first Grand Slam since 2004, sealed at the Stade de "
            "France."
        ),
        real_score="France 12-10 England",
        focus_team="home",
        objectives=[
            win("France"),
            win_margin_at_least("France", 1),
            no_cards("France"),
            total_points_at_least(28),  # real total: 22
            team_tries_at_least("France", 1),
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2011", tournament="six_nations", year=2011,
        display_name="2011 Six Nations, Round 4 Shock",
        date="2011-03-12", home_code="ITA", home_name="Italy",
        away_code="FRA", away_name="France",
        blurb=(
            "Italy's first-ever Six Nations win over France, the defending "
            "champions, in Rome."
        ),
        real_score="Italy 22-21 France",
        focus_team="home",
        objectives=[
            win("Italy"),
            win_margin_at_least("Italy", 1),
            no_cards("Italy"),
            team_tries_at_least("Italy", 2),  # real: 2
            total_points_at_least(48),  # real total: 43
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2012", tournament="six_nations", year=2012,
        display_name="2012 Six Nations, Grand Slam Decider",
        date="2012-03-17", home_code="WAL", home_name="Wales",
        away_code="FRA", away_name="France",
        blurb=(
            "Wales' 3rd Grand Slam in 8 years, sealed at the Millennium "
            "Stadium."
        ),
        real_score="Wales 16-9 France",
        focus_team="home",
        objectives=[
            win("Wales"),
            win_margin_at_least("Wales", 5),
            no_cards("Wales"),
            total_points_at_least(30),  # real total: 25
            team_tries_at_least("Wales", 1),
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2013", tournament="six_nations", year=2013,
        display_name="2013 Six Nations, Final Round",
        date="2013-03-16", home_code="WAL", home_name="Wales",
        away_code="ENG", away_name="England",
        blurb=(
            "Wales' biggest-ever win over England, denying England the Grand "
            "Slam at the Millennium Stadium."
        ),
        real_score="Wales 30-3 England",
        focus_team="home",
        objectives=[
            win("Wales"),
            win_margin_at_least("Wales", 20),
            no_cards("Wales"),
            team_tries_at_least("Wales", 3),  # real: 3
            total_points_at_least(40),  # real total: 33
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2014", tournament="six_nations", year=2014,
        display_name="2014 Six Nations, Final Round (O'Driscoll's Farewell)",
        date="2014-03-15", home_code="FRA", home_name="France",
        away_code="IRE", away_name="Ireland",
        blurb=(
            "Ireland's title-deciding win at the Stade de France - Brian "
            "O'Driscoll's farewell Test."
        ),
        real_score="France 20-22 Ireland",
        focus_team="away",
        objectives=[
            win("Ireland"),
            win_margin_at_least("Ireland", 1),
            no_cards("Ireland"),
            player_tries_at_least("Ireland", "Outside Centre", 1),
            total_points_at_least(48),  # real total: 42
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2015", tournament="six_nations", year=2015,
        display_name="2015 Six Nations, \"Super Saturday\" Final Round",
        date="2015-03-21", home_code="ENG", home_name="England",
        away_code="FRA", away_name="France",
        blurb=(
            "A 221-point, 27-try final-round day across the whole "
            "Championship - Ireland won the title without playing that "
            "afternoon."
        ),
        real_score="England 55-35 France",
        focus_team="home",
        objectives=[
            win("England"),
            win_margin_at_least("England", 15),
            no_cards("England"),
            team_tries_at_least("England", 8),  # real: 8
            total_points_at_least(100),  # real total: 90
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2016", tournament="six_nations", year=2016,
        display_name="2016 Six Nations, Grand Slam Decider",
        date="2016-03-19", home_code="FRA", home_name="France",
        away_code="ENG", away_name="England",
        blurb=(
            "England's first Grand Slam since 2003, sealed at the Stade de "
            "France in Eddie Jones' first title as head coach."
        ),
        real_score="France 21-31 England",
        focus_team="away",
        objectives=[
            win("England"),
            win_margin_at_least("England", 5),
            no_cards("England"),
            team_tries_at_least("England", 3),  # real: 3
            total_points_at_least(55),  # real total: 52
        ],
    ),
    ClassicMatch(
        id="six_nations_tier_b_2017", tournament="six_nations", year=2017,
        display_name="2017 Six Nations, Final Round",
        date="2017-03-18", home_code="IRE", home_name="Ireland",
        away_code="ENG", away_name="England",
        blurb=(
            "Ireland ended England's world-record 18-match winning run in "
            "Dublin."
        ),
        real_score="Ireland 13-9 England",
        focus_team="home",
        objectives=[
            win("Ireland"),
            win_margin_at_least("Ireland", 1),
            no_cards("Ireland"),
            team_tries_at_least("Ireland", 1),  # real: 1
            total_points_at_least(28),  # real total: 22
        ],
    ),
]
