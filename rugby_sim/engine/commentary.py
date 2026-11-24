from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CommentaryEvent:
    minute: int
    team: str
    text: str
    score_home: int
    score_away: int
    # Which zone the ball was in when this event happened - "home_tryline"/
    # "home_22"/"midfield"/"away_22"/"away_tryline" (see `match_engine.Zone`)
    # - real, simulated-state-derived, not fabricated after the fact.
    # `None` only for a `CommentaryEvent` built before the zone model
    # existed (there are none left in this codebase) or by some future
    # caller that genuinely doesn't track it.
    zone: Optional[str] = None
    # Which side of the pitch play was notionally on - "left"/"middle"/
    # "right" (see `match_engine.Side`) - same real, derived-not-fabricated
    # convention as `zone`. Used by the frontend's pitch-diagram
    # visualization to place wingers plausibly.
    side: Optional[str] = None

    def __str__(self) -> str:
        return f"[{self.minute:>2}'] {self.text}  ({self.score_home}-{self.score_away})"
