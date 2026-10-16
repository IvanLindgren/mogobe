"""Navigation on grids derived from original Russian room walking masks."""

import heapq
import math
from functools import lru_cache

from src.world.catalog import BY_KEY


@lru_cache
def world_data():
    return {"rooms": BY_KEY}


def room_data(room):
    return world_data()["rooms"][room]


def walkable(room, x, y):
    r = room_data(room)
    gx, gy = int(x // r["cell"]), int(y // r["cell"])
    return 0 <= gy < len(r["grid"]) and 0 <= gx < len(r["grid"][gy]) and r["grid"][gy][gx] == "1"


def path_to(room, start, target):
    r = room_data(room)
    cell = r["cell"]
    allowed = {(x, y) for y, row in enumerate(r["grid"]) for x, v in enumerate(row) if v == "1"}
    if not allowed:
        raise ValueError("В комнате нет области ходьбы")

    def nearest(point):
        return min(
            allowed,
            key=lambda c: (
                (c[0] * cell + cell / 2 - point[0]) ** 2 + (c[1] * cell + cell / 2 - point[1]) ** 2
            ),
        )

    origin, goal = nearest(start), nearest(target)
    frontier = [(0.0, origin)]
    costs, parents = {origin: 0.0}, {}
    while frontier:
        _, current = heapq.heappop(frontier)
        if current == goal:
            chain = [current]
            while current in parents:
                current = parents[current]
                chain.append(current)
            return [[x * cell + cell / 2, y * cell + cell / 2] for x, y in reversed(chain)]
        x, y = current
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
            nxt = (x + dx, y + dy)
            if nxt not in allowed:
                continue
            if dx and dy and ((x + dx, y) not in allowed or (x, y + dy) not in allowed):
                continue
            value = costs[current] + math.hypot(dx, dy)
            if value < costs.get(nxt, math.inf):
                costs[nxt], parents[nxt] = value, current
                heapq.heappush(frontier, (value + math.dist(nxt, goal), nxt))
    raise ValueError("До этой точки нет прохода")
