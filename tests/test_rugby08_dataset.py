"""Verification for `rugby08_dataset.py` - real, individual 2007 EA Sports
Rugby 08 player ratings sourced from the already-published
`marnoux/rugby08-player-explorer` GitHub dataset. Unit tests use a small,
hand-built fake dataset (monkeypatched in, matching that repo's own real
`players.json` record shape - confirmed live this session) rather than a
live network pull in the suite itself; `test_wikipedia_squad_rugby08_tier`
below separately confirms the wiring into `_cross_reference_attributes`
without needing network access either."""

from rugby_sim.data.sources import rugby08_dataset
from rugby_sim.models.position import Position

FAKE_RECORDS = [
    {
        "id": "00235", "name": "B.O'Driscoll", "star": 1, "nat": "Irish", "pos": ["Centre"],
        "h": [71, 180], "w": [199, 90],
        "r": [98, 82, 85, 93, 97, 96, 89, 78, 39, 82, 80, 77, 18, 3, 9, 90, 72, 92, 95, 91, 98, 79, 100],
        "ss": "0111000000000", "ir": 3, "t": [["ireland", 13]],
    },
    {
        # A second, DIFFERENT real player who happens to share the same
        # "initial + surname" key as a fictional collision case below.
        "id": "99999", "name": "B.Smith", "nat": "English", "pos": ["Wing"],
        "h": [70, 178], "w": [190, 86],
        "r": [60] * 23, "ss": "0" * 13, "ir": 0, "t": [],
    },
    {
        "id": "88888", "name": "B.Smith", "nat": "Welsh", "pos": ["Fly Half"],
        "h": [68, 173], "w": [180, 82],
        "r": [70] * 23, "ss": "0" * 13, "ir": 0, "t": [],
    },
]


def _fake_players_by_key():
    by_key = {}
    for rec in FAKE_RECORDS:
        by_key.setdefault(rec["name"].strip().lower(), []).append(rec)
    return by_key


def _patch_dataset(monkeypatch):
    monkeypatch.setattr(rugby08_dataset, "_PLAYERS_BY_KEY", _fake_players_by_key())
    monkeypatch.setattr(rugby08_dataset, "_load_players_by_key", lambda: rugby08_dataset._PLAYERS_BY_KEY)


def test_rugby08_key_builds_the_real_abbreviated_form():
    assert rugby08_dataset._rugby08_key("Brian O'Driscoll") == "b.o'driscoll"
    assert rugby08_dataset._rugby08_key("Denis Hickie") == "d.hickie"
    assert rugby08_dataset._rugby08_key("Madonna") is None  # no real surname to key off


def test_lookup_finds_a_real_player_by_name(monkeypatch):
    _patch_dataset(monkeypatch)
    rec = rugby08_dataset.lookup_rugby08_record("Brian O'Driscoll")
    assert rec is not None and rec["id"] == "00235"


def test_lookup_returns_none_for_a_name_not_in_the_dataset(monkeypatch):
    _patch_dataset(monkeypatch)
    assert rugby08_dataset.lookup_rugby08_record("Nobody Realname") is None


def test_lookup_disambiguates_a_real_name_collision_by_nationality(monkeypatch):
    _patch_dataset(monkeypatch)
    english = rugby08_dataset.lookup_rugby08_record("Bob Smith", nation="English")
    welsh = rugby08_dataset.lookup_rugby08_record("Bob Smith", nation="Welsh")
    assert english["id"] == "99999"
    assert welsh["id"] == "88888"
    # No nationality given: a documented, honest "first match wins" fallback.
    assert rugby08_dataset.lookup_rugby08_record("Bob Smith") in FAKE_RECORDS[1:]


def test_rugby08_attributes_overlays_real_ratings_on_the_archetype_baseline(monkeypatch):
    _patch_dataset(monkeypatch)
    attrs = rugby08_dataset.rugby08_attributes(Position.OUTSIDE_CENTRE, "Brian O'Driscoll", nation="Irish")
    assert attrs is not None
    # Real, mapped fields match the fake record's own raw ratings exactly.
    assert attrs.pace == 85       # "speed", index 2
    assert attrs.acceleration == 93
    assert attrs.fitness == 100
    assert attrs.discipline == 90
    assert attrs.scrummaging == 18
    # Unmapped fields (no honest 1:1 Rugby08 equivalent) stay at the
    # position's own archetype baseline, never a fabricated real-looking
    # number - confirmed by checking it's NOT one of the raw rating values
    # that would appear if this field had been (wrongly) overlaid.
    from rugby_sim.data.sources.wikipedia_squad import _archetype_attributes
    baseline = _archetype_attributes(Position.OUTSIDE_CENTRE)
    assert attrs.offload == baseline.offload
    assert attrs.positioning == baseline.positioning


def test_rugby08_attributes_returns_none_for_an_unknown_player(monkeypatch):
    _patch_dataset(monkeypatch)
    assert rugby08_dataset.rugby08_attributes(Position.FULLBACK, "Nobody Realname") is None


def test_cross_reference_attributes_reaches_the_rugby08_tier_when_position_is_given(monkeypatch):
    """Confirms the real wiring into `wikipedia_squad._cross_reference_attributes`
    - checked AFTER the hand-curated tiers but BEFORE the rugbydata
    registry, and only reachable when the caller passes `position`."""
    from rugby_sim.data.sources import wikipedia_squad
    _patch_dataset(monkeypatch)
    # Force the registry lookup to look "empty" so a false match there
    # can't accidentally mask a wiring bug.
    monkeypatch.setattr(wikipedia_squad, "fetch_player_registry", lambda: None)

    # "Bob Smith" (not a real curated Hall-of-Famer/EA-rated name) so this
    # test isolates the rugby08_dataset tier itself, not an earlier tier.
    attrs, source = wikipedia_squad._cross_reference_attributes(
        "Bob Smith", position=Position.LEFT_WING, nation="English",
    )
    assert source == "rugby08_dataset"
    assert attrs.fitness == 60

    # Omitting `position` (every pre-existing caller before this pass)
    # skips the tier entirely - behavior-preserving for anyone who hasn't
    # been updated to pass it.
    attrs2, source2 = wikipedia_squad._cross_reference_attributes("Bob Smith")
    assert source2 != "rugby08_dataset"
