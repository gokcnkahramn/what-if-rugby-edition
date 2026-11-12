"""Maps the dataset's raw `position` strings onto our `Position` enum.

The dataset doesn't distinguish Lock 4 vs Lock 5, or which wing/centre slot,
so those pairs fall back to a single representative value - good enough to
seed a pool entry's *natural* position; the user can still start them on
either side, and `Player.rating_at` treats same-unit swaps leniently.
"""

from __future__ import annotations

from typing import Optional

from ...models.position import Position

RAW_POSITION_MAP = {
    "loosehead_prop": Position.LOOSEHEAD_PROP,
    "prop": Position.LOOSEHEAD_PROP,
    "hooker": Position.HOOKER,
    "tighthead_prop": Position.TIGHTHEAD_PROP,
    "lock": Position.LOCK_1,
    "second_row": Position.LOCK_1,
    "blindside_flanker": Position.BLINDSIDE_FLANKER,
    "flanker": Position.OPENSIDE_FLANKER,
    "openside_flanker": Position.OPENSIDE_FLANKER,
    "number_eight": Position.NUMBER_8,
    "number_8": Position.NUMBER_8,
    "scrum_half": Position.SCRUM_HALF,
    "scrumhalf": Position.SCRUM_HALF,
    "fly_half": Position.FLY_HALF,
    "flyhalf": Position.FLY_HALF,
    "outside_half": Position.FLY_HALF,
    "wing": Position.LEFT_WING,
    "winger": Position.LEFT_WING,
    "left_wing": Position.LEFT_WING,
    "right_wing": Position.RIGHT_WING,
    "centre": Position.INSIDE_CENTRE,
    "center": Position.INSIDE_CENTRE,
    "inside_centre": Position.INSIDE_CENTRE,
    "outside_centre": Position.OUTSIDE_CENTRE,
    "fullback": Position.FULLBACK,
    "full_back": Position.FULLBACK,
}

# Ambiguous "substitute" rows the dataset uses when it can't tell which
# position a bench player came on in - never used as a *natural* position.
AMBIGUOUS_SUB_LABELS = {"back_sub", "forward_sub", "sub", "substitute"}


def map_raw_position(raw: Optional[str]) -> Optional[Position]:
    if not raw:
        return None
    key = str(raw).strip().lower()
    if key in AMBIGUOUS_SUB_LABELS:
        return None
    return RAW_POSITION_MAP.get(key)
