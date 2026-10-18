"""Prepare the minimal standalone item package; no server dependencies required."""

import filecmp
from pathlib import Path
import shutil
import sys


def prepare_items(root: Path, destination: Path):
    # Import the pure SWF builder without importing FastAPI, settings or the DB.
    sys.path.insert(0, str(root / "server"))
    from src.shops.swf_graphics import category_icons, metadata, wrapped

    expected = set()

    def save(relative, data):
        target = destination / relative
        expected.add(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)

    for ident, roles in metadata().items():
        if "Display" in roles or "Walking" in roles:
            save(f"Display/{ident}.swf", wrapped("Display", int(ident)))
    animations = root / "assets/compat/item-animations"
    for source in animations.glob("*.swf"):
        target = destination / "InUse" / source.name
        expected.add(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or not filecmp.cmp(source, target, shallow=False):
            shutil.copy2(source, target)
    for ident in category_icons():
        # The gateway gives btnCat0 the category ID from the live catalog.
        save(f"Cats/{ident}.swf", wrapped("Cats", ident, 0))
    # Remove only obsolete build output, never original assets or user data.
    for target in destination.rglob("*"):
        if target.is_file() and target not in expected:
            target.unlink()
    total = sum(target.stat().st_size for target in expected)
    print(f"Embedded item package: {len(expected)} files, {total:,} bytes")


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[1]
    prepare_items(repo, repo / "client/frontend/items")
