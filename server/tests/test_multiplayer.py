import json
from xml.etree.ElementTree import fromstring
from xml.sax.saxutils import escape

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_world import extension, receive, send

from src.world.navigation import walkable


def account(client, name, color):
    assert (
        client.post(
            "/api/auth/registration-drafts",
            json={"username": name, "password": "Pass1234", "color_id": color},
        ).status_code
        == 201
    )
    result = client.post("/api/auth/register", json={"age": 12, "chat_mode": "open"})
    assert result.status_code == 201
    return result.json()["id"], client.cookies.get("mogobe_session")


def join(ws, name):
    send(ws, '<msg t="sys"><body action="verChk"/></msg>')
    assert fromstring(receive(ws)).find("body").get("action") == "apiOK"
    send(
        ws,
        f'<msg t="sys"><body action="login"><login><nick>{escape(name)}</nick>'
        "<pword>__MOGOBE_CURRENT_SESSION__</pword></login></body></msg>",
    )
    assert fromstring(receive(ws)).find("body").get("action") == "rmList"
    assert json.loads(receive(ws))["b"]["o"]["userName"] == name
    extension(ws, "user__joinFirstRoom")
    return fromstring(receive(ws)).find("body")


def auth(token):
    return {"Authorization": "Bearer " + token}


def moved(ws):
    send(
        ws,
        '<msg t="sys"><body action="setUvars" r="3"><vars>'
        '<var n="x" t="n">400</var><var n="y" t="n">392</var>'
        '<var n="AD" t="n">6</var></vars></body></msg>',
    )


def test_two_players_join_walk_chat_exit_and_reconnect(app):
    with TestClient(app) as client:
        first_id, first = account(client, "First_1", 3)
        second_id, second = account(client, "Второй_2", 7)
        with client.websocket_connect("/legacy/socket", headers=auth(first)) as a:
            initial = join(a, "First_1")
            assert len(initial.findall("uLs/u")) == 1
            with client.websocket_connect("/legacy/socket", headers=auth(second)) as b:
                snapshot = join(b, "Второй_2")
                assert {u.findtext("n") for u in snapshot.findall("uLs/u")} == {
                    "First_1",
                    "Второй_2",
                }
                assert {v.text for v in snapshot.findall('uLs/u/vars/var[@n="color"]')} == {
                    "3",
                    "7",
                }
                entry = fromstring(receive(a)).find("body")
                assert entry.get("action") == "uER" and int(entry.find("u").get("i")) == second_id
                moved(a)
                for peer in (a, b):
                    event = fromstring(receive(peer)).find("body")
                    assert event.get("action") == "uVarsUpdate"
                    assert int(event.find("user").get("id")) == first_id
                    assert float(event.find('vars/var[@n="x"]').text) > 350
                send(
                    b,
                    '<msg t="sys"><body action="pubMsg" r="3">'
                    "<txt>speak__Привет &amp; мир!</txt></body></msg>",
                )
                for peer in (a, b):
                    event = fromstring(receive(peer)).find("body")
                    assert (
                        event.get("action") == "pubMsg"
                        and event.findtext("txt") == "speak__Привет & мир!"
                    )
                    assert int(event.find("user").get("id")) == second_id
                # Delimiters in user text cannot choose another speaker or
                # invoke the original client's dynamic avatar actions.
                b_conn = app.state.world.connections[second_id]
                b_conn.last_chat = 0
                send(
                    b,
                    '<msg t="sys"><body action="pubMsg"><txt>speak__hello__999</txt></body></msg>',
                )
                for peer in (a, b):
                    event = fromstring(receive(peer)).find("body")
                    assert event.findtext("txt") == "speak__hello_999"
                    assert int(event.find("user").get("id")) == second_id
            leave = fromstring(receive(a)).find("body")
            assert (
                leave.get("action") == "userGone" and int(leave.find("user").get("id")) == second_id
            )
            with client.websocket_connect("/legacy/socket", headers=auth(second)) as b:
                again = join(b, "Второй_2")
                assert walkable(
                    "novograd",
                    float(again.find('uLs/u/vars/var[@n="x"]').text),
                    float(again.find('uLs/u/vars/var[@n="y"]').text),
                )
                assert len(again.findall("uLs/u")) == 2
                assert fromstring(receive(a)).find("body").get("action") == "uER"
                extension(a, "user__getMyMoney")
                assert json.loads(receive(a))["b"]["o"]["userId"] == first_id
        assert app.state.world.connections == {} and app.state.world_players == {}


def test_same_account_cannot_replace_active_connection_or_rotate_session(app):
    with TestClient(app) as client:
        account_id, token = account(client, "Могоби_1", 5)
        client.cookies.clear()
        assert (
            client.post(
                "/api/auth/login", json={"username": "Могоби_1", "password": "Pass1234"}
            ).status_code
            == 200
        )
        independent = client.cookies.get("mogobe_session")
        assert independent != token
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as original:
            join(original, "Могоби_1")
            # Both a shared token and an independently issued token are guarded
            # by account identity, not by a cookie or a frontend flag.
            for candidate in (token, independent):
                with client.websocket_connect(
                    "/legacy/socket", headers=auth(candidate)
                ) as duplicate:
                    with pytest.raises(WebSocketDisconnect) as denied:
                        receive(duplicate)
                    assert denied.value.code == 4009
            result = client.post(
                "/api/auth/login",
                json={"username": "Могоби_1", "password": "Pass1234"},
                headers=auth(token),
            )
            assert result.status_code == 409 and "уже" in result.json()["detail"]
            for path in ("/legacy/login", "/legacy/resume"):
                result = client.post(
                    path, json={"username": "Могоби_1", "password": "Pass1234"}, headers=auth(token)
                )
                reply = fromstring(result.text).find("Login")
                assert reply.get("status") == "7" and "уже" in reply.get("message")
            assert client.get("/api/auth/me", headers=auth(token)).json()["id"] == account_id
            moved(original)
            assert fromstring(receive(original)).find("body").get("action") == "uVarsUpdate"
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as reconnected:
            assert join(reconnected, "Могоби_1").get("action") == "joinOK"


def test_pending_connection_claim_and_invalid_peer_release(app):
    with TestClient(app) as client:
        _, token = account(client, "Могоби_1", 5)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as pending:
            with client.websocket_connect("/legacy/socket", headers=auth(token)) as duplicate:
                with pytest.raises(WebSocketDisconnect) as denied:
                    receive(duplicate)
                assert denied.value.code == 4009
            join(pending, "Могоби_1")
            send(
                pending,
                '<msg t="sys"><body action="setUvars"><vars>'
                '<var n="x" t="n">nan</var><var n="y" t="n">392</var></vars></body></msg>',
            )
            with pytest.raises(WebSocketDisconnect):
                receive(pending)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as reconnected:
            assert join(reconnected, "Могоби_1").get("action") == "joinOK"


async def test_simultaneous_claims_and_session_rotation_are_serialized():
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException

    from src.world.hub import WorldHub

    hub = WorldHub()
    first = SimpleNamespace(account=SimpleNamespace(id=1), room=None)
    second = SimpleNamespace(account=SimpleNamespace(id=1), room=None)
    async with hub.login_guard(1):
        claim = asyncio.create_task(hub.claim(first))
        await asyncio.sleep(0)
        assert not claim.done()
    await claim
    with pytest.raises(HTTPException) as denied:
        await hub.claim(second)
    assert denied.value.status_code == 409
    hub.release(second)
    assert hub.connections[1] is first
    hub.release(first)
    await hub.claim(second)
    assert hub.connections[1] is second
