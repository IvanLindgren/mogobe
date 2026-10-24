import hashlib
import json
from pathlib import Path
from xml.etree.ElementTree import fromstring

from fastapi.testclient import TestClient
from test_multiplayer import account, auth, join
from test_world import extension, receive, send

from src.world import catalog
from src.world.navigation import path_to, walkable


def test_imported_masks_have_safe_spawns_and_matching_original_assets():
    root = Path(__file__).resolve().parents[2] / "assets/original/Swf/Rooms"
    for room in catalog.DATA["rooms"]:
        assert (
            hashlib.sha256((root / (room["swf"] + ".swf")).read_bytes()).hexdigest()
            == room["source_sha256"]
        )
        assert walkable(room["key"], *room["spawn"])
        assert path_to(room["key"], room["spawn"], room["spawn"])
        assert all(not e["target"] or catalog.resolve(e["target"]) for e in room["exits"])


def test_map_names_all_rooms_and_room_changes_are_authoritative(app):
    with TestClient(app) as client:
        _, token = account(client, "MapRooms_1", 3)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            join(ws, "MapRooms_1")
            listing = client.get("/api/world/rooms", headers=auth(token)).json()["rooms"]
            assert len(listing) >= 40
            for room in catalog.DATA["rooms"]:
                extension(ws, "rooms__jumpToRoom", nameId=room["swf"], userId=999999)
                body = fromstring(receive(ws)).find("body")
                assert body.get("action") == "joinOK"
                assert int(body.get("r")) == room["id"]
                variables = {v.get("n"): v.text for v in body.findall("vars/var")}
                assert variables["baseSwf"] == room["swf"]
                assert variables.get("rbs") == catalog.ROOM_AUDIO.get(room["key"])
                state = client.get("/api/world/me", headers=auth(token)).json()
                assert state["room"] == room["key"] and walkable(
                    room["key"], state["x"], state["y"]
                )
            for missing in ["../../private", "PrivateRoom", "GoldFishing", "UnknownRoom"]:
                extension(ws, "rooms__jumpToRoom", nameId=missing)
                assert json.loads(receive(ws))["b"]["o"]["errorId"] == 69


def test_players_leave_old_room_chat_is_isolated_and_rejoin_snapshot_is_fresh(app):
    with TestClient(app) as client:
        aid, atoken = account(client, "RoomPeer_1", 3)
        bid, btoken = account(client, "RoomPeer_2", 7)
        with client.websocket_connect("/legacy/socket", headers=auth(atoken)) as a:
            join(a, "RoomPeer_1")
            with client.websocket_connect("/legacy/socket", headers=auth(btoken)) as b:
                join(b, "RoomPeer_2")
                receive(a)
                extension(a, "rooms__jumpToRoom", nameId="InfoBoard")
                assert fromstring(receive(a)).find("body").get("r") == str(
                    catalog.resolve("InfoBoard")["id"]
                )
                gone = fromstring(receive(b)).find("body")
                assert gone.get("action") == "userGone" and gone.find("user").get("id") == str(aid)
                before = client.get("/api/world/me", headers=auth(atoken)).json()
                send(
                    a,
                    '<msg t="sys"><body action="setUvars" r="3"><vars>'
                    '<var n="x" t="n">10</var><var n="y" t="n">10</var></vars></body></msg>',
                )
                extension(a, "user__getMyMoney")
                assert json.loads(receive(a))["b"]["o"]["_cmd"] == "user__getMyMoney"
                assert client.get("/api/world/me", headers=auth(atoken)).json() == before
                send(
                    a, '<msg t="sys"><body action="pubMsg"><txt>speak__OtherRoom</txt></body></msg>'
                )
                assert "OtherRoom" in receive(a)
                extension(b, "user__getMyMoney")
                assert json.loads(receive(b))["b"]["o"]["_cmd"] == "user__getMyMoney"
                assert (
                    client.get("/api/world/servers", headers=auth(atoken)).json()["servers"][0][
                        "online"
                    ]
                    == 2
                )
                extension(a, "rooms__jumpToRoom", nameId="Novograd")
                users = fromstring(receive(a)).findall("body/uLs/u")
                assert {int(v.get("i")) for v in users} == {aid, bid}
                assert fromstring(receive(b)).find("body").get("action") == "uER"


def test_only_nearby_authored_door_can_change_the_room(app):
    with TestClient(app) as client:
        ident, token = account(client, "Door_1", 3)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            join(ws, "Door_1")
            extension(ws, "rooms__changeRoom", grfCompunentId=6)
            assert json.loads(receive(ws))["b"]["o"]["errorId"] == 69
            connection = app.state.world.connections[ident]
            entry = next(e for e in catalog.START_ROOM["exits"] if e["token"] == "6")
            left, right, top, bottom = entry["bounds"]
            x, y = path_to(
                "novograd", catalog.START_ROOM["spawn"], ((left + right) / 2, (top + bottom) / 2)
            )[-1]
            connection.player.x, connection.player.y = x, y
            extension(ws, "rooms__changeRoom", grfCompunentId=6)
            assert fromstring(receive(ws)).find("body").get("r") == str(
                catalog.resolve("InfoBoard")["id"]
            )


def test_room_audio_uses_original_files_in_standalone_client_package():
    root = Path(__file__).resolve().parents[2] / "assets/original/Sound/Rooms"
    assert catalog.ROOM_AUDIO["novograd"] == "Novograd.mp3"
    assert catalog.ROOM_AUDIO["summercamp"] == "otdyhaevo.mp3"
    assert all(catalog.resolve(key) for key in catalog.ROOM_AUDIO)
    sources = json.loads((root.parents[1] / "sources.json").read_text(encoding="utf-8"))
    expected = {entry["path"]: entry["sha256"] for entry in sources}
    for track in catalog.ROOM_AUDIO.values():
        assert Path(track).name == track and track.endswith(".mp3")
        assert hashlib.sha256((root / track).read_bytes()).hexdigest() == expected[
            "Sound/Rooms/" + track
        ]
