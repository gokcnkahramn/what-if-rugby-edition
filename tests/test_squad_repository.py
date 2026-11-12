import json

from rugby_sim.data import ENGLAND_SAMPLE
from rugby_sim.data.squad_repository import load_team, save_team, team_from_dict, team_to_dict
from rugby_sim.models import Lineup, Team


def _team():
    lineup = Lineup()
    for p in ENGLAND_SAMPLE:
        lineup.set_starter(p.natural_position, p)
    lineup.captain = ENGLAND_SAMPLE[0]
    lineup.add_bench(ENGLAND_SAMPLE[1])
    return Team(name="England", short_code="ENG", lineup=lineup)


def test_round_trip_preserves_lineup_bench_and_captain():
    team = _team()
    data = team_to_dict(team)
    restored = team_from_dict(data)

    assert restored.name == team.name
    assert len(restored.lineup.starters) == len(team.lineup.starters)
    for position, slot in team.lineup.starters.items():
        assert restored.lineup.starters[position].player.name == slot.player.name
        assert restored.lineup.starters[position].player.attributes.as_dict() == slot.player.attributes.as_dict()
    assert restored.lineup.captain.name == team.lineup.captain.name
    assert [p.name for p in restored.lineup.bench] == [p.name for p in team.lineup.bench]
    assert restored.lineup.validate() == []


def test_save_and_load_file_round_trip(tmp_path):
    team = _team()
    path = tmp_path / "england.json"
    save_team(team, path)

    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["format_version"] == 1

    restored = load_team(path)
    assert restored.name == "England"
    assert restored.lineup.validate() == []


def test_shared_player_only_serialized_once():
    team = _team()
    data = team_to_dict(team)
    # ENGLAND_SAMPLE[1] is both a starter (its natural position) and on the
    # bench - should be stored once and referenced twice.
    assert len(data["players"]) == len(team.lineup.starters)
