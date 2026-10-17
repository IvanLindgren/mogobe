import zlib

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_multiplayer import account, auth
from test_shops import setup_shop

from src.shops.classification import classification
from src.shops.graphics import metadata
from src.shops.models import Category, Item, Offer, OwnedItem, Shop
from src.shops.service import asset_index

KEYS = ("admin1", "admin2", "admin3")


def test_three_private_catalogs_classify_assets_and_preserve_manual_edits(app):
    with TestClient(app) as client:
        _, token, _ = setup_shop(client, app)
        h = auth(token)
        result = client.post("/api/admin/shops/admin/import-assets", headers=h)
        assert result.status_code == 200
        result = result.json()
        assert result["total_assets"] == result["offers_created"] == 2456
        assert result["walking_previews"] == 108
        assert {s["key"] for s in result["shops"]} == set(KEYS)
        catalogs = {key: client.get(f"/api/shops/{key}", headers=h) for key in KEYS}
        all_ids = []
        for response in catalogs.values():
            assert response.status_code == 200 and len(response.content) < 1024 * 1024
            data = response.json()
            assert data["admin_only"]
            assert data["kind"] == ("clothing" if data["key"] == "admin1" else "objects")
            all_ids.extend(i["typeId"] for i in data["items"])
            assert all(i["price"] == 0 for i in data["items"])
        assert len(all_ids) == len(set(all_ids)) == 2456
        assert set(all_ids) == set(asset_index())
        assert {i["mType"] for i in catalogs["admin1"].json()["items"]} <= {1, 3, 4}
        assert {i["mType"] for i in catalogs["admin2"].json()["items"]} <= set(range(6, 12))
        assert {i["mType"] for i in catalogs["admin3"].json()["items"]} <= {2, 12, 13, 14}
        items = {i["id"]: i for i in client.get("/api/admin/items", headers=h).json()}
        assert items[1]["name"] == "Тестовый предмет"  # Explicit manual metadata survives.
        assert items[2]["main_type"] == 6
        assert items[50]["main_type"] == 2
        assert items[100]["main_type"] == 1 and items[100]["inventory_category"] == 4
        assert items[2351]["main_type"] == 1 and items[2351]["inventory_category"] == 0
        assert items[667]["main_type"] == 3 and items[1300]["main_type"] == 8
        assert items[1357]["main_type"] == 10 and items[1723]["main_type"] == 13
        data = client.get("/api/admin/shops/admin1/catalog", headers=h).json()
        assert len(data["categories"]) == 8
        offer = next(o for o in data["offers"] if o["item_id"] == 100)
        offer = {k: v for k, v in offer.items() if k not in ("id", "shop_id")}
        offer.update(price=37, experience=12, stock=3)
        assert (
            client.put("/api/admin/shops/admin1/offers/100", headers=h, json=offer).status_code
            == 200
        )
        again = client.post("/api/admin/shops/admin/import-assets", headers=h).json()
        assert all(
            again[k] == 0
            for k in (
                "items_created",
                "items_classified",
                "offers_created",
                "offers_moved",
                "categories_created",
            )
        )
        saved = next(
            o
            for o in client.get("/api/admin/shops/admin1/catalog", headers=h).json()["offers"]
            if o["item_id"] == 100
        )
        assert (saved["price"], saved["experience"], saved["stock"]) == (37, 12, 3)
        _, regular = account(client, "RegularCatalog", 7)
        assert (
            client.post("/api/admin/shops/admin/import-assets", headers=auth(regular)).status_code
            == 403
        )
        for key in KEYS:
            assert client.get(f"/api/shops/{key}", headers=auth(regular)).status_code == 404
            assert (
                client.post(
                    f"/api/shops/{key}/buy",
                    headers=auth(regular),
                    json={"item_id": 101, "expected_price": 0},
                ).status_code
                == 404
            )


def test_legacy_numeric_catalog_moves_offers_without_losing_ownership_or_prices(app):
    with TestClient(app) as client:
        account_id, token, _ = setup_shop(client, app)
        h = auth(token)

        async def old_catalog():
            async with app.state.sessions() as db:
                shop = Shop(key="admin", title="Административный каталог", kind="objects")
                db.add(shop)
                await db.flush()
                cat = Category(shop_id=shop.id, name="ID 0001–0200", icon_id=4)
                db.add(cat)
                for ident in (2, 50, 100):
                    db.add(
                        Item(id=ident, name=f"Предмет {ident}", main_type=0, inventory_category=0)
                    )
                await db.flush()
                for ident in (2, 50, 100):
                    db.add(
                        Offer(
                            shop_id=shop.id,
                            category_id=cat.id,
                            item_id=ident,
                            price=37,
                            experience=12,
                            stock=3,
                            enabled=False,
                        )
                    )
                db.add(OwnedItem(account_id=account_id, item_id=50))
                await db.commit()

        client.portal.call(old_catalog)
        result = client.post("/api/admin/shops/admin/import-assets", headers=h).json()
        assert result["items_classified"] == result["offers_moved"] == 3
        assert result["offers_created"] == 2453
        for key, ident in zip(KEYS, (100, 2, 50), strict=True):
            data = client.get(f"/api/admin/shops/{key}/catalog", headers=h).json()
            saved = next(o for o in data["offers"] if o["item_id"] == ident)
            assert (saved["price"], saved["experience"], saved["stock"], saved["enabled"]) == (
                37,
                12,
                3,
                False,
            )
            assert not any(c["name"].startswith("ID ") for c in data["categories"])
        inventory = client.get("/api/inventory", headers=h).json()
        assert any(i["typeId"] == 50 and i["mType"] == 2 for i in inventory["items"])

        async def count_owned():
            async with app.state.sessions() as db:
                return len(list(await db.scalars(select(OwnedItem))))

        assert client.portal.call(count_owned) == 1


def test_classified_pets_and_interior_are_not_wearable_but_shirt_is(app):
    with TestClient(app) as client:
        _, token, _ = setup_shop(client, app)
        h = auth(token)
        assert client.post("/api/admin/shops/admin/import-assets", headers=h).status_code == 200
        for key, ident in (
            ("admin1", 100),
            ("admin2", 2),
            ("admin3", 50),
            ("admin1", 2351),
        ):
            bought = client.post(
                f"/api/shops/{key}/buy", headers=h, json={"item_id": ident, "expected_price": 0}
            )
            assert bought.status_code == 200 and bought.json()["experience_awarded"] == 0
            inventory = client.get("/api/inventory", headers=h).json()
            owned = next(i for i in inventory["items"] if i["typeId"] == ident)
            equipped = client.post(
                "/api/inventory/equip", headers=h, json={"owned_item_id": owned["id"]}
            )
            assert equipped.status_code == (200 if ident == 100 else 422)
        assert (
            client.post(
                "/api/shops/admin1/buy", headers=h, json={"item_id": 100, "expected_price": 0}
            ).status_code
            == 409
        )


def test_walking_only_graphics_have_centered_visible_preview_frames(app):
    with TestClient(app) as client:
        for ident in (2351, 2387, 2458):
            info = metadata()[str(ident)]["Walking"]
            assert info["bounds"][1] > info["bounds"][0] and info["bounds"][3] > info["bounds"][2]
            for role in ("Display", "preview"):
                r = client.get(f"/api/shop-assets/{role}/{ident}.swf")
                assert r.status_code == 200
                body = zlib.decompress(r.content[8:])
                assert b"gotoAndStop" in body
                assert f"mlBigItem{ident}".encode() in body
            assert client.get(f"/api/shop-assets/raw/{ident}.swf").status_code == 200
        assert metadata()["2387"]["Walking"]["preview_frame"] > 1


def test_classification_is_complete_and_wearable_slots_have_full_animations():
    data = classification()
    assert {int(i) for i in data["items"]} == set(asset_index())
    for ident, row in data["items"].items():
        assert row["family"] == data["groups"][row["category"]]["family"]
        if row["main_type"] == 1 and row["inventory_category"]:
            assert "standing" in asset_index()[int(ident)]
