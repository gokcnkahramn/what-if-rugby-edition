"""2026-capped italy international player pool (via rugbydata)."""

from ._union_pool import lazy_pool

CODE = "ITA"

get_pool = lazy_pool("ITA")
