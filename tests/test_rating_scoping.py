from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.engine import MatchEngine
from rugby_sim.models import Lineup, Position, Team
from rugby_sim.models.position import CATEGORY_POSITION_GROUPS


def _team(name):
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = ENGLAND_SAMPLE[0]
    return Team(name=name, short_code=name[:3].upper(), lineup=lineup)


def test_scrum_rating_is_scoped_to_front_row_and_locks_not_whole_squad():
    team = _team("Home")
    scoped = team.lineup.team_sub_rating("scrum")

    naive_average = sum(
        slot.player.sub_ratings(slot.position).get("scrum", 50)
        for slot in team.lineup.starters.values()
    ) / len(team.lineup.starters)

    # The scoped and naive (all-15) averages should differ for a normal
    # XV, since backs barely contribute to a real scrum - if they were
    # equal it would mean scoping silently isn't doing anything.
    assert scoped != naive_average

    scrum_group = CATEGORY_POSITION_GROUPS["scrum"]
    expected = sum(
        slot.player.sub_ratings(slot.position).get("scrum", 50)
        for slot in team.lineup.starters.values()
        if slot.position in scrum_group
    ) / len(scrum_group)
    assert round(scoped, 4) == round(expected, 4)


def test_category_groups_only_reference_real_positions():
    for category, group in CATEGORY_POSITION_GROUPS.items():
        assert group, f"{category} has an empty position group"
        for position in group:
            assert isinstance(position, Position)


def test_lineout_turnovers_occur_across_a_season_of_matches():
    home, away = _team("Home"), _team("Away")
    saw_lineout_event = False
    for seed in range(15):
        result = MatchEngine(home, away, seed=seed).run()
        if any("lineout" in e.text.lower() for e in result.events):
            saw_lineout_event = True
            break
    assert saw_lineout_event, "lineout_jumping/lineout_throwing never influenced a single match in 15 tries"
