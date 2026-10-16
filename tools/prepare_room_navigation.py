"""One-time import of the verified walking-mask renders into server navigation."""

from pathlib import Path
import hashlib, json, sys, math
from collections import deque
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
from swf_room_data import SWF, rect
from functools import lru_cache


def transform(box, m):
    a, b, c, d, tx, ty = m
    points = [
        (a * x + c * y + tx, b * x + d * y + ty) for x in [box[0], box[1]] for y in [box[2], box[3]]
    ]
    return [
        min(p[0] for p in points),
        max(p[0] for p in points),
        min(p[1] for p in points),
        max(p[1] for p in points),
    ]


def geometry(s):
    @lru_cache(None)
    def bounds(ident):
        if ident not in s.defs:
            return [0, 0, 0, 0]
        kind, data, _ = s.defs[ident]
        if kind in (2, 22, 32, 83):
            return rect(data, 2)[0]
        if kind == 39:
            boxes = [transform(bounds(p["id"]), p["matrix"]) for p in s.children(ident) if p["id"]]
            if boxes:
                return [
                    min(b[0] for b in boxes),
                    max(b[1] for b in boxes),
                    min(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                ]
        return [0, 0, 0, 0]

    return bounds


TITLES = {
    "Africa": "Африка",
    "Bar": "Кактус",
    "BowlingRoom": "Боулинг",
    "BumagVale": "Долина бумагов",
    "BumagsFoodToysStore": "Еда и игрушки для бумагов",
    "BumagsPotionStore": "Зелья для бумагов",
    "BumagsStore": "Магазин бумагов",
    "CaeteOrube": "CaeteOrube",
    "CastleInnerA": "Замок: зал",
    "CastleInnerB": "Замок: покои",
    "CinemaRoom": "Кинотеатр",
    "ClothesStore": "Стиляги",
    "FearCaveGate": "Вход в Пещеру Смелых",
    "FightingBomagSchool": "Школа бумагов",
    "FightingBomagSchoolIndoor": "Зал школы бумагов",
    "ForestTree": "Полое дерево",
    "FurnitureStore": "МогоДом",
    "HallOfFame": "Зал славы",
    "HoopsRoom": "Баскетбол",
    "Hotel": "Отель",
    "InfoBoard": "Доска объявлений",
    "Island": "Остров",
    "JewelryStore": "Мастерская украшений",
    "JewelryExhibition": "Выставка украшений",
    "KingsRoad": "Солнечная улица",
    "MagicForest": "Зачарованный лес",
    "Mall": "Могоцентр",
    "maze_entrance": "Вход в лабиринт",
    "MeetingRoom": "Комната дозорных",
    "Mexico": "Мексика",
    "MogoPlay": "Планета игр",
    "Novograd": "Новоград",
    "OMGzone": "OMG Zone",
    "PartyRoom_Pirates": "Пиратская вечеринка",
    "PartyRoom_Reg": "Танцевальная вечеринка",
    "PartyRoom_Sweets": "Сладкая вечеринка",
    "Pool": "Бассейн",
    "Port": "Весёлая гавань",
    "ProfyMeetingRoom": "Тайная комната Профи",
    "ProfyQuiz": "Викторина Профи",
    "ProfyRoom": "Комната Профи",
    "Severburg": "Севербург",
    "Ship": "Корабль",
    "Skazkino": "Сказкино",
    "Spa": "Спа",
    "SportStore": "Лига",
    "Submarine": "Подводная лодка",
    "SummerCamp": "Отдыхаево",
    "Sunandsea": "Солнцеморье",
    "Vugovo": "Вьюгово",
}

# Entry numbers are authored graphic-component IDs, not server room IDs.
# Only routes supported by room names, matching return exits and/or named door
# graphics are enabled. Unresolved destinations remain explicit nulls.
ENTRY_TARGETS = {
    "3": "Novograd",
    "4": "Severburg",
    "5": "Sunandsea",
    "6": "InfoBoard",
    "7": "KingsRoad",
    "8": "SummerCamp",
    "9": "Port",
    "10": "Mall",
    "11": "ClothesStore",
    "12": "FurnitureStore",
    "13": "Bar",
    "14": "SportStore",
    "15": "Hotel",
    "16": "MogoPlay",
    "20": "Skazkino",
    "35": "OMGzone",
    "40": "HoopsRoom",
    "41": "BowlingRoom",
    "42": "HallOfFame",
    "46": "ProfyRoom",
    "47": "Spa",
    "48": "CinemaRoom",
    "17": "Pool",
    "58": "OMGzone",
    "59": "PartyRoom_Pirates",
    "60": "PartyRoom_Reg",
    "61": "PartyRoom_Sweets",
    "74": "MagicForest",
    "76": "JewelryStore",
    "78": "FearCaveGate",
    "440": "ForestTree",
    "82": "JewelryExhibition",
    "21": "Ship",
    "86": "ProfyQuiz",
    "87": "ProfyMeetingRoom",
    "90": "Vugovo",
    "104": "BumagVale",
    "132": "BumagsFoodToysStore",
    "133": "BumagsPotionStore",
    "134": "BumagsStore",
    "168": "FightingBomagSchool",
    "169": "FightingBomagSchoolIndoor",
    "164": "CastleInnerA",
    "165": "CastleInnerB",
}
# Keep this authored hit-zone repair in sync with prepareRoomView in MogobeHost.
ENTRY_POSITIONS = {"MagicForest": {"440": (100, 330)}}

IDS = {
    "InfoBoard": 2,
    "Novograd": 3,
    "Severburg": 4,
    "Sunandsea": 5,
    "KingsRoad": 7,
    "SummerCamp": 8,
    "Port": 9,
    "Mall": 10,
    "FurnitureStore": 11,
    "ClothesStore": 12,
    "Bar": 13,
    "SportStore": 14,
    "Hotel": 15,
    "MogoPlay": 16,
    "Skazkino": 20,
}

import argparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--render-dir", type=Path, required=True)
parser.add_argument("--room", help="Prepare one room, preserving all existing room IDs")
args = parser.parse_args()
renders = args.render_dir
out = ROOT / "server/src/world/rooms.json"
current = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"rooms": [], "not_walkable": []}
existing_ids = {r["swf"]: r["id"] for r in current["rooms"]}
next_room_id = max([999, *existing_ids.values(), *IDS.values()]) + 1
rooms = []
skipped = []
for p in sorted((ROOT / "assets/original/Swf/Rooms").glob("*.swf")):
    if args.room and p.stem.casefold() != args.room.casefold():
        continue
    s = SWF(p)
    r = s.summary()
    name = p.stem
    maskpath = renders / ("mask_all_" + name + ".swf") / "1.png"
    if not maskpath.exists():
        maskpath = renders / ("mask_" + name + ".swf") / "1.png"
    if not r["walking"] or not maskpath.exists():
        skipped.append(
            dict(
                name=name,
                reason="Original scene has no ordinary walking layer",
                sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            )
        )
        continue
    mask = Image.open(maskpath).convert("RGBA").getchannel("A")
    assert mask.size == (768, 480), (name, mask.size)
    grid = [
        "".join(
            "1" if all(mask.getpixel((x + dx, y + 4)) > 5 for dx in [2, 4, 6]) else "0"
            for x in range(0, 768, 8)
        )
        for y in range(0, 480, 8)
    ]
    mainpath = renders / ("mask_" + name + ".swf") / "1.png"
    mainmask = Image.open(mainpath).convert("RGBA").getchannel("A")
    allowed = {
        (x, y)
        for y in range(60)
        for x in range(96)
        if all(mainmask.getpixel((x * 8 + dx, y * 8 + 4)) > 5 for dx in [2, 4, 6])
    }
    assert allowed, name
    unseen = set(allowed)
    components = []
    while unseen:
        first = unseen.pop()
        component = {first}
        front = [first]
        while front:
            x, y = front.pop()
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                n = (x + dx, y + dy)
                if n in unseen:
                    unseen.remove(n)
                    component.add(n)
                    front.append(n)
        components.append(component)
    largest = max(components, key=len)
    preferred = (260, 392) if name == "InfoBoard" else (384, 365)
    spawn = min(
        largest,
        key=lambda c: (c[0] * 8 + 4 - preferred[0]) ** 2 + (c[1] * 8 + 4 - preferred[1]) ** 2,
    )
    spawn = [spawn[0] * 8 + 4, spawn[1] * 8 + 4]
    # Keep a deterministic safe start, away from authored door hit zones.
    bounds = geometry(s)
    children = s.children(r["root"])
    exit_holder = next(p for p in children if p["name"] == "mcExisPoints")
    exits = []
    for ex in s.children(exit_holder["id"]):
        if not (ex["name"] or "").startswith("mcEntryPoint"):
            continue
        token = ex["name"].rsplit("_", 1)[-1]
        position = ENTRY_POSITIONS.get(name, {}).get(token)
        if position:
            ex["matrix"][4:6] = position
        box = transform(transform(bounds(ex["id"]), ex["matrix"]), exit_holder["matrix"])
        target = ENTRY_TARGETS.get(token)
        if target == name:
            target = None
        entry = dict(name=ex["name"], token=token, target=target, bounds=[round(n, 2) for n in box])
        if position:
            entry["client_position"] = list(position)
        exits.append(entry)

    def clear(c):
        x, y = c[0] * 8 + 4, c[1] * 8 + 4
        return all(
            not (b[0] - 24 < x < b[1] + 24 and b[2] - 24 < y < b[3] + 24)
            for b in [e["bounds"] for e in exits]
        )

    safe = [c for c in largest if clear(c)]
    if safe and not clear((spawn[0] // 8, spawn[1] // 8)):
        cell = min(
            safe,
            key=lambda c: (c[0] * 8 + 4 - preferred[0]) ** 2 + (c[1] * 8 + 4 - preferred[1]) ** 2,
        )
        spawn = [cell[0] * 8 + 4, cell[1] * 8 + 4]
    ident = existing_ids.get(name, IDS.get(name))
    if ident is None:
        ident = next_room_id
        next_room_id += 1
    room = dict(
        id=ident,
        key=name.lower(),
        swf=name,
        symbol=r["symbol"],
        title=TITLES.get(name, name),
        width=768,
        height=480,
        cell=8,
        spawn=spawn,
        spawn_grid=["".join("1" if (x,y) in largest else "0" for x in range(96)) for y in range(60)],
        grid=grid,
        exits=exits,
        areas=[
            p["name"].removeprefix("mcWalkingArea")
            for p in children
            if (p["name"] or "").startswith("mcWalkingArea")
            and p["name"].removeprefix("mcWalkingArea").isdigit()
        ],
        source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
    )
    rooms.append(room)
if args.room:
    if len(rooms) != 1:
        parser.error("Selected room has no rendered ordinary walking mask")
    prepared = rooms[0]
    previous = next((r for r in current["rooms"] if r["key"] == prepared["key"]), None)
    rooms = [prepared if r["key"] == prepared["key"] else r for r in current["rooms"]]
    if previous is None:
        rooms.append(prepared)
    skipped = [r for r in current["not_walkable"] if r["name"].casefold() != prepared["key"]]
out.write_text(
    json.dumps(dict(rooms=rooms, not_walkable=skipped), ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print("Prepared", len(rooms), "walkable rooms; special scenes:", [v["name"] for v in skipped])
print(
    "Resolved exits:",
    sum(bool(e["target"]) for r in rooms for e in r["exits"]),
    "; unresolved:",
    sum(not e["target"] for r in rooms for e in r["exits"]),
)
