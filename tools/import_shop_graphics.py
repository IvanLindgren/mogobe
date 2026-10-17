"""Import unchanged shop graphics once. Normal builds require no external archive."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import zlib

from swf_room_data import place, records, rect

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", required=True, type=Path)
    args = parser.parse_args()
    meta = {}
    index = json.loads((ROOT / "assets/catalogs/shop-assets.json").read_text(encoding="utf-8"))
    source_meta = json.loads((ROOT / "assets/original/sources.json").read_text(encoding="utf-8"))
    source_meta = [r for r in source_meta if not r["path"].startswith(("Swf/Items/Display/", "Swf/Items/InUse/", "Swf/Items/Walking/")) and r["path"] != "Swf/Assets/Popups/Shop.swf"]
    with zipfile.ZipFile(args.archive_root / "Ru/Clothes.zip") as archive:
        for item in index["items"]:
            row = {}
            for role, target in [("display", "Display"), ("standing", "InUse"), ("walking", "Walking")]:
                if role not in item:
                    continue
                name = item[role][0]
                data = archive.read(name)
                body = zlib.decompress(data[8:]) if data[:3] == b"CWS" else data[8:]
                _, offset = rect(body)
                placements = [place(k, b) for k, b, _ in records(body[offset + 4:]) if k in (26, 70)]
                top = next(p for p in placements if p and p["id"] and p["name"])
                row[target] = {"sprite_id": top["id"], "matrix": top["matrix"]}
                relative = f'Swf/Items/{target}/{item["id"]}.swf'
                path = ROOT / "assets/original" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                source_meta.append({"path": relative, "source": "Ru/Clothes.zip!" + name,
                                    "sha256": hashlib.sha256(data).hexdigest(), "modified": False})
            for name in item.get("walking", [])[1:]:
                data = archive.read(name)
                relative = "Swf/Items/Walking/" + Path(name).name
                (ROOT / "assets/original" / relative).write_bytes(data)
                source_meta.append({"path": relative,"source":"Ru/Clothes.zip!"+name,"sha256":hashlib.sha256(data).hexdigest(),"modified":False})
            meta[str(item["id"])] = row
    popup = args.archive_root / "Ru/Popups/p_33.swf"
    destination = ROOT / "assets/original/Swf/Assets/Popups/Shop.swf"
    shutil.copy2(popup, destination)
    source_meta.append({"path": "Swf/Assets/Popups/Shop.swf", "source": "Ru/Popups/p_33.swf", "original_name": "p_33.swf", "sha256": hashlib.sha256(popup.read_bytes()).hexdigest(), "modified": False})
    (ROOT / "assets/original/sources.json").write_text(json.dumps(source_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "assets/catalogs/shop-graphics.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    from index_shop_graphics import main as index_bounds
    index_bounds()
    print("Imported display and standing graphics for", len(meta), "IDs and original shop popup.")


if __name__ == "__main__":
    main()
