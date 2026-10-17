"""Index preserved item graphics separately from the missing server shop catalog.

python tools/audit_shop_assets.py --archive-root PATH_TO_GAME_ARCHIVE
Reads ZIP files without extracting them. Not used by normal client builds.
"""

import argparse
import hashlib
import json
import re
import zipfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path

from swf_room_data import place, records, rect

ROOT = Path(__file__).resolve().parents[1]


def swf_info(data):
    if data[:3] == b"CWS":
        body = zlib.decompress(data[8:])
    elif data[:3] == b"FWS":
        body = data[8:]
    else:
        raise ValueError("Unsupported SWF signature")
    _, offset = rect(body)
    symbols, names, embedded = [], [], []
    for kind, block, _ in records(body[offset + 4 :]):
        if kind in (56, 76):
            pos = 2
            for _ in range(int.from_bytes(block[:2], "little")):
                pos += 2
                end = block.index(b"\0", pos)
                symbols.append(block[pos:end].decode("utf-8", errors="replace"))
                pos = end + 1
        if kind in (26, 70):
            placement = place(kind, block)
            if placement and placement["name"]:
                names.append(placement["name"])
        if kind == 87:
            embedded.append({"id": int.from_bytes(block[:2], "little"), "bytes": len(block) - 6})
    return {"symbols": symbols, "stage_names": names, "embedded_binary": embedded}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def audit(archive_root):
    archives, items, role_ids, errors = [], defaultdict(dict), defaultdict(set), []
    clean_count = 0
    for relative in ["Ru/Clothes.zip", "He/Items.zip", "Br/BigItems BR.zip"]:
        path = archive_root / relative
        if not path.exists():
            if relative == "Ru/Clothes.zip":
                raise FileNotFoundError(path)
            continue
        with zipfile.ZipFile(path) as archive:
            files = [entry for entry in archive.infolist() if not entry.is_dir()]
            row = {
                "path": relative,
                "sha256": digest(path),
                "file_count": len(files),
                "uncompressed_bytes": sum(entry.file_size for entry in files),
                "extensions": dict(Counter(Path(entry.filename).suffix.lower() for entry in files)),
            }
            archives.append(row)
            if relative != "Ru/Clothes.zip":
                continue
            for entry in files:
                match = re.fullmatch(r"(?:item_)?(\d+)(?:\[\d+\])?\.swf", Path(entry.filename).name)
                if not match:
                    errors.append({"file": entry.filename, "error": "Unrecognized filename"})
                    continue
                ident = int(match[1])
                role = {"Clothes": "display", "IconS RU": "standing", "IconW RU": "walking"}.get(
                    Path(entry.filename).parent.name
                )
                if not role:
                    errors.append({"file": entry.filename, "error": "Unknown asset family"})
                    continue
                info = swf_info(archive.read(entry))
                if not info["symbols"]:
                    clean_count += 1
                role_ids[role].add(ident)
                items[ident].setdefault(role, []).append(entry.filename)
            row["families"] = {
                role: {
                    "files": sum(len(item.get(role, [])) for item in items.values()),
                    "unique_ids": len(ids),
                }
                for role, ids in sorted(role_ids.items())
            }
            row["without_exported_symbols"] = clean_count
    popups = []
    for relative in ["Ru/Popups/p_33.swf"]:
        path = archive_root / relative
        if path.exists():
            popups.append(
                {"source": relative, "sha256": digest(path), **swf_info(path.read_bytes())}
            )
    main = ROOT / "assets/original/Swf/Main.swf"
    return {
        "description": "Inventory of graphics, not a historical list of items offered for sale",
        "generator": "tools/audit_shop_assets.py",
        "source_archives": archives,
        "russian_summary": {
            "unique_ids": len(items),
            "all_three_representations": len(set.intersection(*role_ids.values())),
            "display_without_both_animations": sorted(
                role_ids["display"] - (role_ids["standing"] & role_ids["walking"])
            ),
            "animation_ids_without_display": sorted(
                (role_ids["standing"] | role_ids["walking"]) - role_ids["display"]
            ),
        },
        "shop_popup": popups,
        "protocol": {
            "main_sha256": digest(main),
            "store_request": "rooms__getStoreData",
            "request_fields": ["roomId"],
            "store_response": ["items", "categories"],
            "purchase_request": "user__buyItem",
            "purchase_fields": ["itemId"],
            "item_fields": [
                "id",
                "typeId",
                "sCat",
                "pCat",
                "price",
                "src",
                "mType",
                "inStock",
                "locked",
                "trd",
                "s",
                "sts",
            ],
            "category_fields": ["typeId", "name"],
            "evidence": (
                "Original Main.swf ShopPopup, RequestHandler, StoreTO, ItemTO and CategorieTO"
            ),
            "historical_store_assignments_recovered": False,
            "historical_prices_recovered": False,
            "historical_categories_recovered": False,
            "linkage_note": (
                "Russian graphics with no exported classes need a wrapper/adaptation before "
                "the original ItemFactory can instantiate them. File IDs are graphics IDs, "
                "not proof of a historical offer."
            ),
        },
        "items": [{"id": ident, **roles} for ident, roles in sorted(items.items())],
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "assets/catalogs/shop-assets.json")
    args = parser.parse_args()
    result = audit(args.archive_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = dict(result["russian_summary"])
    for field in ["display_without_both_animations", "animation_ids_without_display"]:
        summary[field] = len(summary[field])
    print(
        json.dumps(
            {
                "archives": result["source_archives"],
                "summary": summary,
                "errors": result["errors"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
