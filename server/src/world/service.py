"""Transient room state. Coordinates are never written to the account database."""

from dataclasses import dataclass

from src.world import catalog, spawning
from src.world.navigation import path_to, room_data


@dataclass
class Player:
    x: float
    y: float
    room_id: int


def enter(room=None, *, arrival_from=None, occupied=()) -> Player:
    data = room_data(room or catalog.START_ROOM["key"])
    x, y = spawning.choose(data, arrival_from, occupied)
    return Player(x=x, y=y, room_id=data["id"])


def move(player: Player, target: tuple[float, float]) -> tuple[float, float]:
    room = catalog.BY_ID[player.room_id]["key"]
    try:
        x, y = path_to(room, (player.x, player.y), target)[-1]
    except ValueError:
        # A click in another disconnected walking area must not disconnect
        # the player. The original client still handles its area entrances.
        return player.x, player.y
    player.x, player.y = x, y
    return x, y
