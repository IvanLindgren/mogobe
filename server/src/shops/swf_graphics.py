"""Build item compatibility movies using only the Python standard library.

Shared by server admin previews and the standalone Windows asset build.
Original graphics are read without modification.
"""

import json
import struct
import zlib
from functools import lru_cache
from pathlib import Path

from .swf_stub import build

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT.parent / "assets/original/Swf/Items"


@lru_cache
def category_icons():
    data = json.loads(
        (ROOT.parent / "assets/catalogs/shop-categories.json").read_text(encoding="utf-8")
    )
    return {item["id"]: item for item in data["icons"]}


def tag(kind, block=b""):
    return struct.pack("<HI", (kind << 6) | 63, len(block)) + block


def records(raw):
    pos = 0
    while pos + 2 <= len(raw):
        header = int.from_bytes(raw[pos : pos + 2], "little")
        pos += 2
        kind, length = header >> 6, header & 63
        if length == 63:
            length = int.from_bytes(raw[pos : pos + 4], "little")
            pos += 4
        block = raw[pos : pos + length]
        pos += length
        yield kind, block
        if kind == 0:
            return


def matrix(values):
    a, b, c, d, tx, ty = values
    bits = ""

    def numbers(nums):
        n = max(2, *(abs(v).bit_length() + 1 for v in nums))
        return f"{n:05b}" + "".join(f"{v & ((1 << n) - 1):0{n}b}" for v in nums)

    bits += "1" + numbers([round(a * 65536), round(d * 65536)])
    bits += "1" + numbers([round(b * 65536), round(c * 65536)]) if b or c else "0"
    bits += numbers([round(tx * 20), round(ty * 20)])
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big")


@lru_cache
def metadata():
    return json.loads(
        (ROOT.parent / "assets/catalogs/shop-graphics.json").read_text(encoding="utf-8")
    )


def wrapped(role, ident, category_id=0):
    source_role = "Display" if role == "Preview" else role
    if source_role == "Display" and "Display" not in metadata().get(str(ident), {}):
        source_role = "Walking"
    info = (
        category_icons().get(ident)
        if role == "Cats"
        else metadata().get(str(ident), {}).get(source_role)
    )
    if not info:
        raise KeyError(ident)
    raw = (
        ROOT.parent / "assets/compat/InventoryCategoryIcons.swf"
        if role == "Cats"
        else ASSETS / source_role / f"{ident}.swf"
    ).read_bytes()
    body = zlib.decompress(raw[8:]) if raw[:3] == b"CWS" else raw[8:]
    offset = (5 + (body[0] >> 3) * 4 + 7) // 8
    chunks = list(records(body[offset + 4 :]))
    result = body[:offset] + struct.pack("<HH", 15 << 8, 1) + tag(69, struct.pack("<I", 8))
    ids = [
        int.from_bytes(b[:2], "little")
        for k, b in chunks
        if k
        in (
            2,
            6,
            7,
            10,
            11,
            14,
            20,
            21,
            22,
            32,
            33,
            34,
            35,
            36,
            37,
            39,
            46,
            48,
            60,
            61,
            62,
            73,
            75,
            83,
            84,
            87,
            88,
            90,
            91,
        )
    ]
    for kind, block in chunks:
        if kind not in (0, 1, 9, 26, 28, 43, 56, 65, 69, 70, 76, 77, 82, 86):
            result += tag(kind, block)
    next_id = max(ids, default=0) + 1
    exports = []
    if role == "InUse":
        exports.append((info["sprite_id"], f"mlIconSItem{ident}"))
    else:
        if role == "Display" or source_role == "Walking":
            exports.append((info["sprite_id"], f"mlBigItem{ident}"))
        names = [f"btnCat{category_id}" if role == "Cats" else f"btnItem{ident}"]
        for name in names:
            if role == "Cats":
                x1, x2, y1, y2 = info["bounds"]
                scale = min(28 / max(x2 - x1, 1), 24 / max(y2 - y1, 1))
                a, b, c, d, tx, ty = 1, 0, 0, 1, -(x1 + x2) / 2, -(y1 + y2) / 2
                cx, cy = 22.475, 18.25
            else:
                a, b, c, d, tx, ty = info["matrix"]
                x1, x2, y1, y2 = info.get("bounds", [-50, 50, -50, 50])
                # Original mlItemState white area: x=14.8..70.9,
                # y=6.2..57.7. Keep four original pixels of padding.
                width, height = (88, 88) if role == "Preview" else (48.1, 43.5)
                scale = min(width / max(x2 - x1, 1), height / max(y2 - y1, 1))
                tx -= (x1 + x2) / 2
                ty -= (y1 + y2) / 2
                cx, cy = (50, 50) if role == "Preview" else (42.85, 31.95)
            transform = [
                a * scale,
                b * scale,
                c * scale,
                d * scale,
                tx * scale + cx,
                ty * scale + cy,
            ]
            placement = bytes([6]) + struct.pack("<HH", 1, info["sprite_id"]) + matrix(transform)
            result += tag(39, struct.pack("<HH", next_id, 1) + tag(26, placement) + tag(1) + tag(0))
            exports.append((next_id, name))
            next_id += 1
    for _, name in exports:
        stub = build(
            name, frame=info.get("preview_frame") if name.startswith("mlBigItem") else None
        )
        sb = stub[8:]
        start = (5 + (sb[0] >> 3) * 4 + 7) // 8 + 4
        result += b"".join(tag(k, b) for k, b in records(sb[start:]) if k == 82)
    result += tag(
        76,
        struct.pack("<H", len(exports))
        + b"".join(struct.pack("<H", i) + n.encode() + b"\0" for i, n in exports),
    )
    if role == "Preview":
        result += tag(
            26, bytes([6]) + struct.pack("<HH", 1, exports[-1][0]) + matrix([1, 0, 0, 1, 0, 0])
        )
    result += tag(1) + tag(0)
    return (
        b"CWS"
        + bytes([max(10, raw[3])])
        + struct.pack("<I", len(result) + 8)
        + zlib.compress(result)
    )


