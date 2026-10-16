from pathlib import Path
import struct, zlib, json, re


class Bits:
    def __init__(self, data, pos=0):
        self.data = data
        self.bit = pos * 8

    def u(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.data[self.bit // 8] >> (7 - self.bit % 8)) & 1)
            self.bit += 1
        return v

    def s(self, n):
        v = self.u(n)
        return v - (1 << n) if n and v >> (n - 1) else v

    def align(self):
        self.bit = (self.bit + 7) // 8 * 8

    @property
    def pos(self):
        return (self.bit + 7) // 8


def records(raw):
    pos = 0
    while pos + 2 <= len(raw):
        start = pos
        h = int.from_bytes(raw[pos : pos + 2], "little")
        pos += 2
        kind = h >> 6
        length = h & 63
        if length == 63:
            length = int.from_bytes(raw[pos : pos + 4], "little")
            pos += 4
        body = raw[pos : pos + length]
        pos += length
        yield kind, body, raw[start:pos]
        if not kind:
            break


def rect(data, pos=0):
    b = Bits(data, pos)
    n = b.u(5)
    v = [b.s(n) / 20 for _ in range(4)]
    b.align()
    return v, b.pos


def matrix(data, pos=0):
    start = pos
    b = Bits(data, pos)
    a = d = 1.0
    rb = rc = 0.0
    if b.u(1):
        n = b.u(5)
        a = b.s(n) / 65536
        d = b.s(n) / 65536
    if b.u(1):
        n = b.u(5)
        rb = b.s(n) / 65536
        rc = b.s(n) / 65536
    n = b.u(5)
    x = b.s(n) / 20
    y = b.s(n) / 20
    b.align()
    return [a, rb, rc, d, x, y], data[start : b.pos], b.pos


def place(kind, data):
    if kind not in (26, 70):
        return None
    flags = data[0]
    extra = data[1] if kind == 70 else 0
    pos = 2 if kind == 70 else 1
    depth = int.from_bytes(data[pos : pos + 2], "little")
    pos += 2
    if extra & 8 or (extra & 16 and flags & 2):
        pos = data.index(b"\0", pos) + 1
    cid = None
    if flags & 2:
        cid = int.from_bytes(data[pos : pos + 2], "little")
        pos += 2
    m = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    mb = b"\0"
    if flags & 4:
        m, mb, pos = matrix(data, pos)
    if flags & 8:
        b = Bits(data, pos)
        add = b.u(1)
        mul = b.u(1)
        n = b.u(4)
        for _ in range(4 * int(add) + 4 * int(mul)):
            b.s(n)
        b.align()
        pos = b.pos
    if flags & 16:
        pos += 2
    name = None
    if flags & 32:
        end = data.index(b"\0", pos)
        name = data[pos:end].decode("utf-8")
        pos = end + 1
    return dict(id=cid, depth=depth, name=name, matrix=m, matrix_bytes=mb)


class SWF:
    def __init__(self, path):
        self.path = Path(path)
        d = self.path.read_bytes()
        body = zlib.decompress(d[8:]) if d[:3] == b"CWS" else d[8:]
        self.rect, first = rect(body)
        self.version = d[3]
        self.header = body[: first + 4]
        self.tags = list(records(body[first + 4 :]))
        self.defs = {}
        self.symbols = {}
        for kind, block, encoded in self.tags:
            if kind in (2, 22, 32, 83, 39):
                self.defs[int.from_bytes(block[:2], "little")] = (kind, block, encoded)
            if kind == 76:
                pos = 2
                for i in range(int.from_bytes(block[:2], "little")):
                    ident = int.from_bytes(block[pos : pos + 2], "little")
                    pos += 2
                    end = block.index(b"\0", pos)
                    name = block[pos:end].decode()
                    pos = end + 1
                    self.symbols[name] = ident

    def children(self, ident):
        if ident not in self.defs or self.defs[ident][0] != 39:
            return []
        rows = []
        for kind, data, _ in records(self.defs[ident][1][4:]):
            if kind == 1:
                break
            p = place(kind, data)
            if p:
                rows.append(p)
        return rows

    def summary(self):
        name = re.sub(r"\[\d+\]", "", self.path.stem)
        symbol = "ml" + ("maze_entrance" if name == "Maze_entrance" else name)
        root = self.symbols.get(symbol)
        children = self.children(root)
        walking = [r for r in children if (r["name"] or "").startswith("mcWalking")]
        exits = next((r for r in children if r["name"] == "mcExisPoints"), None)
        exitrows = self.children(exits["id"]) if exits else []
        return dict(
            file=self.path.name,
            root=root,
            symbol=symbol,
            walking=[{k: v for k, v in r.items() if k != "matrix_bytes"} for r in walking],
            exits=[{k: v for k, v in r.items() if k != "matrix_bytes"} for r in exitrows],
        )


if __name__ == "__main__":
    for p in sorted(
        (Path(__file__).resolve().parents[1] / "assets/original/Swf/Rooms").glob("*.swf")
    ):
        print(json.dumps(SWF(p).summary(), ensure_ascii=False))
