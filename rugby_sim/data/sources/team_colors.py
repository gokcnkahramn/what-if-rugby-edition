"""Real primary home-jersey color per union/invitational side, for the
pitch-diagram visualization (player dots colored like the real team's
actual jersey, rather than a generic home/away color - see `app.js`'s
`teamColorFor`/`playerDotMarkup`). Same "curated, real, committed to the
repo" convention as `venues.py`/`legends.py`.

Researched live (WebSearch), not recalled from memory, for every entry -
most are well-documented/iconic and high-confidence; a handful of smaller
unions (flagged below) had thin or inconsistent sourcing and are included
as a reasonable best-effort single representative color, not a precisely
verified official spec. Sourced colors are never substituted for
"visibility" - a team whose real jersey is white or another pale color is
still given that real color; the frontend picks readable text/outline
contrast separately (see `readableTextColor` in app.js), it never
overrides the real color choice.

Deliberately NOT included: the Pacific Islanders (2004-2008) - researched
and found to have genuinely inconsistent kit colors across their short
history (2004 tour: red/white/blue; no confirmed 2008 kit details at
all), so there's no honest single "team color" to assign - falls back to
the frontend's generic invitational color instead of a guessed one.
"""

from __future__ import annotations

#: Union code -> real primary home jersey hex color. Keys match
#: `union_registry.UNION_REGISTRY`'s codes, plus "BAR"/"LIO" (the
#: Barbarians/British & Irish Lions - see `national_teams/barbarians.py`/
#: `lions.py`).
TEAM_COLORS = {
    "ENG": "#FFFFFF",
    "FRA": "#002654",
    "IRE": "#169B62",
    "SCO": "#00205B",
    "WAL": "#D30731",
    "ITA": "#0B4EA2",
    "NZL": "#000000",
    "AUS": "#FFC20E",
    "RSA": "#007A4D",
    "ARG": "#75AADB",
    "JPN": "#BC002D",
    "FIJ": "#FFFFFF",
    "GEO": "#7B1113",
    "ROU": "#FFD700",
    "ESP": "#C60C30",
    "POR": "#C8102E",
    "SAM": "#002147",
    "TGA": "#C8102E",
    "USA": "#FFFFFF",
    "CAN": "#E8112D",
    "URU": "#75AADB",
    "CHI": "#D52B1E",
    "NAM": "#002F6C",
    # Lower-confidence tier below (thin/inconsistent sourcing for these
    # smaller unions - see module docstring) - still real-researched best
    # guesses, not fabricated, but worth a spot-check against current kit
    # photos if ever in doubt.
    "SUI": "#FF0000",
    "GER": "#000000",
    "POL": "#FFFFFF",
    "NED": "#FF6600",
    "BEL": "#000000",
    "RUS": "#DA291C",
    "HKG": "#ED1C24",
    "ZIM": "#006400",
    # Invitational sides (not World Rugby unions - see
    # `union_registry.py`'s own docstring for why these aren't in
    # `UNION_REGISTRY`).
    "BAR": "#000000",  # Barbarians - real black-and-white hooped jersey; black picked as representative
    "LIO": "#C8102E",  # British & Irish Lions - iconic red jersey
}
