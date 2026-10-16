import json
import sqlite3
from xml.etree.ElementTree import fromstring

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from starlette.websockets import WebSocketDisconnect

from alembic import command
from src.config import ROOT
from src.world.navigation import path_to, walkable


def register(client):
    assert (
        client.post(
            "/api/auth/registration-drafts",
            json={"username": "Мого_12", "password": "Pass1234", "color_id": 7},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/auth/register",
            json={
                "age": 12,
                "chat_mode": "closed",
                "accepted_terms": False,
                "newsletter": False,
                "parent_email": None,
            },
        ).status_code
        == 201
    )


def send(ws, message):
    ws.send_bytes(message.encode("utf-8") + b"\0")


def receive(ws):
    return ws.receive_bytes().decode("utf-8").removesuffix("\0")


def extension(ws, command, **params):
    send(ws, json.dumps({"t": "xt", "b": {"c": command, "p": params}}))


def login(ws):
    send(ws, '<msg t="sys"><body action="verChk" r="0"><ver v="165"/></body></msg>')
    assert fromstring(receive(ws)).find("body").get("action") == "apiOK"
    # A split multibyte UTF-8 code point must survive separate Ruffle frames.
    packet = (
        '<msg t="sys"><body action="login" r="0"><login><nick>Мого_12</nick>'
        "<pword>__MOGOBE_CURRENT_SESSION__</pword></login></body></msg>\0"
    ).encode()
    index = packet.index("М".encode()) + 1
    ws.send_bytes(packet[:index])
    ws.send_bytes(packet[index:])
    rooms = fromstring(receive(ws)).findall("body/rmList/rm")
    names = {room.findtext("n") for room in rooms}
    assert {"InfoBoard", "Novograd", "Severburg", "Mall", "Port"} <= names
    assert len(rooms) == len(names)
    reply = json.loads(receive(ws))["b"]["o"]
    assert reply["_cmd"] == "login" and reply["userName"] == "Мого_12"
    extension(ws, "user__joinFirstRoom")
    body = fromstring(receive(ws)).find("body")
    assert body.get("action") == "joinOK" and body.get("r") == "3"
    variables = {node.get("n"): node.text for node in body.findall("uLs/u/vars/var")}
    assert variables["color"] == "7"
    assert body.findtext("uLs/u/n") == "Мого_12"
    return float(variables["x"]), float(variables["y"])


def test_novograd_login_walk_reconnect_and_invalid_room_requests(app):
    with TestClient(app) as client:
        register(client)
        assert client.get("/api/world/me").json()["entered"] is False
        with client.websocket_connect("/legacy/socket") as ws:
            spawn = login(ws)
            assert walkable("novograd", *spawn)
            send(
                ws,
                '<msg t="sys"><body action="setUvars" r="3"><vars>'
                '<var n="x" t="n">560</var><var n="y" t="n">392</var>'
                "</vars></body></msg>",
            )
            assert fromstring(receive(ws)).find("body").get("action") == "uVarsUpdate"
            state = client.get("/api/world/me").json()
            moved = (state["x"], state["y"])
            assert moved != spawn and walkable("novograd", *moved)
            assert state["color_id"] == 7 and state["room"] == "novograd"
            extension(ws, "rooms__jumpToRoom", roomId=1)
            assert json.loads(receive(ws))["b"]["o"]["errorId"] == 69
            extension(ws, "rooms__changeRoom", gCId=3)
            assert json.loads(receive(ws))["b"]["o"]["errorId"] == 69
        with client.websocket_connect("/legacy/socket") as ws:
            assert walkable("novograd", *login(ws))
            assert client.post("/api/auth/logout").status_code == 204
            extension(ws, "user__getMyMoney")
            with pytest.raises(WebSocketDisconnect):
                receive(ws)


def test_world_requires_session_and_rejects_foreign_origin(app):
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/legacy/socket"):
                pass
        register(client)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/legacy/socket", headers={"Origin": "https://other.test"}
            ):
                pass


@pytest.mark.parametrize("values", [("nan", "392"), ("900", "392"), ("400", "inf")])
def test_invalid_positions_do_not_change_saved_state(app, values):
    with TestClient(app) as client:
        register(client)
        with client.websocket_connect("/legacy/socket") as ws:
            login(ws)
            send(
                ws,
                '<msg t="sys"><body action="setUvars" r="3"><vars>'
                f'<var n="x" t="n">{values[0]}</var><var n="y" t="n">{values[1]}</var>'
                "</vars></body></msg>",
            )
            with pytest.raises(WebSocketDisconnect):
                receive(ws)
        state = client.get("/api/world/me").json()
        assert state["entered"] is False and state["x"] is None and state["y"] is None
        with client.websocket_connect("/legacy/socket") as ws:
            assert walkable("novograd", *login(ws))


def test_walking_mask_route_avoids_scenery():
    route = path_to("infoboard", (260, 392), (0, 0))
    assert all(walkable("infoboard", *point) for point in route)
    assert route[-1] != [0, 0]
    assert all(abs(a[0] - b[0]) <= 8 and abs(a[1] - b[1]) <= 8 for a, b in zip(route, route[1:]))


def test_position_table_removed_without_changing_accounts_or_sessions(app):
    with TestClient(app) as client:
        register(client)
        config = Config(str(ROOT / "alembic.ini"))
        command.downgrade(config, "c918a202ef70")
        database = make_url(app.state.settings.database_url).database
        with sqlite3.connect(database) as db:
            account_id = db.execute("SELECT id FROM auth_account").fetchone()[0]
            db.execute("INSERT INTO world_player VALUES (?,2,500,396)", (account_id,))
            before = db.execute("SELECT count(*) FROM auth_session").fetchone()[0]
        command.upgrade(config, "head")
        with sqlite3.connect(database) as db:
            assert (
                db.execute("SELECT name FROM sqlite_master WHERE name='world_player'").fetchone()
                is None
            )
            assert db.execute("SELECT count(*) FROM auth_session").fetchone()[0] == before
        assert client.get("/api/auth/me").json()["username"] == "Мого_12"
        with client.websocket_connect("/legacy/socket") as ws:
            x, y = login(ws)
            assert walkable("novograd", x, y)
