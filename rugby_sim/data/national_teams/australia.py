"""2026-capped australia international player pool (via rugbydata)."""

from ._union_pool import lazy_pool

CODE = "AUS"

get_pool = lazy_pool("AUS")
