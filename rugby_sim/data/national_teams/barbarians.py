"""Barbarian F.C. - not a World Rugby union, so it isn't in the rugbydata
dataset at all (confirmed by scanning the whole dataset for "Barbarian").
Manually entered from the 2026 summer tour squad (v South Africa, 20 June
2026) via public match-report coverage (barbarianfc.co.uk, supersport.com,
rugby.com.au, edinburghrugby.org - the full matchday-23 announcement).
Each player's real `nation` is kept - turning out for the Barbarians
doesn't change anyone's eligibility - and `notes` records the invitational
call-up instead. The original 10-player list only covered a handful of the
real announced squad (not enough to fill every position for a lineup) -
the rest of the real matchday 23 was added afterward from the same
coverage, same manual/hand-estimated-rating convention.
"""

from __future__ import annotations

from typing import List

from ...models.attributes import Attributes
from ...models.player import Player
from ...models.position import Position
from ._union_pool import lazy_invitational_pool

CODE = "BAR"

_POOL: List[Player] = [
    Player("TJ Perenara", "New Zealand", Position.SCRUM_HALF,
           Attributes(passing=88, game_intelligence=90, kicking_game=78, pace=80,
                      handling=86, composure=84, leadership=90, versatility=55),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - captain.",
           data_source="manual"),
    Player("Duhan van der Merwe", "Scotland", Position.LEFT_WING,
           Attributes(pace=93, strength=88, footwork=76, aerial=70, tackling=68,
                      agility=80, offload=72, versatility=45),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started on the wing.",
           data_source="manual"),
    Player("Andrew Kellaway", "Australia", Position.FULLBACK,
           Attributes(pace=85, aerial=82, kicking_game=74, composure=78,
                      game_intelligence=78, tackling=74, footwork=74, versatility=65),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - back three.",
           data_source="manual"),
    Player("Kyle Sinckler", "England", Position.TIGHTHEAD_PROP,
           Attributes(scrummaging=86, strength=88, tackling=76, fitness=76,
                      handling=70, discipline=58, versatility=35),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 squad.",
           data_source="manual"),
    Player("D'Arcy Rae", "Scotland", Position.LOOSEHEAD_PROP,
           Attributes(scrummaging=82, strength=82, tackling=72, fitness=78, versatility=35),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Izack Rodda", "Australia", Position.LOCK_2,
           Attributes(lineout_jumping=80, strength=86, tackling=78, scrummaging=76,
                      fitness=78, aerial=76, versatility=40),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - bench lock.",
           data_source="manual"),
    Player("Liam McConnell", "Scotland", Position.BLINDSIDE_FLANKER,
           Attributes(tackling=80, strength=78, fitness=84, tackle_technique=78,
                      game_intelligence=72, versatility=45),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - bench back row.",
           data_source="manual"),
    Player("Tomas Albornoz", "Argentina", Position.FLY_HALF,
           Attributes(kicking_game=80, game_intelligence=80, passing=80, goal_kicking=78,
                      composure=76, handling=80, versatility=55),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 squad.",
           data_source="manual"),
    Player("Santiago Arata", "Uruguay", Position.SCRUM_HALF,
           Attributes(passing=78, game_intelligence=76, kicking_game=68, pace=78,
                      handling=80, composure=74, versatility=45),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 squad.",
           data_source="manual"),
    Player("Warrick Gelant", "South Africa", Position.FULLBACK,
           Attributes(pace=88, aerial=76, kicking_game=72, composure=76,
                      game_intelligence=76, footwork=82, versatility=55),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Elliot Dee", "Wales", Position.HOOKER,
           Attributes(scrummaging=74, lineout_throwing=78, tackling=76, fitness=78,
                      handling=74, versatility=35),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started at hooker.",
           data_source="manual"),
    Player("Oli Kebble", "Scotland", Position.LOOSEHEAD_PROP,
           Attributes(scrummaging=78, strength=80, tackling=70, fitness=74, versatility=30),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - bench prop.",
           data_source="manual"),
    Player("Mayco Vivas", "Argentina", Position.TIGHTHEAD_PROP,
           Attributes(scrummaging=80, strength=82, tackling=72, fitness=74, versatility=30),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Pedro Delgado", "Argentina", Position.TIGHTHEAD_PROP,
           Attributes(scrummaging=76, strength=78, tackling=68, fitness=72, versatility=30),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - bench prop.",
           data_source="manual"),
    Player("Guido Petti", "Argentina", Position.LOCK_1,
           Attributes(lineout_jumping=82, strength=84, tackling=80, scrummaging=76,
                      fitness=78, aerial=72, versatility=35),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Franco Molina", "Argentina", Position.LOCK_2,
           Attributes(lineout_jumping=76, strength=80, tackling=76, scrummaging=74,
                      fitness=74, aerial=68, versatility=30),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Lachlan Boshier", "New Zealand", Position.OPENSIDE_FLANKER,
           Attributes(tackling=82, fitness=84, game_intelligence=76, tackle_technique=78,
                      strength=76, pace=68, versatility=40),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Alex Moon", "Australia", Position.BLINDSIDE_FLANKER,
           Attributes(tackling=78, strength=78, fitness=80, tackle_technique=74,
                      game_intelligence=70, versatility=35),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Leonel Oviedo", "Argentina", Position.BLINDSIDE_FLANKER,
           Attributes(tackling=76, strength=76, fitness=78, tackle_technique=72,
                      game_intelligence=68, versatility=35),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - bench back row.",
           data_source="manual"),
    Player("Miracle Fai'ilagi", "Australia", Position.NUMBER_8,
           Attributes(strength=82, tackling=78, fitness=80, handling=70,
                      game_intelligence=68, pace=66, versatility=30),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Harry Plummer", "New Zealand", Position.FLY_HALF,
           Attributes(kicking_game=76, game_intelligence=76, passing=76, goal_kicking=72,
                      composure=72, handling=76, versatility=55),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 squad.",
           data_source="manual"),
    Player("Virimi Vakatawa", "France", Position.INSIDE_CENTRE,
           Attributes(pace=84, strength=82, offload=86, footwork=80, handling=78,
                      tackling=68, agility=80, versatility=50),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Alex Nankivell", "New Zealand", Position.OUTSIDE_CENTRE,
           Attributes(pace=78, strength=80, tackling=78, footwork=74, handling=76,
                      game_intelligence=74, versatility=45),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - started.",
           data_source="manual"),
    Player("Tuidraki Samusamuvodre", "Fiji", Position.RIGHT_WING,
           Attributes(pace=86, footwork=80, agility=82, strength=74, handling=70,
                      offload=72, versatility=40),
           era="'26", notes="Barbarians v South Africa, 20 Jun 2026 - bench back three.",
           data_source="manual"),
]


# `season` is accepted for interface parity with the other pools, but
# ignored - the Barbarians are an invitational side assembled per fixture,
# not a union with a per-year roster, and this manual list isn't dated
# beyond the single 2026 tour it was entered from.
get_pool = lazy_invitational_pool(lambda: _POOL)
