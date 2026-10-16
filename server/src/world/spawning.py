"""Safe random starts on the original main walking layer, away from triggers."""

import math
import random
from functools import lru_cache

from src.world import catalog


@lru_cache(None)
def safe_points(key):
    room = catalog.BY_KEY[key]
    cell = room["cell"]
    points = []
    for gy, row in enumerate(room["spawn_grid"]):
        for gx, value in enumerate(row):
            x, y = gx * cell + cell / 2, gy * cell + cell / 2
            if value != "1" or not (24 <= x <= 744 and 64 <= y <= 420):
                continue
            # Leave space for the avatar's foot marker and network rounding.
            if any(
                e["bounds"][0] - 28 <= x <= e["bounds"][1] + 28
                and e["bounds"][2] - 28 <= y <= e["bounds"][3] + 28
                for e in room["exits"]
            ):
                continue
            points.append((x, y))
    if not points:
        raise ValueError("Room has no safe main-layer spawn points: " + key)
    return tuple(points)


def distance_to_entry(point, entry):
    x, y = point
    left, right, top, bottom = entry["bounds"]
    return math.hypot(max(left - x, 0, x - right), max(top - y, 0, y - bottom))


def choose(room, arrival_from=None, occupied=()):
    points = safe_points(room["key"])
    free = [p for p in points if all(math.dist(p, other) >= 36 for other in occupied)]
    if free:
        points = free
    elif occupied:
        clearance = {p: min(math.dist(p, other) for other in occupied) for p in points}
        best = max(clearance.values())
        points = [p for p in points if clearance[p] >= best - 4]
    entries = [e for e in room["exits"] if arrival_from and e["target"] == arrival_from["swf"]]
    if arrival_from and not entries and room["exits"]:
        # Four one-way links have no identified return. Prefer an unresolved
        # physical doorway on the opposite side of the source passage.
        source = next((e for e in arrival_from["exits"] if e["target"] == room["swf"]), None)
        if source:
            left, right, top, bottom = source["bounds"]
            opposite = (768 - (left + right) / 2, 480 - (top + bottom) / 2)
            candidates = [e for e in room["exits"] if e["target"] is None] or room["exits"]
            entries = [min(candidates, key=lambda e: distance_to_entry(opposite, e))]
    if entries:
        distances = {p: min(distance_to_entry(p, e) for e in entries) for p in points}
        nearest = min(distances.values())
        points = [p for p in points if distances[p] <= nearest + 48]
    else:
        anchor = room["spawn"]
        nearby = [p for p in points if math.dist(p, anchor) <= 128]
        if nearby:
            points = nearby
    return random.choice(points)
