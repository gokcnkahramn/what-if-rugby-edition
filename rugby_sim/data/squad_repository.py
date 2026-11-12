"""Save/load a drafted `Team` (lineup + bench + captain) to a plain JSON
file - so a squad you spent time drafting in the interactive CLI or web UI
doesn't have to be rebuilt from scratch next time, and can be shared as a
file independent of this machine's network/data cache.

The whole `Player` (attributes, nation, era, notes, data_source) is
serialized inline, not just a reference into a pool - so a loaded squad
works completely offline, even for a player who came from a live Wikipedia/
rugbydata pull or a specific historical season that isn't cached anymore.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from ..models.attributes import Attributes
from ..models.player import Player
from ..models.position import Position
from ..models.team import Lineup, Team

FORMAT_VERSION = 1


def _player_to_dict(player: Player) -> dict:
    return {
        "name": player.name,
        "nation": player.nation,
        "natural_position": player.natural_position.value,
        "attributes": player.attributes.as_dict(),
        "era": player.era,
        "notes": player.notes,
        "data_source": player.data_source,
    }


def _player_from_dict(data: dict) -> Player:
    return Player(
        name=data["name"],
        nation=data["nation"],
        natural_position=Position(data["natural_position"]),
        attributes=Attributes.from_dict(data["attributes"]),
        era=data.get("era"),
        notes=data.get("notes", ""),
        data_source=data.get("data_source", "manual"),
    )


def team_to_dict(team: Team) -> dict:
    """Builds the JSON-ready structure for one `Team`. Players are
    deduplicated by identity so a bench player who's also referenced
    elsewhere isn't written out twice."""
    players: list = []
    index_by_identity: dict = {}

    def player_index(player: Player) -> int:
        key = id(player)
        if key not in index_by_identity:
            index_by_identity[key] = len(players)
            players.append(_player_to_dict(player))
        return index_by_identity[key]

    starters = {
        position.value: player_index(slot.player)
        for position, slot in team.lineup.starters.items()
    }
    bench = [player_index(p) for p in team.lineup.bench]
    captain = player_index(team.lineup.captain) if team.lineup.captain else None

    return {
        "format_version": FORMAT_VERSION,
        "name": team.name,
        "short_code": team.short_code,
        "players": players,
        "starters": starters,
        "bench": bench,
        "captain": captain,
    }


def team_from_dict(data: dict) -> Team:
    players = [_player_from_dict(p) for p in data["players"]]

    lineup = Lineup()
    for pos_value, idx in data["starters"].items():
        lineup.set_starter(Position(pos_value), players[idx])
    for idx in data.get("bench", []):
        lineup.add_bench(players[idx])
    if data.get("captain") is not None:
        lineup.captain = players[data["captain"]]

    return Team(name=data["name"], short_code=data.get("short_code", data["name"][:3].upper()), lineup=lineup)


def save_team(team: Team, path: Union[str, Path]) -> None:
    Path(path).write_text(json.dumps(team_to_dict(team), indent=2, ensure_ascii=False), encoding="utf-8")


def load_team(path: Union[str, Path]) -> Team:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return team_from_dict(data)
