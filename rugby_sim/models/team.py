from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .player import Player
from .position import CATEGORY_POSITION_GROUPS, Position, JERSEY_NUMBER


@dataclass
class SquadSlot:
    """One shirt in the matchday 23: a position mapped to the player chosen
    for it. This is where the user builds the 'what if' lineup."""
    position: Position
    player: Player

    @property
    def jersey(self) -> int:
        return JERSEY_NUMBER.get(self.position, 0)

    @property
    def fit_rating(self) -> float:
        return self.player.rating_at(self.position)

    def __repr__(self) -> str:
        return f"#{self.jersey} {self.position.value}: {self.player.name} (fit {self.fit_rating})"


@dataclass
class Lineup:
    """A full matchday squad: 15 starters + up to 8 replacements (6-2 or 5-3
    splits are both fine, bench slots don't need a fixed position)."""
    starters: Dict[Position, SquadSlot] = field(default_factory=dict)
    bench: List[Player] = field(default_factory=list)
    captain: Optional[Player] = None

    def set_starter(self, position: Position, player: Player) -> None:
        self.starters[position] = SquadSlot(position=position, player=player)

    def add_bench(self, player: Player) -> None:
        if len(self.bench) >= 8:
            raise ValueError("Bench is already full (8 replacements max).")
        self.bench.append(player)

    def validate(self) -> List[str]:
        """Return a list of problems (empty = fully legal matchday squad)."""
        problems = []
        missing = [p for p in Position if p not in self.starters]
        if missing:
            problems.append(
                "Missing starters for: " + ", ".join(p.value for p in missing)
            )
        seen_players = {}
        for slot in self.starters.values():
            seen_players.setdefault(slot.player.name, []).append(slot.position.value)
        for name, positions in seen_players.items():
            if len(positions) > 1:
                problems.append(f"{name} is named in multiple positions: {positions}")
        if self.captain is None:
            problems.append("No captain assigned.")
        return problems

    def team_sub_rating(self, category: str) -> float:
        """Average of a given sub-rating across the starting XV (0-100) -
        or, for a category in `CATEGORY_POSITION_GROUPS` (scrum, lineout,
        lineout_throw, aerial, kicking), only across the starters actually
        involved in that phase of play (e.g. "scrum" averages the front
        row + locks, not all 15 - a strong front five no longer gets
        diluted by two wingers who barely scrummage)."""
        group = CATEGORY_POSITION_GROUPS.get(category)
        slots = (
            [s for s in self.starters.values() if s.position in group]
            if group else list(self.starters.values())
        )
        if not slots:
            slots = list(self.starters.values())
        values = [slot.player.sub_ratings(slot.position).get(category, 50) for slot in slots]
        return sum(values) / len(values) if values else 50.0

    def pretty_print(self) -> str:
        lines = []
        for pos in Position:
            slot = self.starters.get(pos)
            if slot:
                lines.append(repr(slot))
            else:
                lines.append(f"#{JERSEY_NUMBER[pos]} {pos.value}: -- EMPTY --")
        if self.bench:
            lines.append("Bench: " + ", ".join(p.name for p in self.bench))
        if self.captain:
            lines.append(f"Captain: {self.captain.name}")
        return "\n".join(lines)


@dataclass
class Team:
    name: str
    short_code: str
    lineup: Lineup = field(default_factory=Lineup)
    kit_colors: str = ""

    def __repr__(self) -> str:
        return f"<Team {self.name} ({self.short_code})>"
