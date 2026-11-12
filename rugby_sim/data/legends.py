"""Hall of Fame "legend" players - era-specific, and kept deliberately
separate from the real national-team `POOLS` registry.

Two tiers:
- `CURATED_LEGENDS` (~30): hand-tuned `Attributes` from real-world
  reputation/playing style, `data_source="manual"` - the original
  Jonah Lomu '97 / John Smit '08-style entries.
- `get_all_legends()` (~125 total): the above PLUS every other resolvable
  member of Wikipedia's "Category:World Rugby Hall of Fame inductees"
  (190 members total; the rest are filtered out automatically because
  they're not individual player biographies - teams, tours, institutions,
  non-playing administrators - or their infobox didn't have a parseable
  position/nation). Each of those extra entries has its position/nation/
  era parsed straight from that person's own Wikipedia infobox (see
  `rugby_sim/data/sources/hof_scraper.py`) - real - but a generic
  position-archetype rating, not a scouted one, `data_source="hof_archetype"`.
  This is network-heavy on first call (~190 page fetches); results are
  disk-cached, so later calls (even in a new process) are instant.

By design, legends are NOT part of any `POOLS[code]` union pool and will
never get pulled in by "by nation" team drafting or a real-tournament
replay - they only show up where a team is built from a free/custom pool
mix (see `rugby_sim/interactive_cli.py`'s "LEG" pseudo-code). Nothing stops
you from drafting an all-time XV, but it has to be a deliberate choice.
"""

from __future__ import annotations

from typing import List, Optional

from ..models.attributes import Attributes
from ..models.player import Player
from ..models.position import Position

CURATED_LEGENDS: List[Player] = [
    Player("Jonah Lomu", "New Zealand", Position.RIGHT_WING,
           Attributes(pace=96, strength=97, footwork=80, aerial=72, tackling=70,
                      handling=70, offload=74, agility=78, fitness=84, versatility=55),
           era="'97", notes="World Rugby Hall of Fame. 1995/97 peak Lomu - the archetypal "
           "'what if' piece.", data_source="manual"),
    Player("John Smit", "South Africa", Position.HOOKER,
           Attributes(scrummaging=88, lineout_throwing=80, strength=86, tackling=78,
                      leadership=92, game_intelligence=80, fitness=78, versatility=45),
           era="'08", notes="World Rugby Hall of Fame. Captained South Africa to the "
           "2007 World Cup; later moved to tighthead.", data_source="manual"),
    Player("Richie McCaw", "New Zealand", Position.OPENSIDE_FLANKER,
           Attributes(tackling=95, fitness=94, tackle_technique=94, game_intelligence=92,
                      leadership=94, pace=74, versatility=50),
           era="'15", notes="World Rugby Hall of Fame. Two-time World Cup winning captain.",
           data_source="manual"),
    Player("Dan Carter", "New Zealand", Position.FLY_HALF,
           Attributes(kicking_game=94, goal_kicking=93, game_intelligence=92, passing=90,
                      composure=92, handling=88, pace=76, versatility=45),
           era="'15", notes="World Rugby Hall of Fame. Widely rated the best fly-half "
           "of his generation.", data_source="manual"),
    Player("Brian O'Driscoll", "Ireland", Position.OUTSIDE_CENTRE,
           Attributes(pace=84, footwork=90, tackling=84, game_intelligence=90, offload=82,
                      passing=82, versatility=50), era="'09",
           notes="World Rugby Hall of Fame. Lions and Ireland captain, 2009 Grand Slam.",
           data_source="manual"),
    Player("Jonny Wilkinson", "England", Position.FLY_HALF,
           Attributes(kicking_game=92, goal_kicking=96, composure=95, tackling=76,
                      game_intelligence=88, handling=82, versatility=40), era="'03",
           notes="World Rugby Hall of Fame. 2003 World Cup-winning drop goal.",
           data_source="manual"),
    Player("Martin Johnson", "England", Position.LOCK_1,
           Attributes(lineout_jumping=86, strength=90, tackling=84, scrummaging=84,
                      leadership=94, fitness=76, versatility=35), era="'03",
           notes="World Rugby Hall of Fame. 2003 World Cup-winning captain.",
           data_source="manual"),
    Player("Lawrence Dallaglio", "England", Position.NUMBER_8,
           Attributes(strength=88, tackling=86, fitness=84, handling=76, offload=72,
                      game_intelligence=80, versatility=40), era="'03",
           notes="World Rugby Hall of Fame. 2003 World Cup winner.", data_source="manual"),
    Player("Jason Leonard", "England", Position.LOOSEHEAD_PROP,
           Attributes(scrummaging=88, strength=84, fitness=78, tackling=72, discipline=82,
                      versatility=45), era="'03",
           notes="World Rugby Hall of Fame. Most-capped England prop of his era.",
           data_source="manual"),
    Player("Gareth Edwards", "Wales", Position.SCRUM_HALF,
           Attributes(passing=94, pace=88, game_intelligence=90, kicking_game=78,
                      handling=90, composure=86, versatility=40), era="'73",
           notes="World Rugby Hall of Fame. Often named the greatest player ever to "
           "play the game.", data_source="manual"),
    Player("Barry John", "Wales", Position.FLY_HALF,
           Attributes(kicking_game=88, game_intelligence=90, passing=84, composure=90,
                      footwork=82, versatility=35), era="'71",
           notes="World Rugby Hall of Fame. 'The King' - 1971 Lions tour.",
           data_source="manual"),
    Player("J. P. R. Williams", "Wales", Position.FULLBACK,
           Attributes(tackling=86, aerial=78, pace=78, composure=84, footwork=76,
                      game_intelligence=80, versatility=35), era="'71",
           notes="World Rugby Hall of Fame. Pioneering attacking fullback.",
           data_source="manual"),
    Player("Shane Williams", "Wales", Position.LEFT_WING,
           Attributes(pace=90, footwork=96, agility=94, aerial=58, tackling=62,
                      offload=72, versatility=40), era="'08",
           notes="World Rugby Hall of Fame. 2008 World Rugby Player of the Year.",
           data_source="manual"),
    Player("Serge Blanco", "France", Position.FULLBACK,
           Attributes(pace=86, footwork=88, aerial=76, kicking_game=78, composure=86,
                      game_intelligence=86, versatility=45), era="'87",
           notes="World Rugby Hall of Fame. Attacking fullback icon of the 1980s.",
           data_source="manual"),
    Player("Philippe Sella", "France", Position.INSIDE_CENTRE,
           Attributes(strength=82, tackling=84, passing=80, game_intelligence=86,
                      pace=78, offload=74, versatility=40), era="'91",
           notes="World Rugby Hall of Fame. Most-capped centre of his generation.",
           data_source="manual"),
    Player("Jean-Pierre Rives", "France", Position.BLINDSIDE_FLANKER,
           Attributes(tackling=88, fitness=86, tackle_technique=84, leadership=86,
                      game_intelligence=80, versatility=45), era="'81",
           notes="World Rugby Hall of Fame. Iconic blond-haired French captain.",
           data_source="manual"),
    Player("David Campese", "Australia", Position.RIGHT_WING,
           Attributes(pace=90, footwork=92, aerial=62, offload=80, agility=88,
                      game_intelligence=82, versatility=45), era="'91",
           notes="World Rugby Hall of Fame. 1991 World Cup winner, maverick finisher.",
           data_source="manual"),
    Player("Tim Horan", "Australia", Position.INSIDE_CENTRE,
           Attributes(tackling=86, strength=78, passing=80, game_intelligence=88,
                      pace=76, offload=76, versatility=45), era="'99",
           notes="World Rugby Hall of Fame. Two-time World Cup winner (1991, 1999).",
           data_source="manual"),
    Player("George Gregan", "Australia", Position.SCRUM_HALF,
           Attributes(passing=86, game_intelligence=88, tackling=76, kicking_game=72,
                      composure=88, pace=74, versatility=35), era="'99",
           notes="World Rugby Hall of Fame. Most-capped scrum-half of his era.",
           data_source="manual"),
    Player("Naas Botha", "South Africa", Position.FLY_HALF,
           Attributes(kicking_game=90, goal_kicking=92, game_intelligence=84,
                      composure=88, passing=74, versatility=30), era="'92",
           notes="World Rugby Hall of Fame. Prolific goal-kicker of the apartheid-era "
           "Springboks.", data_source="manual"),
    Player("Danie Gerber", "South Africa", Position.OUTSIDE_CENTRE,
           Attributes(pace=84, strength=78, footwork=84, tackling=78, game_intelligence=84,
                      offload=72, versatility=40), era="'92",
           notes="World Rugby Hall of Fame. Regarded as South Africa's finest-ever centre.",
           data_source="manual"),
    Player("Frik du Preez", "South Africa", Position.LOCK_2,
           Attributes(lineout_jumping=82, strength=88, tackling=80, scrummaging=80,
                      fitness=78, aerial=72, versatility=40), era="'70",
           notes="World Rugby Hall of Fame. 1960s-70s Springbok great, athletic lock.",
           data_source="manual"),
    Player("Bryan Habana", "South Africa", Position.RIGHT_WING,
           Attributes(pace=94, footwork=78, aerial=66, tackling=68, agility=84,
                      versatility=35), era="'07",
           notes="World Rugby Hall of Fame. 2007 World Cup winner, 2007 World Rugby "
           "Player of the Year.", data_source="manual"),
    Player("Joost van der Westhuizen", "South Africa", Position.SCRUM_HALF,
           Attributes(passing=84, strength=78, tackling=82, pace=80, game_intelligence=84,
                      kicking_game=70, versatility=35), era="'95",
           notes="World Rugby Hall of Fame. 1995 World Cup winner, powerful box-kicking "
           "scrum-half.", data_source="manual"),
    Player("Zinzan Brooke", "New Zealand", Position.NUMBER_8,
           Attributes(strength=84, handling=82, kicking_game=68, tackling=82, offload=80,
                      game_intelligence=84, versatility=40), era="'95",
           notes="World Rugby Hall of Fame. Famed for drop goals from a number 8.",
           data_source="manual"),
    Player("Michael Jones", "New Zealand", Position.OPENSIDE_FLANKER,
           Attributes(tackling=90, fitness=90, pace=80, tackle_technique=88,
                      game_intelligence=84, versatility=40), era="'95",
           notes="World Rugby Hall of Fame. Regarded as one of the first truly modern "
           "opensides.", data_source="manual"),
    Player("Colin Meads", "New Zealand", Position.LOCK_1,
           Attributes(strength=90, tackling=86, lineout_jumping=76, scrummaging=82,
                      fitness=82, leadership=84, versatility=35), era="'67",
           notes="World Rugby Hall of Fame. 'Pinetree' - an all-time All Blacks great "
           "of the 1960s.", data_source="manual"),
    Player("Agustin Pichot", "Argentina", Position.SCRUM_HALF,
           Attributes(passing=82, game_intelligence=86, tackling=74, pace=74,
                      leadership=88, kicking_game=68, versatility=35), era="'07",
           notes="World Rugby Hall of Fame. Captained Los Pumas to third at the 2007 "
           "World Cup.", data_source="manual"),
    Player("Hugo Porta", "Argentina", Position.FLY_HALF,
           Attributes(kicking_game=88, goal_kicking=86, game_intelligence=86,
                      composure=86, passing=72, versatility=30), era="'85",
           notes="World Rugby Hall of Fame. The first great Argentine rugby star.",
           data_source="manual"),
    Player("Diego Dominguez", "Italy", Position.FLY_HALF,
           Attributes(kicking_game=86, goal_kicking=90, game_intelligence=82,
                      composure=84, passing=74, versatility=30), era="'99",
           notes="World Rugby Hall of Fame. Prolific point-scorer for Italy.",
           data_source="manual"),
    Player("Keith Wood", "Ireland", Position.HOOKER,
           Attributes(scrummaging=80, lineout_throwing=74, tackling=82, handling=78,
                      strength=82, leadership=84, offload=70, versatility=45), era="'01",
           notes="World Rugby Hall of Fame. Dynamic, ball-carrying hooker and Lions "
           "captain.", data_source="manual"),
    Player("Willie John McBride", "Ireland", Position.LOCK_1,
           Attributes(strength=86, tackling=82, lineout_jumping=68, scrummaging=78,
                      leadership=90, fitness=76, versatility=35), era="'74",
           notes="World Rugby Hall of Fame. Led the unbeaten 1974 Lions to South Africa.",
           data_source="manual"),
]

# Backwards-compatible name (this used to be the whole list).
LEGENDS = CURATED_LEGENDS

_full_cache: Optional[List[Player]] = None


def get_all_legends(force_refresh: bool = False) -> List[Player]:
    """`CURATED_LEGENDS` plus every other resolvable Hall of Fame member
    (see module docstring). A curated entry always wins over its scraped
    counterpart on a name collision, since it has a hand-tuned rating."""
    global _full_cache
    if _full_cache is not None and not force_refresh:
        return _full_cache

    from .sources.hof_scraper import build_all_hof_legends

    curated_names = {p.name.strip().lower() for p in CURATED_LEGENDS}
    scraped = build_all_hof_legends()
    merged = list(CURATED_LEGENDS)
    for player in scraped:
        if player.name.strip().lower() in curated_names:
            continue
        merged.append(player)

    _full_cache = merged
    return merged
