import re

from rugby_sim.data.sources.team_colors import TEAM_COLORS
from rugby_sim.data.sources.union_registry import UNION_REGISTRY

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_every_real_union_has_a_well_formed_color():
    codes = {e.code for e in UNION_REGISTRY}
    missing = codes - set(TEAM_COLORS)
    assert not missing, f"missing team colors for: {missing}"
    for code, hexval in TEAM_COLORS.items():
        assert HEX_RE.match(hexval), f"{code}'s color {hexval!r} isn't a well-formed #RRGGBB hex"


def test_invitational_sides_covered_except_the_genuinely_inconsistent_one():
    # Barbarians/Lions have a real, documented color; the Pacific
    # Islanders don't (see team_colors.py's own docstring) - deliberately
    # absent rather than guessed.
    assert "BAR" in TEAM_COLORS and "LIO" in TEAM_COLORS
    assert "PAC" not in TEAM_COLORS
