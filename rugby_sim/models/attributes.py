"""Player attribute model.

All attributes are on a 1-100 scale, roughly comparable to a FIFA/NFL-style
rating so that custom and historical players can be scouted consistently.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass
class Attributes:
    # Physical
    pace: int = 50
    acceleration: int = 50
    strength: int = 50
    fitness: int = 50
    agility: int = 50

    # Contact / defense
    tackling: int = 50
    tackle_technique: int = 50
    aerial: int = 50  # high-ball / restart contests

    # Set piece
    scrummaging: int = 50
    lineout_jumping: int = 50
    lineout_throwing: int = 50

    # Skill
    handling: int = 50
    passing: int = 50
    offload: int = 50
    footwork: int = 50
    kicking_game: int = 50  # tactical / territorial kicking
    goal_kicking: int = 50
    place_kicking_range: int = 50

    # Mental
    game_intelligence: int = 50
    positioning: int = 50
    leadership: int = 50
    discipline: int = 50  # lower -> more prone to penalties/cards
    composure: int = 50

    # Versatility: how well the player adapts when played out of position.
    # 100 = seamless adaptation, 0 = relies entirely on natural position.
    versatility: int = 40

    def clamp(self) -> "Attributes":
        """Return a copy with all values clamped to [1, 100]."""
        data = {}
        for f in fields(self):
            v = getattr(self, f.name)
            data[f.name] = max(1, min(100, int(v)))
        return Attributes(**data)

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict) -> "Attributes":
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered).clamp()
