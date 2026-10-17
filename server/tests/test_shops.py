import asyncio
import json
from xml.etree.ElementTree import fromstring

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_multiplayer import account, auth, join
from test_profiles import reply
from test_world import extension, receive, send

from src.auth.models import Account
from src.config import Settings
from src.main import create_app
from src.shops.models import Offer, OwnedItem, Wallet

ADMIN = "/api/admin/shops"


def setup_shop(client, app, *, restricted=False, price=10, stock=1):
    ident, token = account(client, "ShopAdmin", 3)

    async def grant():
        async with app.state.sessions() as db:
            await db.execute(update(Account).where(Account.id == ident).values(is_admin=True))
            await db.commit()

    client.portal.call(grant)
    headers = auth(token)
    assert (
        client.put(
            ADMIN + "/items/1",
            headers=headers,
            json={"id": 1, "name": "Тестовый предмет", "main_type": 1},
        ).status_code
        == 200
    )
    assert (
        client.put(
            ADMIN + "/test",
            headers=headers,
            json={
                "key": "test",
                "title": "Тестовый магазин",
                "admin_only": restricted,
                "room_key": "clothesstore",
            },
        ).status_code
        == 200
    )
    category = client.post(
        ADMIN + "/test/categories", headers=headers, json={"name": "Вещи", "icon_id": 4}
    ).json()
    offer = {"item_id": 1, "category_id": category["id"], "price": price, "stock": stock}
    assert client.put(ADMIN + "/test/offers/1", headers=headers, json=offer).status_code == 200
    return ident, token, offer


def test_admin_permissions_and_no_public_self_promotion(app):
    with TestClient(app) as client:
        assert client.get(ADMIN).status_code == 401
        ident, token = account(client, "ShopUser", 3)
        assert client.get(ADMIN, headers=auth(token)).status_code == 403
        assert (
            client.put(
                ADMIN + "/test",
                headers=auth(token),
                json={"key": "test", "title": "X", "is_admin": True},
            ).status_code
            == 403
        )
        assert (
            client.post(
                ADMIN + "/login", json={"username": "ShopUser", "password": "Pass1234"}
            ).status_code
            == 403
        )
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            join(ws, "ShopUser")
            extension(ws, "user__getUserCardInfo", userId=ident)
            assert reply(ws, "user__getUserCardInfo")[0]["member"] is False


def test_live_catalog_price_stock_purchase_inventory_and_restart(app):
    with TestClient(app) as client:
        admin_id, admin_token, offer = setup_shop(client, app)
        _, token = account(client, "ShopBuyer", 7)
        ah, bh = auth(admin_token), auth(token)
        assert client.get("/api/shops/test", headers=bh).json()["items"][0]["price"] == 10
        assert (
            client.post(
                "/api/shops/test/buy", headers=bh, json={"item_id": 1, "expected_price": 10}
            ).status_code
            == 409
        )
        assert client.get(ADMIN + "/test/catalog", headers=ah).json()["offers"][0]["stock"] == 1
        assert (
            client.post(
                ADMIN + "/accounts/ShopBuyer/balance", headers=ah, json={"coins": 50}
            ).status_code
            == 200
        )
        assert (
            client.put(
                ADMIN + "/test/offers/1", headers=ah, json={**offer, "price": 20}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/shops/test/buy", headers=bh, json={"item_id": 1, "expected_price": 10}
            ).status_code
            == 409
        )
        assert client.get("/api/shops/test", headers=bh).json()["items"][0]["price"] == 20
        assert (
            client.post(
                "/api/shops/test/buy",
                headers=bh,
                json={"item_id": 1, "expected_price": 20, "coins": 999},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/shops/test/buy", headers=bh, json={"item_id": 1, "expected_price": 20}
            ).json()["coins"]
            == 30
        )
        assert (
            client.post(
                "/api/shops/test/buy", headers=bh, json={"item_id": 1, "expected_price": 20}
            ).status_code
            == 409
        )
        assert client.get("/api/inventory", headers=bh).json()["items"][0]["typeId"] == 1
        assert client.get("/api/inventory", headers=ah).json()["items"] == []
        restarted = create_app(Settings(database_url=app.state.settings.database_url))
        with TestClient(restarted) as other:
            assert other.get("/api/inventory", headers=bh).json()["coins"] == 30
            assert other.get(ADMIN + "/test/catalog", headers=ah).json()["offers"][0]["stock"] == 0
        assert client.get(ADMIN + "/items", headers=ah).json()[0]["name"] == "Тестовый предмет"
        assert client.delete(ADMIN + "/test/offers/1", headers=ah).status_code == 204
        assert client.get("/api/shops/test", headers=bh).json()["items"] == []
        assert client.get("/api/inventory", headers=bh).json()["items"][0]["typeId"] == 1


def test_admin_shop_badge_session_login_while_playing_and_revoke(app):
    with TestClient(app) as client:
        ident, token, offer = setup_shop(client, app, restricted=True, price=0)
        _, regular = account(client, "ShopOther", 7)
        assert client.get("/api/shops/test", headers=auth(regular)).status_code == 404
        assert (
            client.post(
                "/api/shops/test/buy",
                headers=auth(regular),
                json={"item_id": 1, "expected_price": 0},
            ).status_code
            == 404
        )
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            join(ws, "ShopAdmin")
            extension(ws, "user__getUserCardInfo", userId=ident)
            assert reply(ws, "user__getUserCardInfo")[0]["member"] is True
            # A separate admin browser login does not rotate the game's token.
            client.cookies.clear()
            assert (
                client.post(
                    ADMIN + "/login", json={"username": "ShopAdmin", "password": "Pass1234"}
                ).status_code
                == 200
            )
            send(ws, '<msg t="sys"><body action="pubMsg"><txt>speak__/shop test</txt></body></msg>')
            data = json.loads(receive(ws))["b"]["o"]
            assert data == {"_cmd": "shop__open", "key": "test"}

            async def revoke():
                async with app.state.sessions() as db:
                    await db.execute(
                        update(Account).where(Account.id == ident).values(is_admin=False)
                    )
                    await db.commit()

            client.portal.call(revoke)
            assert client.get("/api/shops/test", headers=auth(token)).status_code == 404
            assert client.get(ADMIN, headers=auth(token)).status_code == 403
            extension(ws, "user__getUserCardInfo", userId=ident)
            assert reply(ws, "user__getUserCardInfo")[0]["member"] is False


def test_category_isolation_invalid_graphic_price_and_closed_shops(app):
    with TestClient(app) as client:
        _, token, offer = setup_shop(client, app)
        h = auth(token)
        assert (
            client.put(
                ADMIN + "/second", headers=h, json={"key": "second", "title": "Другой"}
            ).status_code
            == 200
        )
        assert client.put(ADMIN + "/second/offers/1", headers=h, json=offer).status_code == 422
        assert (
            client.put(
                ADMIN + "/items/999999", headers=h, json={"id": 999999, "name": "X"}
            ).status_code
            == 422
        )
        assert (
            client.put(ADMIN + "/test/offers/1", headers=h, json={**offer, "price": -1}).status_code
            == 422
        )
        assert (
            client.put(ADMIN + "/test/offers/1", headers=h, json={**offer, "stock": -1}).status_code
            == 422
        )
        assert (
            client.put(
                ADMIN + "/test", headers=h, json={"key": "test", "title": "Тест", "enabled": False}
            ).status_code
            == 200
        )
        assert client.get("/api/shops/test", headers=h).status_code == 404
        assert (
            client.post(
                "/api/shops/test/buy", headers=h, json={"item_id": 1, "expected_price": 10}
            ).status_code
            == 404
        )


def test_graphics_are_self_contained_and_export_compatibility_classes(app):
    with TestClient(app) as client:
        _, token, offer = setup_shop(client, app)
        category = client.get("/api/shops/test", headers=auth(token)).json()["categories"][0][
            "typeId"
        ]
        for path, name in [
            ("Display/1", "btnItem1"),
            ("InUse/1", "mlIconSItem1"),
            (f"Cats/{category}", f"btnCat{category}"),
        ]:
            result = client.get("/api/shop-assets/" + path + ".swf")
            assert result.status_code == 200
            import zlib

            assert name.encode() in zlib.decompress(result.content[8:])
        assert client.get("/api/shop-assets/raw/1.swf").status_code == 200
        assert client.get("/api/shop-assets/preview/1.swf").status_code == 200
        assert client.get("/api/shop-assets/Display/999999.swf").status_code == 404
        assert client.get("/api/shop-assets/Other/1.swf").status_code == 404
        assert client.get("/admin/shops").status_code == 200


@pytest.mark.asyncio
async def test_concurrent_last_item_is_sold_once(client, app):
    async def register(name):
        client.cookies.clear()
        assert (
            await client.post(
                "/api/auth/registration-drafts",
                json={"username": name, "password": "Pass1234", "color_id": 3},
            )
        ).status_code == 201
        r = await client.post("/api/auth/register", json={"age": 12, "chat_mode": "open"})
        assert r.status_code == 201
        return r.json()["id"], client.cookies.get("mogobe_session")

    admin_id, admin = await register("RaceAdmin")
    a, ta = await register("RaceBuyer1")
    b, tb = await register("RaceBuyer2")
    async with app.state.sessions() as db:
        await db.execute(update(Account).where(Account.id == admin_id).values(is_admin=True))
        db.add_all([Wallet(account_id=a, coins=50), Wallet(account_id=b, coins=50)])
        await db.commit()
    h = auth(admin)
    await client.put(ADMIN + "/items/1", headers=h, json={"id": 1, "name": "X"})
    await client.put(ADMIN + "/race", headers=h, json={"key": "race", "title": "X"})
    category = (
        await client.post(ADMIN + "/race/categories", headers=h, json={"name": "X", "icon_id": 4})
    ).json()["id"]
    await client.put(
        ADMIN + "/race/offers/1",
        headers=h,
        json={"item_id": 1, "category_id": category, "price": 10, "stock": 1},
    )

    async def buy(token):
        return await client.post(
            "/api/shops/race/buy", headers=auth(token), json={"item_id": 1, "expected_price": 10}
        )

    results = await asyncio.gather(buy(ta), buy(tb))
    assert sorted(r.status_code for r in results) == [200, 409]
    async with app.state.sessions() as db:
        assert len(list(await db.scalars(select(OwnedItem)))) == 1
        assert sum(await db.scalars(select(Wallet.coins))) == 90
        assert await db.scalar(select(Offer.stock)) == 0


def test_physical_shop_uses_authoritative_room_and_refuses_unquoted_purchase(app):
    with TestClient(app) as client:
        ident, token, offer = setup_shop(client, app, price=0)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            join(ws, "ShopAdmin")
            extension(ws, "user__buyItem", itemId=1)
            assert reply(ws, "user__buyItem")[0]["status"] is False
            extension(ws, "rooms__getStoreData", roomId=999)
            assert reply(ws, "rooms__getStoreData")[0]["items"] == []
            extension(ws, "rooms__jumpToRoom", nameId="ClothesStore")
            assert fromstring(receive(ws)).find("body").get("action") == "joinOK"
            extension(ws, "rooms__getStoreData", roomId=999)
            assert reply(ws, "rooms__getStoreData")[0]["items"][0]["typeId"] == 1
            extension(ws, "user__buyItem", itemId=1)
            # Wallet and shop events can precede the purchase response.
            while True:
                raw = receive(ws)
                if raw.startswith("{"):
                    data = json.loads(raw)["b"]["o"]
                    if data["_cmd"] == "user__buyItem":
                        assert data["status"] is True
                        break
            assert (
                client.get("/api/inventory", headers=auth(token)).json()["items"][0]["typeId"] == 1
            )


def test_category_icon_change_gets_new_linkage_without_client_cache_staleness(app):
    with TestClient(app) as client:
        _, token, offer = setup_shop(client, app)
        h = auth(token)
        before = client.get("/api/shops/test", headers=h).json()
        old = before["categories"][0]["typeId"]
        assert client.get(f"/api/shop-assets/Cats/{old}.swf").status_code == 200
        assert (
            client.put(
                ADMIN + f"/test/categories/{offer['category_id']}",
                headers=h,
                json={"name": "Верх", "icon_id": 5},
            ).status_code
            == 200
        )
        after = client.get("/api/shops/test", headers=h).json()
        new = after["categories"][0]["typeId"]
        assert new != old and after["items"][0]["sCat"] == new
        import zlib

        data = client.get(f"/api/shop-assets/Cats/{new}.swf")
        assert data.status_code == 200 and f"btnCat{new}".encode() in zlib.decompress(
            data.content[8:]
        )
