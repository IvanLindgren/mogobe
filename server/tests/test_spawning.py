import math
import random
from time import monotonic
from xml.etree.ElementTree import fromstring

from fastapi.testclient import TestClient
from test_multiplayer import account, auth, join
from test_world import extension, receive

from src.world import catalog, service, spawning
from src.world.navigation import walkable


def test_random_spawns_use_main_mask_avoid_triggers_and_other_players(monkeypatch):
    monkeypatch.setattr(spawning, "random", random.Random(2026))
    for room in catalog.DATA["rooms"]:
        positions = []
        for _ in range(12):
            player = service.enter(room["key"], occupied=positions[-3:])
            point = (player.x, player.y)
            assert walkable(room["key"], *point)
            assert room["spawn_grid"][int(player.y // 8)][int(player.x // 8)] == "1"
            assert all(math.dist(point, other) >= 36 for other in positions[-3:])
            assert all(
                not (
                    e["bounds"][0] - 28 <= player.x <= e["bounds"][1] + 28
                    and e["bounds"][2] - 28 <= player.y <= e["bounds"][3] + 28
                )
                for e in room["exits"]
            )
            positions.append(point)
        assert len(set(positions)) > 1


def test_arrivals_appear_on_matching_sides_without_automatic_return(monkeypatch):
    monkeypatch.setattr(spawning, "random", random.Random(23))
    for _ in range(20):
        right = service.enter("novograd", arrival_from=catalog.resolve("InfoBoard"))
        left = service.enter("infoboard", arrival_from=catalog.resolve("Novograd"))
        assert right.x > 600 and left.x < 160
        # The server tolerates packets near a door, but the avatar itself must
        # be outside the actual original trigger so no bounce can fire.
        for player in [right, left]:
            room = catalog.BY_ID[player.room_id]
            assert all(
                not (
                    e["bounds"][0] <= player.x <= e["bounds"][1]
                    and e["bounds"][2] <= player.y <= e["bounds"][3]
                )
                for e in room["exits"]
            )


def test_every_resolved_transition_arrives_near_a_physical_passage(monkeypatch):
    monkeypatch.setattr(spawning, "random", random.Random(15))
    for source in catalog.DATA["rooms"]:
        for exit in source["exits"]:
            destination = catalog.resolve(exit["target"]) if exit["target"] else None
            if not destination:
                continue
            player = service.enter(destination["key"], arrival_from=source)
            point = (player.x, player.y)
            entries = [e for e in destination["exits"] if e["target"] == source["swf"]]
            if not entries:
                assert point in spawning.safe_points(destination["key"])
                continue
            nearest = min(
                spawning.distance_to_entry(p, e)
                for p in spawning.safe_points(destination["key"])
                for e in entries
            )
            assert min(spawning.distance_to_entry(point, e) for e in entries) <= nearest + 48


def test_f5_intent_is_session_bound_once_and_does_not_persist_normal_logout(app):
    with TestClient(app) as client:
        ident, token = account(client, "ResumeRoom_1", 3)
        assert client.post("/api/world/reconnect", headers=auth(token)).status_code == 409
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            assert join(ws, "ResumeRoom_1").get("r") == "3"
            extension(ws, "rooms__jumpToRoom", nameId="FearCaveGate")
            assert fromstring(receive(ws)).find("body").get("r") == str(
                catalog.resolve("FearCaveGate")["id"]
            )
            # A client cannot select its own resume destination in this API.
            assert (
                client.post(
                    "/api/world/reconnect", json={"room": "Mall"}, headers=auth(token)
                ).status_code
                == 204
            )
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            assert join(ws, "ResumeRoom_1").get("r") == str(catalog.resolve("FearCaveGate")["id"])
            assert ident not in app.state.world.reconnects
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            assert join(ws, "ResumeRoom_1").get("r") == "3"
            assert client.post("/api/world/reconnect", headers=auth(token)).status_code == 204
            digest, room, _ = app.state.world.reconnects[ident]
            app.state.world.reconnects[ident] = (digest, room, monotonic() - 1)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            assert join(ws, "ResumeRoom_1").get("r") == "3"


def test_another_session_cannot_prepare_reconnect_for_the_active_player(app):
    with TestClient(app) as client:
        ident, token = account(client, "ResumeOwner_1", 4)
        client.cookies.clear()
        assert (
            client.post(
                "/api/auth/login", json={"username": "ResumeOwner_1", "password": "Pass1234"}
            ).status_code
            == 200
        )
        other = client.cookies.get("mogobe_session")
        assert token != other
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            join(ws, "ResumeOwner_1")
            assert client.post("/api/world/reconnect", headers=auth(other)).status_code == 409
            assert ident not in app.state.world.reconnects
