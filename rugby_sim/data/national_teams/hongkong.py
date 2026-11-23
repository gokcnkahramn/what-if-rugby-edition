"""Hong Kong international pool - Wikipedia-only (no rugbydata team_id at
all for this union); needed for the 2027 Rugby World Cup draw (Pool A)."""

from __future__ import annotations

from ._union_pool import lazy_wikipedia_only_pool

CODE = "HKG"
get_pool = lazy_wikipedia_only_pool("HKG", "Hong Kong")
