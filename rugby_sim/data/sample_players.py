"""A small seed roster to get started - mostly England-flavoured plus a
couple of iconic cross-era names (Lomu '97, McInnes-style '08 hooker) so
the "what if" premise (e.g. Lomu at fullback) can be tried immediately.

Extend this freely, or load your own players via `Player(...)` /
`Attributes(...)` directly - this file is just a convenience starting set,
not a schema.
"""

from __future__ import annotations

from ..models.attributes import Attributes
from ..models.player import Player
from ..models.position import Position
from .legends import LEGENDS

ENGLAND_SAMPLE = [
    Player("Ellis Genge", "England", Position.LOOSEHEAD_PROP,
           Attributes(scrummaging=84, strength=83, tackling=72, fitness=78, discipline=62, versatility=35)),
    Player("Jamie George", "England", Position.HOOKER,
           Attributes(lineout_throwing=85, scrummaging=75, tackling=74, handling=76, fitness=80, game_intelligence=78, versatility=40)),
    Player("Dan Cole", "England", Position.TIGHTHEAD_PROP,
           Attributes(scrummaging=88, strength=82, tackling=68, fitness=70, discipline=70, versatility=25)),
    Player("Maro Itoje", "England", Position.LOCK_1,
           Attributes(lineout_jumping=90, strength=85, tackling=85, scrummaging=78, fitness=84, aerial=80, game_intelligence=82, versatility=55)),
    Player("George Martin", "England", Position.LOCK_2,
           Attributes(lineout_jumping=80, strength=86, tackling=86, scrummaging=76, fitness=82, aerial=74, versatility=45)),
    Player("Tom Curry", "England", Position.BLINDSIDE_FLANKER,
           Attributes(tackling=88, strength=78, fitness=88, tackle_technique=86, game_intelligence=80, versatility=60)),
    Player("Sam Underhill", "England", Position.OPENSIDE_FLANKER,
           Attributes(tackling=90, fitness=86, pace=70, tackle_technique=90, game_intelligence=78, agility=74, versatility=50)),
    Player("Billy Vunipola", "England", Position.NUMBER_8,
           Attributes(strength=92, tackling=80, pace=68, fitness=78, handling=74, offload=78, game_intelligence=72, versatility=40)),
    Player("Alex Mitchell", "England", Position.SCRUM_HALF,
           Attributes(passing=86, game_intelligence=80, kicking_game=74, pace=80, handling=84, composure=76, versatility=45)),
    Player("Marcus Smith", "England", Position.FLY_HALF,
           Attributes(kicking_game=82, game_intelligence=88, passing=84, goal_kicking=78, composure=80, handling=86, pace=78, footwork=86, versatility=70)),
    Player("Tommy Freeman", "England", Position.LEFT_WING,
           Attributes(pace=90, footwork=78, aerial=68, tackling=68, agility=82, versatility=50)),
    Player("Ollie Lawrence", "England", Position.INSIDE_CENTRE,
           Attributes(strength=84, tackling=82, passing=72, game_intelligence=74, offload=68, pace=78, versatility=45)),
    Player("Henry Slade", "England", Position.OUTSIDE_CENTRE,
           Attributes(pace=78, footwork=84, passing=82, tackling=74, game_intelligence=84, offload=78, versatility=55)),
    Player("Immanuel Feyi-Waboso", "England", Position.RIGHT_WING,
           Attributes(pace=92, footwork=84, aerial=66, tackling=66, agility=86, versatility=40)),
    Player("Freddie Steward", "England", Position.FULLBACK,
           Attributes(aerial=90, kicking_game=78, pace=76, composure=82, game_intelligence=78, tackling=76, footwork=66, versatility=50)),
]

# `LEGENDS` (Hall of Fame "what if" players, ~30 of them) now lives in its
# own module, `rugby_sim/data/legends.py` - re-exported here for anyone
# already importing it from `sample_players`.
ALL_SAMPLE_PLAYERS = ENGLAND_SAMPLE + LEGENDS
