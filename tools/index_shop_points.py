"""Extract visible original shop interaction regions from repository room SWFs."""

import argparse
import json
from pathlib import Path

from index_shop_graphics import measure, transformed
from swf_room_data import SWF

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "server/src/shops/points.json")
    args = parser.parse_args()
    points = []
    rooms = json.loads((ROOT / "server/src/world/rooms.json").read_text(encoding="utf-8"))["rooms"]
    for room in rooms:
        swf = SWF(ROOT / f"assets/original/Swf/Rooms/{room['swf']}.swf")
        for holder in swf.children(swf.symbols[room["symbol"]]):
            if holder["name"] != "mcExisPoints":
                continue
            for child in swf.children(holder["id"]):
                name = child["name"] or ""
                # Original pet sales use a popup region rather than mcShopPoint.
                if not (name.startswith("mcShopPoint_") or
                        (room["key"] == "bumagsstore" and name == "mcPopupPoint_51")):
                    continue
                area = measure(swf, child["id"])
                if area is None:
                    continue
                area = transformed(transformed(area, child["matrix"]), holder["matrix"])
                if area[0] >= 768 or area[1] < 0 or area[2] >= 480 or area[3] < 0:
                    continue
                points.append({"id": room["key"] + "." + name,
                               "room_key": room["key"], "room_title": room["title"],
                               "name": name, "bounds": [round(n, 3) for n in area]})
    args.output.write_text(json.dumps(points, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Indexed {len(points)} original shop points; database bindings unchanged")


if __name__ == "__main__":
    main()
