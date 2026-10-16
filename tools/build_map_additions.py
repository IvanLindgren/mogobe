"""Extract the original Bumagland button and island from the Russian map.

Preserves vector/timeline records, including all button states. No redraws or
original edits. The game supplies the original Button controller at runtime.
"""
from pathlib import Path
import hashlib
import json
import struct
import zlib

from swf_room_data import SWF, place, records, rect
from build_loading_stub import build

ROOT = Path(__file__).resolve().parents[1]


def tag(kind, data=b""):
    return struct.pack("<HI", (kind << 6) | 63, len(data)) + data


def main():
    source = ROOT / "assets/original/Swf/Assets/Popups/WorldMapRussian.swf"
    swf = SWF(source)
    assert swf.symbols["p_3_fla.AravaBtn2_11"] == 92
    assert any(p["name"] == "mcBumagVale" and p["id"] == 92 for p in swf.children(286))
    # Object 286 starts with the island scenery, then its button at depth 55.
    # Subsequent placements belong to the other destinations on the map.
    placements = []
    for kind, body, encoded in records(swf.defs[286][1][4:]):
        p = place(kind, body)
        if p and p["depth"] <= 55:
            placements.append(encoded)
    assert len(placements) == 17
    body = swf.header[:-2] + struct.pack("<H", 1)
    body += tag(69, struct.pack("<I", 8))
    for kind, data, encoded in swf.tags:
        # Retain the exact original graphics/timelines. Export the selected
        # fragment as a class so each popup can instantiate it synchronously.
        if kind == 39 and int.from_bytes(data[:2], "little") == 286:
            data = data[:4] + b"".join(placements) + tag(1) + tag(0)
            encoded = tag(39, data)
        if kind in (2, 6, 7, 10, 11, 14, 20, 21, 22, 32, 33, 34, 35, 36, 37,
                    39, 46, 48, 60, 61, 62, 73, 75, 83, 84, 87, 88, 90, 91):
            body += encoded
    exports = [(0, "MogobeMapBumagLand"), (286, "MogobeBumagMapFragment")]
    for ident, name in exports:
        stub = build(name, root=ident == 0)
        _, offset = rect(stub[8:])
        body += b"".join(encoded for kind, _, encoded in records(stub[8+offset+4:]) if kind == 82)
    body += tag(76, struct.pack("<H", len(exports)) + b"".join(
        struct.pack("<H", ident) + name.encode("ascii") + b"\0" for ident, name in exports))
    body += tag(1) + tag(0)
    output = ROOT / "assets/compat/WorldMapBumagLand.swf"
    output.write_bytes(b"CWS" + bytes([swf.version]) + struct.pack("<I", len(body)+8) + zlib.compress(body))
    output.with_suffix(".source.json").write_text(json.dumps({
        "original_game_asset": False,
        "original_graphics": True,
        "source": source.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "generator": "tools/build_map_additions.py",
        "button_symbol": "p_3_fla.AravaBtn2_11",
        "fragment_class": "MogobeBumagMapFragment",
        "loading": "Preload once at startup; instantiate original fragment for each popup",
        "map_object": 286,
        "map_depths": "2-55 (island scenery and original button)",
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Extracted original Bumagland button and island:", output)


if __name__ == "__main__":
    main()
