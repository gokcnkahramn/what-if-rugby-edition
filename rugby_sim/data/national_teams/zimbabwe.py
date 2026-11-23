"""Zimbabwe international pool - Wikipedia-only (no rugbydata team_id at
all for this union); needed for the 2027 Rugby World Cup draw (Pool F)."""

from __future__ import annotations

from ._union_pool import lazy_wikipedia_only_pool

CODE = "ZIM"
get_pool = lazy_wikipedia_only_pool("ZIM", "Zimbabwe")
