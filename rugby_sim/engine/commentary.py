from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CommentaryEvent:
    minute: int
    team: str
    text: str
    score_home: int
    score_away: int

    def __str__(self) -> str:
        return f"[{self.minute:>2}'] {self.text}  ({self.score_home}-{self.score_away})"
