"""Give the original 16px site icon the sizes required by the Windows shell."""
from pathlib import Path
import hashlib
import json
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / 'assets/ui'
    source = folder / 'site-original.ico'
    original = Image.open(source).convert('RGBA')
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [original.resize((size, size), Image.Resampling.NEAREST) for size in sizes]
    out = folder / 'app.ico'
    frames[-1].save(out, format='ICO', sizes=[(size, size) for size in sizes], append_images=frames[:-1])
    metadata = json.loads((folder / 'site-original.source.json').read_text())
    metadata.update(original_game_asset=False, modified=True, source='assets/ui/site-original.ico',
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    sha256=hashlib.sha256(out.read_bytes()).hexdigest(), bytes=out.stat().st_size,
                    role='Original favicon pixels scaled with nearest-neighbor into Windows icon sizes',
                    sizes=sizes, generated_by='tools/prepare_icon.py')
    (folder / 'app.source.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    original.resize((128, 128), Image.Resampling.NEAREST).save(ROOT / 'client/build/appicon.png')
    shutil.copy2(out, ROOT / 'client/build/windows/icon.ico')
    print('Windows icon sizes:', Image.open(out).ico.sizes())


if __name__ == '__main__':
    main()
