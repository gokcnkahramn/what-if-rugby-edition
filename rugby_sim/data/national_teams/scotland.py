"""2026-capped scotland international player pool (via rugbydata)."""

from ._union_pool import lazy_pool

CODE = "SCO"

get_pool = lazy_pool("SCO")
