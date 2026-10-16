"""Imported original rooms and explicit graphic-component transitions."""

import json
from pathlib import Path

DATA = json.loads(Path(__file__).with_name("rooms.json").read_text(encoding="utf-8"))
BY_KEY = {room["key"]: room for room in DATA["rooms"]}
BY_ID = {room["id"]: room for room in DATA["rooms"]}
BY_NAME = {
    alias.casefold(): room
    for room in DATA["rooms"]
    for alias in (room["key"], room["swf"], room["title"])
}
START_ROOM = BY_KEY["novograd"]


def resolve(value):
    if type(value) is int:
        return BY_ID.get(value)
    if isinstance(value, str):
        return BY_NAME.get(value.strip().casefold())
    return None


def exit_destination(room, token, x, y):
    if type(token) not in (int, str):
        return None
    for entry in room["exits"]:
        if entry["token"] != str(token) or not entry["target"]:
            continue
        left, right, top, bottom = entry["bounds"]
        # The final movement variable and trigger can be adjacent packets.
        # Allow that short walk, but reject a forged exit across the room.
        if left - 80 <= x <= right + 80 and top - 80 <= y <= bottom + 80:
            return resolve(entry["target"])
    return None
