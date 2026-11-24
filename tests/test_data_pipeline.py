from rugby_sim.data import LEGENDS, POOLS
from rugby_sim.data.national_teams.barbarians import get_pool as barbarians_pool
from rugby_sim.data.national_teams.wales import get_pool as wales_pool
from rugby_sim.data.sources.attribute_mapping import map_stats_to_attributes
from rugby_sim.data.sources.position_mapping import map_raw_position
from rugby_sim.models.position import Position

TIER2_CODES = ["GEO", "ROU", "ESP", "POR", "SAM", "TGA", "USA", "CAN", "URU", "CHI", "NAM"]


def assert_duplicates_are_only_real_twin_position_pairs(pool, label=""):
    """A Wikipedia/historical-sourced pool deliberately contains a second
    `Player` entry (same name) for anyone mapped to one of
    `wikipedia_squad.TWIN_POSITION`'s 5 "primary" positions (loosehead
    prop/lock/left wing/inside centre/blindside flanker) - these real
    players are genuine candidates for the "twin" slot too (tighthead
    prop/lock/right wing/outside centre/openside flanker), since the real
    data source this pool came from can't distinguish which of the two a
    given real person actually played (see `with_twin_position_duplicates`'s
    own module-level comment for the full rationale). This is a real,
    intentional exception to "no duplicate names" - this helper confirms
    every duplicate name in `pool` is EXACTLY this kind (never more than 2
    occurrences, and always a genuine twin-position pair), not some other,
    unintended duplication slipping through."""
    from rugby_sim.data.sources.wikipedia_squad import TWIN_POSITION

    seen = {}
    for p in pool:
        seen.setdefault(p.name, []).append(p.natural_position)
    for name, positions in seen.items():
        if len(positions) == 1:
            continue
        assert len(positions) == 2, f"{label}{name} appears {len(positions)} times: {positions}"
        a, b = positions
        assert TWIN_POSITION.get(a) == b or TWIN_POSITION.get(b) == a, (
            f"{label}{name} duplicated at non-twin positions {positions}"
        )


def test_tier2_pools_are_all_populated():
    # Each Tier 2 union (2027 Rugby World Cup picture) must resolve a usable,
    # full-size 2026 pool via the rugbydata+Wikipedia merge. A name CAN now
    # legitimately appear twice (a real twin-position duplicate - see
    # `assert_duplicates_are_only_real_twin_position_pairs`), but never for
    # any other reason (regression: Portugal's Wikipedia squad listing
    # genuinely repeats a few utility players once per position group they
    # cover - parse_current_squad must dedupe that, not pool_builder).
    for code in TIER2_CODES:
        pool = POOLS[code]()
        assert len(pool) >= 20, f"{code} returned a suspiciously small pool ({len(pool)})"
        assert_duplicates_are_only_real_twin_position_pairs(pool, label=f"{code}: ")
        assert all(p.era == "'26" for p in pool), f"{code} pool isn't all tagged 2026"


def test_wikipedia_squad_parse_dedupes_repeated_entries():
    from rugby_sim.data.sources.wikipedia_squad import parse_current_squad

    wikitext = """
==Players==
===Current squad===
{{nat rs player|pos=LK|name={{sortname|Alex|Example}}|age=1|caps=5|club=X}}
{{nat rs player|pos=FL|name={{sortname|Alex|Example}}|age=1|caps=5|club=X}}
{{nat rs player|pos=HK|name={{sortname|Sam|Other}}|age=1|caps=2|club=Y}}
==Coaches==
"""
    entries = parse_current_squad(wikitext)
    names = [f"{e['first']} {e['last']}" for e in entries]
    assert names == ["Alex Example", "Sam Other"]


def test_union_pool_has_no_duplicate_player_names():
    # Regression test: rugbydata occasionally tracks the same real person
    # under two different player_ids (confirmed for Wales's Ellis Mee -
    # 6 caps under one id, 1 under another). build_union_pool must collapse
    # these to a single entry (keeping the one with more caps) so a drafted
    # lineup can never end up with "the same player" in two slots.
    pool = wales_pool(season="2026")
    names = [p.name for p in pool]
    assert len(names) == len(set(names))


def test_legends_are_plentiful_and_not_in_any_nation_pool():
    assert len(LEGENDS) >= 20
    assert all(p.data_source == "manual" for p in LEGENDS)
    assert all(p.era for p in LEGENDS)  # every legend must be dated
    names = [p.name for p in LEGENDS]
    assert len(names) == len(set(names))
    # Legends must never leak into a real union's own pool.
    assert "LEG" not in POOLS
    legend_names = set(names)
    nzl_names = {p.name for p in POOLS["NZL"]()}
    assert not (legend_names & nzl_names)


def test_full_hof_roster_covers_most_of_the_wikipedia_category():
    from rugby_sim.data.legends import CURATED_LEGENDS, get_all_legends

    all_legends = get_all_legends()
    # The HoF category has 190 members; many are teams/tours/administrators/
    # commentators with no playing infobox (filtered out automatically), or
    # have a career too old/sparse to parse a position+nation from. ~95 real
    # extra players on top of the curated 32 is the actual, verified yield.
    assert len(all_legends) >= len(CURATED_LEGENDS) + 60
    names = [p.name for p in all_legends]
    assert len(names) == len(set(names))
    assert all(p.era for p in all_legends)
    assert all(p.data_source in ("manual", "hof_archetype") for p in all_legends)
    # A curated (hand-tuned) entry must win over its scraped counterpart.
    lomu = next(p for p in all_legends if p.name == "Jonah Lomu")
    assert lomu.data_source == "manual"


def test_barbarians_pool_is_manual_and_populated():
    pool = barbarians_pool()
    assert len(pool) >= 8
    assert all(p.data_source == "manual" for p in pool)
    assert all(p.era == "'26" for p in pool)


def test_barbarians_pool_covers_every_position():
    # A real matchday-23 squad must have at least one real option per
    # position, or a lineup can't actually be built/validated.
    pool = barbarians_pool()
    covered = {p.natural_position for p in pool}
    missing = [pos for pos in Position if pos not in covered]
    assert not missing, f"Barbarians pool is missing: {missing}"
    names = [p.name for p in pool]
    assert len(names) == len(set(names))


def test_position_mapping_known_values():
    assert map_raw_position("number_eight") == Position.NUMBER_8
    assert map_raw_position("openside_flanker") == Position.OPENSIDE_FLANKER
    assert map_raw_position("back_sub") is None
    assert map_raw_position(None) is None


def test_attribute_mapping_percentile_scaling_uses_peer_context():
    from rugby_sim.data.sources.attribute_mapping import build_peer_proxies, map_stats_to_attributes

    weak_stats = {"tackles_made": 20, "tackles_missed": 10}
    strong_stats = {"tackles_made": 50, "tackles_missed": 2}
    mid_stats = {"tackles_made": 35, "tackles_missed": 6}

    peers = build_peer_proxies([(weak_stats, 5), (strong_stats, 5), (mid_stats, 5)])

    without_peers = map_stats_to_attributes(mid_stats, caps=5).tackling
    with_peers = map_stats_to_attributes(mid_stats, caps=5, peer_proxies=peers).tackling

    # With fewer than MIN_PEER_SAMPLE peers it must fall back to the fixed
    # breakpoints (same result as calling with no peer_proxies at all).
    tiny_peer_set = build_peer_proxies([(mid_stats, 5)])
    assert map_stats_to_attributes(mid_stats, caps=5, peer_proxies=tiny_peer_set).tackling == without_peers

    # The weakest tackler in a 3-player pool should rank at/near the bottom
    # once there ARE enough peers to percentile-rank against (pad to 5).
    padded_peers = build_peer_proxies([
        (weak_stats, 5), (strong_stats, 5), (mid_stats, 5), (mid_stats, 5), (strong_stats, 5),
    ])
    weakest_rating = map_stats_to_attributes(weak_stats, caps=5, peer_proxies=padded_peers).tackling
    strongest_rating = map_stats_to_attributes(strong_stats, caps=5, peer_proxies=padded_peers).tackling
    assert weakest_rating < strongest_rating


def test_attribute_mapping_stays_in_range():
    stats = {
        "tackles_made": 50, "tackles_missed": 5, "dominant_tackles": 10,
        "carries": 20, "metres_carried": 120, "line_breaks": 3,
        "clean_breaks": 2, "defenders_beaten": 8, "offloads": 4,
        "passes": 60, "turnovers_lost": 2, "kicks_from_hand": 10,
        "kick_percent_success": 0.8, "penalty_goals": 3, "conversion_goals": 5,
        "lineouts_won": 5, "total_lineouts": 12, "rucks_won": 20,
        "turnovers_won": 3, "penalties_conceded": 1, "yellow_cards": 0,
        "red_cards": 0,
    }
    attrs = map_stats_to_attributes(stats, caps=5)
    for value in attrs.as_dict().values():
        assert 1 <= value <= 100
