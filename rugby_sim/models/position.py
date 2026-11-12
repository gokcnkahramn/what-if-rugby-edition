"""The 15 rugby union positions and the attribute profile each demands.

Each profile is a dict of {attribute_name: weight}. Weights don't need to
sum to 1 - they are normalized when a rating is computed. This is the core
lever for the "what if" premise: plug any player into any profile and see
how their attributes map onto a position they never actually played.
"""

from __future__ import annotations

from enum import Enum


class Position(str, Enum):
    LOOSEHEAD_PROP = "Loosehead Prop"
    HOOKER = "Hooker"
    TIGHTHEAD_PROP = "Tighthead Prop"
    LOCK_1 = "Lock (4)"
    LOCK_2 = "Lock (5)"
    BLINDSIDE_FLANKER = "Blindside Flanker"
    OPENSIDE_FLANKER = "Openside Flanker"
    NUMBER_8 = "Number 8"
    SCRUM_HALF = "Scrum-half"
    FLY_HALF = "Fly-half"
    LEFT_WING = "Left Wing"
    INSIDE_CENTRE = "Inside Centre"
    OUTSIDE_CENTRE = "Outside Centre"
    RIGHT_WING = "Right Wing"
    FULLBACK = "Fullback"


# Shirt numbers in the traditional order, handy for lineup printing.
JERSEY_NUMBER = {
    Position.LOOSEHEAD_PROP: 1,
    Position.HOOKER: 2,
    Position.TIGHTHEAD_PROP: 3,
    Position.LOCK_1: 4,
    Position.LOCK_2: 5,
    Position.BLINDSIDE_FLANKER: 6,
    Position.OPENSIDE_FLANKER: 7,
    Position.NUMBER_8: 8,
    Position.SCRUM_HALF: 9,
    Position.FLY_HALF: 10,
    Position.LEFT_WING: 11,
    Position.INSIDE_CENTRE: 12,
    Position.OUTSIDE_CENTRE: 13,
    Position.RIGHT_WING: 14,
    Position.FULLBACK: 15,
}

FORWARDS = {
    Position.LOOSEHEAD_PROP, Position.HOOKER, Position.TIGHTHEAD_PROP,
    Position.LOCK_1, Position.LOCK_2, Position.BLINDSIDE_FLANKER,
    Position.OPENSIDE_FLANKER, Position.NUMBER_8,
}
BACKS = set(Position) - FORWARDS

# Which positions actually feed a given team-level sub-rating category
# (`Lineup.team_sub_rating` / `MatchEngine._team_sub_rating`). Before this
# existed, EVERY category was averaged across all 15 starters - so a
# team's scrum rating, say, was diluted by 10 backs who barely scrummage,
# and a winger's weak lineout_jumping dragged down a category they're
# never actually involved in. A category not listed here (tackling,
# attack, handling, discipline) genuinely is whole-team, so it still
# averages over all 15 - that's a deliberate "team-wide" choice, not an
# oversight.
CATEGORY_POSITION_GROUPS: dict[str, set] = {
    "scrum": {
        Position.LOOSEHEAD_PROP, Position.HOOKER, Position.TIGHTHEAD_PROP,
        Position.LOCK_1, Position.LOCK_2,
    },
    "lineout": {
        Position.HOOKER, Position.LOCK_1, Position.LOCK_2,
        Position.BLINDSIDE_FLANKER, Position.OPENSIDE_FLANKER, Position.NUMBER_8,
    },
    "lineout_throw": {Position.HOOKER},
    "aerial": {
        Position.FULLBACK, Position.LEFT_WING, Position.RIGHT_WING,
        Position.LOCK_1, Position.LOCK_2,
    },
    "kicking": {Position.SCRUM_HALF, Position.FLY_HALF, Position.FULLBACK},
}

# Attribute weight profile per position. These drive both the "fit rating"
# used to judge an out-of-position selection, and the raw contribution the
# player makes to team sub-ratings (scrum, lineout, defense, attack, ...).
POSITION_PROFILES: dict[Position, dict[str, float]] = {
    Position.LOOSEHEAD_PROP: {
        "scrummaging": 3.0, "strength": 2.0, "tackling": 1.0,
        "fitness": 1.0, "discipline": 1.0,
    },
    Position.HOOKER: {
        "lineout_throwing": 2.5, "scrummaging": 2.0, "tackling": 1.5,
        "handling": 1.0, "fitness": 1.0, "game_intelligence": 1.0,
    },
    Position.TIGHTHEAD_PROP: {
        "scrummaging": 3.0, "strength": 2.0, "tackling": 1.0,
        "fitness": 1.0, "discipline": 1.0,
    },
    Position.LOCK_1: {
        "lineout_jumping": 2.5, "strength": 2.0, "tackling": 1.5,
        "scrummaging": 1.5, "fitness": 1.0, "aerial": 1.0,
    },
    Position.LOCK_2: {
        "lineout_jumping": 2.5, "strength": 2.0, "tackling": 1.5,
        "scrummaging": 1.5, "fitness": 1.0, "aerial": 1.0,
    },
    Position.BLINDSIDE_FLANKER: {
        "tackling": 2.5, "strength": 2.0, "fitness": 1.5,
        "tackle_technique": 1.5, "game_intelligence": 1.0, "lineout_jumping": 0.5,
    },
    Position.OPENSIDE_FLANKER: {
        "tackling": 2.5, "fitness": 2.0, "pace": 1.0,
        "tackle_technique": 2.0, "game_intelligence": 1.5, "agility": 1.0,
    },
    Position.NUMBER_8: {
        "strength": 2.0, "tackling": 2.0, "pace": 1.0, "fitness": 1.5,
        "handling": 1.0, "game_intelligence": 1.0, "offload": 1.0,
    },
    Position.SCRUM_HALF: {
        "passing": 3.0, "game_intelligence": 2.0, "kicking_game": 1.5,
        "pace": 1.0, "handling": 1.5, "composure": 1.0,
    },
    Position.FLY_HALF: {
        "kicking_game": 2.5, "game_intelligence": 2.5, "passing": 2.0,
        "goal_kicking": 1.5, "composure": 1.5, "handling": 1.0,
    },
    Position.LEFT_WING: {
        "pace": 3.0, "footwork": 1.5,
        "aerial": 1.0, "tackling": 1.0, "agility": 1.5,
    },
    Position.INSIDE_CENTRE: {
        "strength": 1.5, "tackling": 2.0, "passing": 1.5,
        "game_intelligence": 1.5, "offload": 1.0, "pace": 1.0,
    },
    Position.OUTSIDE_CENTRE: {
        "pace": 2.0, "footwork": 1.5, "passing": 1.5, "tackling": 1.5,
        "game_intelligence": 1.0, "offload": 1.0,
    },
    Position.RIGHT_WING: {
        "pace": 3.0, "footwork": 1.5, "aerial": 1.0,
        "tackling": 1.0, "agility": 1.5,
    },
    Position.FULLBACK: {
        "aerial": 2.5, "kicking_game": 1.5, "pace": 1.5, "composure": 1.5,
        "game_intelligence": 1.5, "tackling": 1.0, "footwork": 1.0,
    },
}
