import json
from xml.etree.ElementTree import fromstring

from fastapi.testclient import TestClient
from test_multiplayer import account, auth, join
from test_world import extension, receive

from src.inventory import service
from src.shops.models import Item, OwnedItem


def seed(client, app, ident):
    async def create():
        async with app.state.sessions() as db:
            for item in (100, 101, 20):
                if await db.get(Item, item) is None:
                    db.add(Item(id=item, name=str(item), main_type=1, inventory_category=4))
            await db.flush()
            owned = [OwnedItem(account_id=ident, item_id=i) for i in (100, 101, 20)]
            db.add_all(owned)
            await db.commit()
            return [i.id for i in owned]

    return client.portal.call(create)


def test_outfit_ownership_replacement_and_persistence(app):
    with TestClient(app) as client:
        first, token = account(client, "Wardrobe", 3)
        ids = seed(client, app, first)
        second, other = account(client, "OtherWear", 7)
        other_ids = seed(client, app, second)
        h = auth(token)

        def change(action, ident):
            return client.post("/api/inventory/" + action, headers=h, json={"owned_item_id": ident})

        assert change("equip", other_ids[0]).status_code == 404
        assert change("equip", ids[0]).json()["items"][0]["typeId"] == 100
        assert change("equip", ids[1]).json()["items"][0]["typeId"] == 101
        assert change("unequip", ids[0]).json()["items"][0]["typeId"] == 101
        assert client.get("/api/inventory/equipped", headers=auth(other)).json()["items"] == []
        assert (
            client.get("/api/social/profiles/" + str(first), headers=h).json()["items"][0]["typeId"]
            == 101
        )
        # Reconnect snapshot must carry the persisted outfit before avatar loads.
        with client.websocket_connect("/legacy/socket", headers=h) as ws:
            snapshot = join(ws, "Wardrobe")
            items = snapshot.find(f'uLs/u[@i="{first}"]/vars/var[@n="items"]')
            assert json.loads(items.text)[0]["typeId"] == 101
        assert change("unequip", ids[1]).json()["items"] == []
        assert len(client.get("/api/inventory", headers=h).json()["items"]) == 3


def test_original_inventory_equip_sync_and_unequip_protocol(app):
    with TestClient(app) as client:
        first, token = account(client, "Wardrobe", 3)
        ids = seed(client, app, first)
        _, other = account(client, "Observer", 7)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as a:
            join(a, "Wardrobe")
            with client.websocket_connect("/legacy/socket", headers=auth(other)) as b:
                join(b, "Observer")
                receive(a)
                extension(a, "user__setInUseItem", items=[{"id": 999999}])
                failure = fromstring(receive(a)).find("body")
                assert failure.get("action") == "pubMsg"
                assert "не принадлежит" in failure.findtext("txt")
                assert (
                    client.get("/api/inventory/equipped", headers=auth(token)).json()["items"] == []
                )
                # Forged category and graphic ID are ignored: only owned ID is used.
                extension(
                    a, "user__setInUseItem", items=[{"id": ids[0], "typeId": 999999, "pCat": 1}]
                )
                own = fromstring(receive(a)).find("body")
                remote = fromstring(receive(b)).find("body")
                assert own.get("action") == remote.get("action") == "uVarsUpdate"
                data = json.loads(remote.find('vars/var[@n="items"]').text)
                assert data[0]["typeId"] == 100 and data[0]["pCat"] == 4
                assert json.loads(receive(a))["b"]["o"]["_cmd"] == "user__setInUseItem"
                extension(a, "user__getInventoryItems", mainType=1, placeCategorys=[4])
                items = json.loads(receive(a))["b"]["o"]["items"]
                assert {i["typeId"] for i in items} == {101, 20}
                extension(a, "user__getInventoryItems", mainType=1, placeCategorys=[3])
                assert json.loads(receive(a))["b"]["o"]["items"] == []
                # Original MyCardPopup sends split button names as strings.
                extension(a, "user__getInventoryItems", mainType=1, placeCategorys=["4", "8"])
                assert {i["typeId"] for i in json.loads(receive(a))["b"]["o"]["items"]} == {101, 20}
                extension(a, "user__getInventoryItems", mainType="1", placeCategorys=["3", "7"])
                assert json.loads(receive(a))["b"]["o"]["items"] == []
                extension(a, "user__getInventoryItems", mainType=True, placeCategorys=["4"])
                assert json.loads(receive(a))["b"]["o"]["items"] == []
                extension(a, "user__getInventoryItems", mainType=1, placeCategorys=["4", "invalid"])
                assert json.loads(receive(a))["b"]["o"]["items"] == []
                extension(a, "user__setNotInUseItem", items=[{"id": ids[0]}])
                assert (
                    json.loads(fromstring(receive(b)).find('body/vars/var[@n="items"]').text) == []
                )
                receive(a)
                assert json.loads(receive(a))["b"]["o"]["_cmd"] == "user__setNotInUseItem"


def test_batch_validation_is_atomic(app):
    with TestClient(app) as client:
        first, token = account(client, "Wardrobe", 3)
        ids = seed(client, app, first)
        h = auth(token)
        assert (
            client.post(
                "/api/inventory/equip", headers=h, json={"owned_item_id": ids[0]}
            ).status_code
            == 200
        )

        async def invalid():
            import pytest
            from fastapi import HTTPException

            async with app.state.sessions() as db:
                with pytest.raises(HTTPException):
                    await service.change(db, first, [ids[1], 999999], wear=True)

        client.portal.call(invalid)
        assert client.get("/api/inventory/equipped", headers=h).json()["items"][0]["typeId"] == 100
        assert (
            client.post("/api/inventory/equip", headers=h, json={"owned_item_id": True}).status_code
            == 422
        )
