"""2026-capped south africa international player pool (via rugbydata)."""

from ._union_pool import lazy_pool

CODE = "RSA"

get_pool = lazy_pool("RSA")
