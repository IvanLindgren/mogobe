"""Generate a tiny AS3 compatibility class, without replacing any original SWF.

Equivalent ActionScript:
  package { public dynamic class mlLoadingScreen_0 extends flash.display.MovieClip {
    public function mlLoadingScreen_0() { super(); }
  } }

The missing historical loading screen becomes an empty two-second wait; the
actual login, room, avatar and control panel remain the original movies.
No external AS3 compiler or downloaded substitute graphics are required.
"""

import struct


def u30(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out) + bytes([value])


def tag(kind, data=b""):
    return struct.pack("<HI", (kind << 6) | 63, len(data)) + data


def build(class_name="mlLoadingScreen_0", root=False, frame=None):
    abc = bytearray(struct.pack("<HH", 16, 46))
    abc += b"\x01\x01\x01"  # empty int/uint/double pools
    strings = [b"", b"flash.display", b"MovieClip", class_name.encode("ascii")]
    if frame is not None:
        strings.append(b"gotoAndStop")
    abc += u30(len(strings))
    for value in strings[1:]:
        abc += u30(len(value)) + value
    abc += b"\x03\x16\x00\x16\x01"  # public package namespaces
    abc += b"\x01"  # namespace sets
    abc += bytes([4 if frame is not None else 3]) + b"\x07\x02\x02\x07\x01\x03"
    if frame is not None:
        abc += b"\x07\x01\x04"  # public gotoAndStop
    abc += b"\x03" + b"\x00\x00\x00\x00" * 3  # method signatures
    abc += b"\x00"  # metadata
    abc += b"\x01\x02\x01\x00\x00\x00\x00"  # class instance
    abc += b"\x01\x00"  # static initializer, no traits
    abc += b"\x01\x02\x01\x02\x04\x01\x00"  # script exporting class
    constructor = bytes.fromhex("d0 30 d0 49 00")
    if frame is not None:
        constructor += bytes.fromhex("d0 25") + u30(frame) + bytes.fromhex("4f 03 01")
    constructor += b"\x47"
    bodies = [
        (0, 2 if frame is not None else 1, 1, 1, 2, constructor),
        (1, 1, 1, 1, 2, bytes.fromhex("d0 30 47")),
        (2, 2, 1, 0, 2, bytes.fromhex("d0 30 65 00 60 01 30 60 01 58 00 1d 68 02 47")),
    ]
    abc += u30(len(bodies))
    for method, stack, locals_, initial, maximum, code in bodies:
        for value in [method, stack, locals_, initial, maximum, len(code)]:
            abc += u30(value)
        abc += code + b"\x00\x00"  # no exceptions or activation traits
    # RECT(0,15360,0,9600), 15fps, one frame. A minimal stage is sufficient:
    # this movie exports a class that Main instantiates, it is never the root.
    if root:
        bits = f"{15:05b}" + "".join(f"{n:015b}" for n in (0, 15360, 0, 9600))
        bits += "0" * (-len(bits) % 8)
        rect = int(bits, 2).to_bytes(len(bits) // 8, "big")
    else:
        rect = b"\x08\x00"  # zero bounds
    payload = rect + struct.pack("<HH", 15 << 8, 1)
    payload += tag(69, struct.pack("<I", 8))  # FileAttributes: AS3
    payload += tag(82, b"\x00\x00\x00\x00loading-compat\x00" + abc)
    if root:
        payload += tag(76, struct.pack("<HH", 1, 0) + class_name.encode("ascii") + b"\0")
    payload += tag(1) + tag(0)
    return b"FWS" + bytes([10]) + struct.pack("<I", len(payload) + 8) + payload
