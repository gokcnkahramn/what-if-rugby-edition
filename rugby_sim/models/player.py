from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .attributes import Attributes
from .position import Position, POSITION_PROFILES


@dataclass
class Player:
    name: str
    nation: str
    natural_position: Position
    attributes: Attributes = field(default_factory=Attributes)
    era: Optional[str] = None  # e.g. "1997" or "2008" for historical snapshots
    notes: str = ""
    data_source: str = "manual"  # "rugbydata" | "wikipedia" | "manual" (provenance)

    def rating_at(self, position: Position) -> float:
        """0-100 'fit' rating for playing this player at `position`.

        The weighted attribute score is the baseline. If the position is not
        the player's natural one, we apply a penalty scaled by how different
        the position is and softened by the player's versatility - this is
        what lets a "what if Lomu plays fullback" experiment feel earned
        rather than just free-rolled.
        """
        profile = POSITION_PROFILES[position]
        total_weight = sum(profile.values())
        attrs = self.attributes.as_dict()
        raw = sum(attrs.get(attr, 50) * w for attr, w in profile.items())
        base_score = raw / total_weight if total_weight else 50.0

        if position == self.natural_position:
            return round(min(100.0, base_score), 1)

        penalty_factor = self._out_of_position_penalty(position)
        adjusted = base_score * penalty_factor
        return round(max(1.0, min(100.0, adjusted)), 1)

    def _out_of_position_penalty(self, position: Position) -> float:
        """Multiplier in (0, 1] applied when playing out of position."""
        from .position import FORWARDS, BACKS

        same_unit = (
            (position in FORWARDS) == (self.natural_position in FORWARDS)
        )
        # Baseline unfamiliarity penalty: harsher crossing forward/back line.
        base_penalty = 0.90 if same_unit else 0.72

        versatility_bonus = (self.attributes.versatility - 50) / 100 * 0.25
        factor = base_penalty + versatility_bonus
        return max(0.4, min(1.0, factor))

    def sub_ratings(self, position: Position) -> dict:
        """Per-category contribution, used by the match engine."""
        attrs = self.attributes
        fit = self.rating_at(position) / 100
        return {
            "scrum": attrs.scrummaging * fit,
            "lineout": attrs.lineout_jumping * fit,
            "lineout_throw": attrs.lineout_throwing * fit,
            "tackling": attrs.tackling * fit,
            "attack": (attrs.pace + attrs.footwork + attrs.offload) / 3 * fit,
            "kicking": attrs.kicking_game * fit,
            "goal_kicking": attrs.goal_kicking * fit,
            "handling": attrs.handling * fit,
            "discipline": attrs.discipline,
            "aerial": attrs.aerial * fit,
        }

    def __repr__(self) -> str:
        era = f" '{self.era}" if self.era else ""
        return f"<Player {self.name}{era} ({self.nation}) nat={self.natural_position.value}>"
