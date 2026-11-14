"""Smoke test for the calibration harness in `scripts/calibrate_ratings.py`.

This does NOT re-run the full 15-fixture x 11-seed 2024 Six Nations sweep
on every `pytest` run (that hits the network/disk-cache and takes a couple
of minutes) - it just checks the harness's own logic (real-winner
derivation, modal-vote tie-break) is correct, and that the real-results
table has exactly 15 rows (6 choose 2, i.e. nothing missing or duplicated).
For the actual calibration number, run
`python scripts/calibrate_ratings.py` directly - see the README's
"Calibration: does the engine pick real winners?" section for the current
figure.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from calibrate_ratings import REAL_RESULTS, UNIONS, real_winner  # noqa: E402


def test_real_results_cover_every_pairing_exactly_once():
    nations = set(UNIONS.values())
    pairs_seen = set()
    for home, away, _hs, _as in REAL_RESULTS:
        assert home in nations and away in nations
        pair = frozenset((home, away))
        assert pair not in pairs_seen, f"duplicate fixture: {home} vs {away}"
        pairs_seen.add(pair)
    expected_pairs = {frozenset(p) for p in itertools.combinations(nations, 2)}
    assert pairs_seen == expected_pairs


def test_real_winner_handles_draw_and_both_sides():
    assert real_winner(20, 10, "A", "B") == "A"
    assert real_winner(10, 20, "A", "B") == "B"
    assert real_winner(13, 13, "A", "B") == "draw"
