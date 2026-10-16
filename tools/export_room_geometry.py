from pathlib import Path
import struct, zlib, json, sys, re, hashlib
from swf_room_data import SWF, records, place
import argparse, subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(
    description="Render original room geometry and walking masks with JPEXS."
)
parser.add_argument("--room", help="Export just one SWF room name")
parser.add_argument("--java", default="java")
parser.add_argument("--ffdec", required=True)
parser.add_argument("--output", type=Path, default=ROOT / "tools/exports/room-geometry")
args = parser.parse_args()
out = args.output
movies = out / "movies"
movies.mkdir(parents=True, exist_ok=True)


def tag(kind, data=b""):
    return struct.pack("<HI", (kind << 6) | 63, len(data)) + data


def stage():
    bits = f"{15:05b}" + "".join(f"{n:015b}" for n in (0, 15360, 0, 9600))
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big") + struct.pack("<HH", 15 << 8, 1)


def export_movie(swf, name, placements, preview=False):
    data = stage()
    root = swf.summary()["root"]
    for kind, body, encoded in swf.tags:
        if kind in (0, 1, 4, 5, 9, 12, 26, 28, 43, 59, 69, 70, 76, 77, 82, 86):
            continue
        if kind == 39 and int.from_bytes(body[:2], "little") == root and preview:
            children = body[:4]
            for child_kind, child_body, child_encoded in records(body[4:]):
                p = place(child_kind, child_body)
                if p and (p["name"] or "").startswith(
                    ("mcWalkingArea", "mcExisPoints", "mcIntractiveCursor")
                ):
                    continue
                children += child_encoded
            encoded = tag(kind, children)
        data += encoded
    for depth, p in enumerate(placements, 1):
        data += tag(26, b"\x06" + struct.pack("<HH", depth, p["id"]) + p["matrix_bytes"])
    data += tag(1) + tag(0)
    (movies / (name + ".swf")).write_bytes(
        b"CWS" + bytes([swf.version]) + struct.pack("<I", len(data) + 8) + zlib.compress(data)
    )


paths = list((ROOT / "assets/original/Swf/Rooms").glob("*.swf"))
if args.room:
    paths = [p for p in paths if p.stem.casefold() == args.room.casefold()]
    if not paths:
        parser.error("Room SWF not found")
catalog = []
seen = set()
for p in paths:
    sw = SWF(p)
    r = sw.summary()
    name = r["symbol"][2:]
    if name in seen:
        continue
    seen.add(name)
    r.update(source=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest(), name=name)
    if r["root"]:
        placements = sw.children(r["root"])
        walking = [row for row in placements if (row["name"] or "").startswith("mcWalkingArea")]
        main = next((row for row in walking if row["name"] == "mcWalkingArea"), None)
        if main:
            export_movie(sw, "mask_" + name, [main])
            if len(walking) > 1:
                export_movie(sw, "mask_all_" + name, walking)
        export_movie(sw, "preview_" + name, [dict(id=r["root"], matrix_bytes=b"\0")], preview=True)
    catalog.append(r)
(out / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
print("Prepared", len(catalog), "assets and", len(list(movies.glob("*.swf"))), "analysis movies")

subprocess.run(
    [
        args.java,
        "-Djava.awt.headless=true",
        "-jar",
        args.ffdec,
        "-ignorebackground",
        "-format",
        "frame:png",
        "-export",
        "frame",
        str(out / "renders"),
        str(movies),
    ],
    check=True,
)
