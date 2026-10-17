import json

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_multiplayer import account, auth, join
from test_profiles import reply
from test_shops import setup_shop
from test_world import extension, receive

from src.inventory.models import EquippedItem
from src.shops.world_shops import points


def test_room_point_binding_is_editable_and_checks_current_room_and_role(app):
    with TestClient(app) as client:
        ident, token, _ = setup_shop(client, app)
        h = auth(token)
        body = {
            "key": "test",
            "title": "Точка",
            "kind": "clothing",
            "points": ["mall.mcShopPoint_1"],
        }
        assert client.put("/api/admin/shops/test", headers=h, json=body).status_code == 200
        assert (
            client.get("/api/shop-points?room=mall", headers=h).json()["points"][0]["shop_key"]
            == "test"
        )
        assert client.post("/api/shop-points/mall.mcShopPoint_1/open", headers=h).status_code == 409
        with client.websocket_connect("/legacy/socket", headers=h) as ws:
            join(ws, "ShopAdmin")
            extension(ws, "rooms__jumpToRoom", nameId="Mall")
            for _ in range(3):
                message = receive(ws)
                if "joinOK" in message:
                    break
            app.state.world.connections[ident].state.update(x=50, y=400)
            assert (
                client.post("/api/shop-points/mall.mcShopPoint_1/open", headers=h).status_code
                == 409
            )
            # The original request must use the editable point binding, not Shop.room_key.
            extension(ws, "rooms__getStoreData", roomId=-1)
            assert reply(ws, "rooms__getStoreData")[0]["items"] == []
            app.state.world.connections[ident].state.update(x=386, y=359)
            assert (
                client.post("/api/shop-points/mall.mcShopPoint_1/open", headers=h).status_code
                == 200
            )
            extension(ws, "rooms__getStoreData", roomId=-1)
            assert reply(ws, "rooms__getStoreData")[0]["items"][0]["typeId"] == 1
            assert (
                client.post("/api/shop-points/spa.mcShopPoint_1/open", headers=h).status_code == 404
            )
        assert (
            client.put("/api/admin/shops/test", headers=h, json={**body, "points": []}).status_code
            == 200
        )
        assert client.get("/api/shop-points?room=mall", headers=h).json()["points"] == []
        assert (
            client.put(
                "/api/admin/shops/test", headers=h, json={**body, "points": ["unknown"]}
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/admin/shops/test", headers=h, json={**body, "admin_only": True}
            ).status_code
            == 200
        )
        _, regular = account(client, "PointVisitor", 7)
        assert (
            client.get("/api/shop-points?room=mall", headers=auth(regular)).json()["points"] == []
        )
        assert (
            client.post(
                "/api/shop-points/mall.mcShopPoint_1/open", headers=auth(regular)
            ).status_code
            == 404
        )
        assert len(points()) == 23


def test_item_metadata_and_offer_category_change_existing_inventory_and_worn_slot(app):
    with TestClient(app) as client:
        ident, token, offer = setup_shop(client, app, price=0)
        h = auth(token)
        # Use a normal wearable asset while preserving the shop fixture.
        item = {"id": 100, "name": "Рубашка", "main_type": 1, "inventory_category": 4}
        assert client.put("/api/admin/items/100", headers=h, json=item).status_code == 200
        category = client.post(
            "/api/admin/shops/test/categories", headers=h, json={"name": "Верх", "icon_id": 4}
        ).json()["id"]
        offer = {"item_id": 100, "category_id": category, "price": 0, "experience": 0}
        assert (
            client.put("/api/admin/shops/test/offers/100", headers=h, json=offer).status_code == 200
        )
        assert (
            client.post(
                "/api/shops/test/buy", headers=h, json={"item_id": 100, "expected_price": 0}
            ).status_code
            == 200
        )
        owned = client.get("/api/inventory", headers=h).json()["items"][0]["id"]
        assert (
            client.post(
                "/api/inventory/equip", headers=h, json={"owned_item_id": owned}
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/admin/items/100", headers=h, json={**item, "inventory_category": 1}
            ).status_code
            == 200
        )
        assert client.get("/api/inventory/equipped", headers=h).json()["items"][0]["pCat"] == 1

        async def worn_slot():
            async with app.state.sessions() as db:
                return await db.scalar(
                    select(EquippedItem.slot).where(EquippedItem.account_id == ident)
                )

        assert client.portal.call(worn_slot) == 1
        dest = client.post(
            "/api/admin/shops/test/categories",
            headers=h,
            json={"name": "Очки", "icon_id": 6, "inventory_category": 18},
        ).json()["id"]
        assert (
            client.put(
                "/api/admin/shops/test/offers/100", headers=h, json={**offer, "category_id": dest}
            ).status_code
            == 200
        )
        assert client.get("/api/inventory", headers=h).json()["items"][0]["pCat"] == 18
        assert client.portal.call(worn_slot) == 18
        assert (
            client.put(
                "/api/admin/items/100",
                headers=h,
                json={**item, "main_type": 2, "inventory_category": 0},
            ).status_code
            == 200
        )
        assert client.get("/api/inventory/equipped", headers=h).json()["items"] == []
        assert client.get("/api/inventory", headers=h).json()["items"][0]["mType"] == 2


def test_startup_seeds_public_shops_only_once_and_preserves_operator_edits(app):
    from src.config import Settings
    from src.main import create_app

    def defaults():
        return create_app(
            Settings(database_url=app.state.settings.database_url, bootstrap_defaults=True)
        )

    with TestClient(defaults()) as client:
        assert (
            client.post(
                "/api/admin/login", json={"username": "admin", "password": "admin"}
            ).status_code
            == 200
        )
        shops = client.get("/api/admin/shops").json()
        assert len(shops) == 17
        style = next(s for s in shops if s["key"] == "clothesstore")
        assert style["points"] == ["clothesstore.mcShopPoint_1"]
        catalog = client.get("/api/admin/shops/clothesstore/catalog").json()
        item = catalog["offers"][0]["item_id"]
        assert client.delete("/api/admin/shops/clothesstore/offers/" + str(item)).status_code == 204
        assert (
            client.put(
                "/api/admin/shops/clothesstore",
                json={
                    **{k: v for k, v in style.items() if k != "id"},
                    "title": "Мой магазин",
                    "points": [],
                },
            ).status_code
            == 200
        )
    with TestClient(defaults()) as client:
        client.post("/api/admin/login", json={"username": "admin", "password": "admin"})
        catalog = client.get("/api/admin/shops/clothesstore/catalog").json()
        assert catalog["shop"]["title"] == "Мой магазин" and catalog["shop"]["points"] == []
        assert item not in {o["item_id"] for o in catalog["offers"]}


def test_starter_objects_match_shop_families_and_existing_assets():
    from src.config import ROOT
    from src.shops.classification import classification
    from src.shops.service import asset_index

    defaults = json.loads(
        (ROOT.parent / "assets/catalogs/world-shops.json").read_text(encoding="utf-8")
    )
    allowed = {
        "furniturestore": {2},
        "jewelrystore": {3, 4},
        "bumagsstore": {6, 7},
        "bumagsfoodtoysstore": {8, 9, 11},
        "bumagspotionstore": {10},
    }
    items = classification()["items"]
    for shop in defaults["shops"]:
        assert shop["point"] in points()
        assert shop["items"] and len(shop["items"]) == len(set(shop["items"]))
        for ident in shop["items"]:
            assert ident in asset_index()
            assert items[str(ident)]["main_type"] in allowed.get(shop["key"], {1})
