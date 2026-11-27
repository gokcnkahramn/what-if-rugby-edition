"""Verification for `scripts/refresh_cache.py` - the data-freshness tool
that force-refreshes a union's real rugbydata/Wikipedia caches on disk.
Pure logic/wiring tests (cache-path deletion, unknown-code handling), not a
live network re-pull in the test suite itself (that's already exercised by
every other test that calls `build_union_pool` for real)."""

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "refresh_cache.py"
_spec = importlib.util.spec_from_file_location("refresh_cache", SCRIPT_PATH)
refresh_cache = importlib.util.module_from_spec(_spec)
sys.modules["refresh_cache"] = refresh_cache
_spec.loader.exec_module(refresh_cache)

from rugby_sim.data.sources.pool_builder import ALL_TEAM_IDS


def test_delete_team_cache_handles_a_missing_file_gracefully():
    assert refresh_cache._delete_team_cache("not-a-real-team-id") is False


def test_delete_wiki_cache_handles_a_missing_page_gracefully():
    assert refresh_cache._delete_wiki_cache("Not A Real Wikipedia Page Title XYZ") is False


def test_refresh_union_reports_an_unknown_code_without_crashing(capsys):
    refresh_cache.refresh_union("ZZZ_NOT_REAL", "2026")
    out = capsys.readouterr().out
    assert "unknown union code" in out


def test_every_tier1_union_code_is_a_real_known_entry():
    # Spot-check the lookup table this script relies on is still real and
    # populated, not a silent regression in `pool_builder`'s own registry.
    assert "ENG" in ALL_TEAM_IDS
    assert "NZL" in ALL_TEAM_IDS
