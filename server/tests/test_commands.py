import json
from xml.etree.ElementTree import fromstring

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_multiplayer import account, auth, join
from test_profiles import reply
from test_progression import until
from test_shops import setup_shop
from test_world import send

from src.admin.commands import MAX_COINS, alert, give


def chat(ws, text):
    send(ws, '<msg t="sys"><body action="pubMsg"><txt>speak__' + text + "</txt></body></msg>")


def test_give_optional_recipient_including_offline_and_coins_limit(app):
    with TestClient(app) as client:
        admin, token, _ = setup_shop(client, app)
        target, other = account(client, "Другой__2", 7)
        client.portal.call(give, app, admin, "/give coins 50")
        client.portal.call(give, app, admin, "/give exp 1500 другой__2")
        client.portal.call(give, app, admin, "/give coins 123 другой__2")
        client.portal.call(give, app, admin, "/give item 1 другой__2")
        assert client.get("/api/inventory", headers=auth(other)).json()["coins"] == 123
        assert client.get("/api/inventory", headers=auth(other)).json()["items"][0]["typeId"] == 1
        assert client.get("/api/inventory", headers=auth(token)).json() == {
            "items": [],
            "coins": 50,
        }
        assert (
            client.get("/api/social/profiles/" + str(target), headers=auth(other)).json()["score"]
            == 1500
        )
        with pytest.raises(HTTPException) as duplicate:
            client.portal.call(give, app, admin, "/give item 1 Другой__2")
        assert duplicate.value.status_code == 409
        client.portal.call(give, app, admin, f"/give coins {MAX_COINS - 123} Другой__2")
        with pytest.raises(HTTPException) as overflow:
            client.portal.call(give, app, admin, "/give coins 1 Другой__2")
        assert overflow.value.status_code == 409
        assert client.get("/api/inventory", headers=auth(other)).json()["coins"] == MAX_COINS
        for command in [
            "/give item 1 ShopAdmin",
            "/give coins 1 ShopAdmin",
            "/give exp 1 ShopAdmin",
        ]:
            with pytest.raises(HTTPException) as denied:
                client.portal.call(give, app, target, command)
            assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as missing:
            client.portal.call(give, app, admin, "/give coins 1 MissingUser")
        assert missing.value.status_code == 404


def test_live_target_receives_original_score_popup_and_authoritative_coins(app):
    with TestClient(app) as client:
        admin, token, _ = setup_shop(client, app)
        target, other = account(client, "Другой__2", 7)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as a:
            join(a, "ShopAdmin")
            with client.websocket_connect("/legacy/socket", headers=auth(other)) as b:
                join(b, "Другой__2")
                from test_world import receive

                receive(a)
                # Full chat path preserves a valid double underscore in the recipient.
                chat(a, "/give exp 1500 другой__2")
                b_frames = until(
                    b,
                    lambda x: (
                        x.startswith("{") and json.loads(x)["b"]["o"]["_cmd"] == "shop__changed"
                    ),
                )
                assert any(
                    x.startswith("{")
                    and json.loads(x)["b"]["o"]["_cmd"] == "user__worldScoreChange"
                    for x in b_frames
                )
                a_frames = until(a, lambda x: "Начислено опыта: 1500" in x)
                assert not any(
                    x.startswith("{")
                    and json.loads(x)["b"]["o"]["_cmd"] == "user__worldScoreChange"
                    for x in a_frames
                )
                # Clear only the sender cooldown; no wall-clock sleeps in protocol tests.
                app.state.world.connections[admin].last_chat = 0
                chat(a, "/give coins 75 Другой__2")
                b_frames = until(
                    b,
                    lambda x: (
                        x.startswith("{") and json.loads(x)["b"]["o"]["_cmd"] == "shop__changed"
                    ),
                )
                assert any("mo_1" in x and "75" in x for x in b_frames if x.startswith("<"))
                assert client.get("/api/inventory", headers=auth(other)).json()["coins"] == 75
                assert (
                    client.get("/api/social/profiles/" + str(target), headers=auth(other)).json()[
                        "score"
                    ]
                    == 1500
                )


def test_help_is_available_to_everyone_and_tracks_current_role(app):
    with TestClient(app) as client:
        _, token, _ = setup_shop(client, app)
        ident, other = account(client, "Ordinary", 7)

        def commands(token):
            return client.get("/api/world/commands", headers=auth(token)).json()["commands"]

        regular = commands(other)
        assert {c["syntax"] for c in regular} == {
            "/help",
            "/room ключ",
            "/shop ключ",
            "/online",
            "/exit",
        }
        assert all(not c["admin_only"] for c in regular)
        admin = commands(token)
        assert {
            "/give coins N [ник]",
            "/give exp N [ник]",
            "/give item ID [ник]",
            "/alert текст",
        } <= {c["syntax"] for c in admin}
        assert (
            client.put(
                f"/api/admin/accounts/{ident}/admin", headers=auth(token), json={"is_admin": True}
            ).status_code
            == 200
        )
        assert any(c["syntax"] == "/alert текст" for c in commands(other))
        assert (
            client.put(
                f"/api/admin/accounts/{ident}/admin", headers=auth(token), json={"is_admin": False}
            ).status_code
            == 200
        )
        assert not any(c["admin_only"] for c in commands(other))


def test_room_and_shop_commands_are_public_but_admin_shops_stay_restricted(app):
    with TestClient(app) as client:
        _, token, _ = setup_shop(client, app, restricted=True)
        admin = auth(token)
        assert (
            client.put(
                "/api/admin/shops/public",
                headers=admin,
                json={"key": "public", "title": "Обычный магазин"},
            ).status_code
            == 200
        )
        _, regular = account(client, "Ordinary", 7)
        with client.websocket_connect("/legacy/socket", headers=auth(regular)) as ws:
            join(ws, "Ordinary")
            chat(ws, "/shop public")
            assert reply(ws, "shop__open")[0]["key"] == "public"
            app.state.world.connections[
                next(
                    i
                    for i, p in app.state.world.connections.items()
                    if p.account.username == "Ordinary"
                )
            ].last_chat = 0
            chat(ws, "/shop test")
            until(ws, lambda x: "Магазин недоступен" in x)
            peer = next(
                p for p in app.state.world.connections.values() if p.account.username == "Ordinary"
            )
            peer.last_chat = 0
            chat(ws, "/room InfoBoard")
            frames = until(
                ws,
                lambda x: (
                    x.startswith("<") and fromstring(x).find("body").get("action") == "joinOK"
                ),
            )
            assert fromstring(frames[-1]).find("body").get("r") == "2"


def test_alert_broadcasts_across_rooms_and_rechecks_admin(app):
    with TestClient(app) as client:
        admin, token, _ = setup_shop(client, app)
        ordinary, other = account(client, "Ordinary", 7)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as a:
            join(a, "ShopAdmin")
            with client.websocket_connect("/legacy/socket", headers=auth(other)) as b:
                join(b, "Ordinary")
                peer = app.state.world.connections[ordinary]
                client.portal.call(peer.join, 2)
                result = client.portal.call(
                    alert, app, admin, "/alert Всем привет__тест &amp; проверка!"
                )
                assert result.endswith("2")
                for ws in (a, b):
                    message, _ = reply(ws, "msg__sendPublicMsg")
                    assert message["messageType"] == "alert"
                    assert message["text"] == "Всем привет__тест &amp; проверка!"
                    assert message["sender"] == "ShopAdmin"
                with pytest.raises(HTTPException) as denied:
                    client.portal.call(alert, app, ordinary, "/alert Нельзя")
                assert denied.value.status_code == 403
        for command in ["/alert", "/alert ", "/alert " + ("x" * 231)]:
            with pytest.raises(HTTPException) as invalid:
                client.portal.call(alert, app, admin, command)
            assert invalid.value.status_code == 422
