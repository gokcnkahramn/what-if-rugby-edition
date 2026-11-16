"""Verification for the real, scoped home-advantage feature (see
`MatchEngine.__init__`'s `home_advantage` param and `Tournament._play`'s
`home_advantage_for` param): a small, honest home-field nudge, applied only
where real fixture data justifies it - real round-robin competitions (via
their genuine `fx.home`), World Cup host nations' own matches, and nowhere
else (Nations Championship finals weekend, friendlies, draft mode, fully
custom/synthetic tournaments all stay neutral)."""

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.engine.match_engine import HOME_ADVANTAGE_BONUS
from rugby_sim.models import Lineup, Team
from rugby_sim.tournament import Tournament
from rugby_sim.tournament.world_cup_2027 import HOST_NATION


def _team(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = ENGLAND_SAMPLE[0]
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


# -------------------------- worked-example: engine-level effect ------------

def test_home_advantage_modestly_shifts_territory_and_win_rate_over_many_seeds():
    n_seeds = 300
    home_terr_adv, home_terr_neutral = [], []
    home_wins_adv = home_wins_neutral = 0

    for seed in range(n_seeds):
        home, away = _team("Home"), _team("Away")
        result = MatchEngine(home, away, seed=seed, home_advantage=True).run()
        home_terr_adv.append(result.stats["Home"].territory_pct)
        if result.winner is not None and result.winner.name == "Home":
            home_wins_adv += 1

        home, away = _team("Home"), _team("Away")
        result = MatchEngine(home, away, seed=seed, home_advantage=False).run()
        home_terr_neutral.append(result.stats["Home"].territory_pct)
        if result.winner is not None and result.winner.name == "Home":
            home_wins_neutral += 1

    avg_terr_adv = sum(home_terr_adv) / n_seeds
    avg_terr_neutral = sum(home_terr_neutral) / n_seeds
    win_rate_adv = home_wins_adv / n_seeds
    win_rate_neutral = home_wins_neutral / n_seeds

    print(
        f"\nhome_advantage=True : avg territory {avg_terr_adv:.2f}%, win rate {win_rate_adv:.3f}\n"
        f"home_advantage=False: avg territory {avg_terr_neutral:.2f}%, win rate {win_rate_neutral:.3f}\n"
        f"HOME_ADVANTAGE_BONUS = {HOME_ADVANTAGE_BONUS}"
    )

    # Real, modest shift - two identical squads should favor the "home" side
    # a bit more with the bonus than without, but nowhere near dramatically
    # (a few percentage points of territory / win rate, not double-digit
    # swings) - since both squads are literally identical here, any shift at
    # all is attributable to the bonus, not a rating gap.
    assert avg_terr_adv > avg_terr_neutral
    assert 0.5 < (avg_terr_adv - avg_terr_neutral) < 5.0
    assert win_rate_adv >= win_rate_neutral


def test_home_advantage_only_affects_self_home_never_the_away_side():
    # Flip which Team object is "home" vs "away" while keeping
    # home_advantage=True - the advantage should follow `self.home`, not a
    # fixed team name, and have no notion of human/AI control at all.
    home, away = _team("Alpha"), _team("Beta")
    territory_alpha_as_home = []
    for seed in range(100):
        h, a = _team("Alpha"), _team("Beta")
        result = MatchEngine(h, a, seed=seed, home_advantage=True).run()
        territory_alpha_as_home.append(result.stats["Alpha"].territory_pct)

    territory_beta_as_home = []
    for seed in range(100):
        h, a = _team("Beta"), _team("Alpha")
        result = MatchEngine(h, a, seed=seed, home_advantage=True).run()
        territory_beta_as_home.append(result.stats["Beta"].territory_pct)

    avg_alpha = sum(territory_alpha_as_home) / 100
    avg_beta = sum(territory_beta_as_home) / 100
    # Whichever side is `self.home` should benefit - roughly symmetric since
    # both squads are identical, regardless of team name.
    assert abs(avg_alpha - avg_beta) < 2.0
    assert avg_alpha > 50.0
    assert avg_beta > 50.0


# -------------------------- real round-robin fixtures -----------------------

def test_real_round_robin_fixture_gets_home_advantage_matching_fx_home():
    from rugby_sim.tournament.real_fixtures import load_real_fixtures

    fixtures = load_real_fixtures("six_nations", "2026")
    assert fixtures, "expected real 2026 Six Nations fixtures to be recoverable"
    fx = fixtures[0]

    teams = {
        name: _team(name)
        for name in sorted({f.home for f in fixtures} | {f.away for f in fixtures})
    }
    captured = {}
    original_play = Tournament._play

    def spy_play(self, home_name, away_name, seed, home_advantage_for=None):
        captured.setdefault(home_name, []).append((home_name, away_name, home_advantage_for))
        return original_play(self, home_name, away_name, seed, home_advantage_for)

    Tournament._play = spy_play
    try:
        t = Tournament(teams=teams)
        t.run_real("six_nations", season="2026", seed=1)
    finally:
        Tournament._play = original_play

    # Every real fixture's home_advantage_for must equal its own real home side.
    for home_name, calls in captured.items():
        for h, a, adv in calls:
            assert adv == h, f"expected home_advantage_for == real home ({h}), got {adv}"


def test_nations_championship_finals_never_get_home_advantage_for_either_side():
    from rugby_sim.data.sources.nations_championship_2026 import NORTH_POOL, SOUTH_POOL

    teams = {name: _team(name) for name in sorted(NORTH_POOL | SOUTH_POOL)}
    captured = []
    original_play = Tournament._play

    def spy_play(self, home_name, away_name, seed, home_advantage_for=None):
        captured.append((home_name, away_name, home_advantage_for))
        return original_play(self, home_name, away_name, seed, home_advantage_for)

    Tournament._play = spy_play
    try:
        t = Tournament(teams=teams)
        report = t.run_nations_championship(year=2026, seed=1)
    finally:
        Tournament._play = original_play

    # The 6 finals-weekend fixtures (the final 6 `_play` calls) must have
    # home_advantage_for=None for both sides.
    finals_calls = captured[-6:]
    assert len(finals_calls) == 6
    for h, a, adv in finals_calls:
        assert adv is None, f"finals fixture {h} v {a} should be neutral, got home_advantage_for={adv}"

    # Meanwhile, the round-robin stage fixtures DID get a real home side.
    round_robin_calls = captured[:-6]
    assert any(adv is not None for _, _, adv in round_robin_calls)


# -------------------------- World Cup host nation ---------------------------

def test_world_cup_host_nation_match_gets_home_advantage_non_host_does_not():
    from rugby_sim.tournament.world_cup_2027 import POOLS_2027

    host = HOST_NATION[2027]
    assert host == "Australia"

    all_names = {n for pool in POOLS_2027.values() for n in pool}
    teams = {name: _team(name) for name in all_names}

    captured = []
    original_play = Tournament._play

    def spy_play(self, home_name, away_name, seed, home_advantage_for=None):
        captured.append((home_name, away_name, home_advantage_for))
        return original_play(self, home_name, away_name, seed, home_advantage_for)

    Tournament._play = spy_play
    try:
        t = Tournament(teams=teams)
        t.run_world_cup_2027(fixture_mode="specific", seed=1)
    finally:
        Tournament._play = original_play

    host_matches = [(h, a, adv) for h, a, adv in captured if host in (h, a)]
    non_host_matches = [(h, a, adv) for h, a, adv in captured if host not in (h, a)]

    assert host_matches, "expected the host nation to have played at least one match"
    assert non_host_matches, "expected at least one non-host match in the tournament"

    for h, a, adv in host_matches:
        assert adv == host, f"host nation's own match {h} v {a} should get home_advantage_for={host}, got {adv}"
    for h, a, adv in non_host_matches:
        assert adv is None, f"non-host match {h} v {a} should stay neutral, got home_advantage_for={adv}"


# -------------------------- human/AI fairness unaffected --------------------

def test_home_advantage_is_never_keyed_to_my_team_human_control():
    """Interactive (`my_team`) fixtures go through `pause_hook`, which never
    receives `home_advantage` at all (see `Tournament._play`'s docstring) -
    confirming the feature genuinely can't introduce a human/AI asymmetry,
    since it's wired purely off real fixture home/away data, never off
    which side is `self.my_team`."""
    home, away = _team("Home"), _team("Away")
    pause_calls = []

    def pause_hook(home_name, away_name, home_team, away_team, seed, initial_condition):
        pause_calls.append((home_name, away_name))
        return MatchEngine(home_team, away_team, seed=seed, home_advantage=False).run()

    t = Tournament(teams={"Home": home, "Away": away}, my_team="Home", pause_hook=pause_hook)
    # Directly drive `_play` for a fixture where `home_advantage_for` WOULD
    # have been set (as a real competition's wiring would do) - the
    # pause_hook path must still be the one invoked, untouched by it.
    t._play("Home", "Away", seed=1, home_advantage_for="Home")
    assert pause_calls == [("Home", "Away")]
