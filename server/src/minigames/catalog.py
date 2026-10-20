"""Confirmed original mini-game resources and local reward policy."""

GAMES = {
    "goldfishing": {
        "key": "goldfishing",
        "title": "Рыбалка",
        "swf": "/Swf/Games/GoldFishing.swf",
        "frame_rate": 15,
        "score_per_coin": 100,
        "max_coins": 100,
        "score_per_experience": 100,
        "max_experience": 100,
    }
}


def at_entry(room, token, x, y):
    # Original Russian GamesName id 81 = Treasures / GoldFishing, and the
    # preserved Severburg scene contains the matching mcEntryPoint_81 shape.
    if room["key"] != "severburg" or type(token) not in (int, str) or str(token) != "81":
        return None
    point = next(entry for entry in room["exits"] if entry["token"] == "81")
    left, right, top, bottom = point["bounds"]
    return "goldfishing" if left - 80 <= x <= right + 80 and top - 80 <= y <= bottom + 80 else None
