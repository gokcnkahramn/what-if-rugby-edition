"""2026-capped new zealand international player pool (via rugbydata)."""

from ._union_pool import lazy_pool

CODE = "NZL"

get_pool = lazy_pool("NZL")
