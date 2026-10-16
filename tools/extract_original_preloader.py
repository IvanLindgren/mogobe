"""Reuse Mogo's original vector shapes and animated timelines without its network bootstrap."""
from pathlib import Path
import hashlib
import json
import struct
import zlib

def tag(kind, data=b""):
    return struct.pack("<HI", (kind << 6) | 63, len(data)) + data

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / 'assets/original/Swf/Mogo.swf'
    original = source.read_bytes()
    raw = original[:8] + zlib.decompress(original[8:]) if original[:3] == b'CWS' else original
    rect_size = (5 + 4 * (raw[8] >> 3) + 7) // 8
    start = 8 + rect_size + 4
    payload = raw[8:start]  # Original bounds, frame rate and frame count.
    pos = start
    sprites = []
    while pos < len(raw):
        begin = pos
        header = struct.unpack_from('<H', raw, pos)[0]
        pos += 2
        kind, size = header >> 6, header & 63
        if size == 63:
            size = struct.unpack_from('<I', raw, pos)[0]
            pos += 4
        data = raw[pos:pos + size]
        pos += size
        # Keep each visual definition byte-for-byte, including nested animation.
        if kind in (69, 9, 2, 22, 32, 83, 39):
            payload += raw[begin:pos]
        if kind == 39:
            sprites.append(struct.unpack_from('<HH', data))
    assert (13, 1) in sprites and any(frames > 1 for _, frames in sprites)
    payload += tag(26, b'\x06' + struct.pack('<HH', 1, 13) + b'\0')
    payload += tag(1) + tag(0)
    output = b'FWS' + raw[3:4] + struct.pack('<I', 8 + len(payload)) + payload
    out = ROOT / 'assets/compat/OriginalPreloader.swf'
    out.write_bytes(output)
    out.with_suffix('.source.json').write_text(json.dumps({
        'original_game_asset': False,
        'role': 'Original mlPreLoader graphics and animated timelines extracted without redrawing',
        'source': 'assets/original/Swf/Mogo.swf',
        'source_sha256': hashlib.sha256(original).hexdigest(),
        'sha256': hashlib.sha256(output).hexdigest(),
        'symbol': 'mlPreLoader', 'sprite_id': 13, 'sprites': sprites,
        'generated_by': 'tools/extract_original_preloader.py',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(out)


if __name__ == '__main__':
    main()
