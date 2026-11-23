"""2026-capped ireland international player pool (via rugbydata)."""

from ._union_pool import lazy_pool

CODE = "IRE"

get_pool = lazy_pool("IRE")
