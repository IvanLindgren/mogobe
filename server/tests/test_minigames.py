from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from test_multiplayer import account, auth, join
from test_world import extension, receive

from src.minigames import service
from src.minigames.models import GameRun


def age_run(client, app, run_id, seconds=45):
    async def age():
        async with app.state.sessions() as db:
            row = await db.get(GameRun, run_id)
            row.started_at = service.now() - timedelta(seconds=seconds)
            await db.commit()

    client.portal.call(age)


def test_game_requires_world_and_validates_result(app):
    with TestClient(app) as client:
        assert client.post("/api/minigames/goldfishing/start").status_code == 401
        _, token = account(client, "FishOwner", 7)
        h = auth(token)
        assert client.post("/api/minigames/goldfishing/start", headers=h).status_code == 409
        with client.websocket_connect("/legacy/socket", headers=h) as ws:
            join(ws, "FishOwner")
            assert client.post("/api/minigames/missing/start", headers=h).status_code == 404
            response = client.post("/api/minigames/goldfishing/start", headers=h)
            assert response.status_code == 201
            data = response.json()
            assert data["player"]["avatarColor"] == 7
            finish = "/api/minigames/runs/" + data["id"] + "/finish"
            assert client.post("/api/minigames/goldfishing/start", headers=h).status_code == 409
            for score in [True, -1, 1.5, "100", 1000001]:
                assert (
                    client.post(
                        finish, headers=h, json={"score": score, "completed": True}
                    ).status_code
                    == 422
                )
            assert (
                client.post(
                    finish, headers=h, json={"score": 100, "completed": True, "coins": 999}
                ).status_code
                == 422
            )
            assert (
                client.post(finish, headers=h, json={"score": 100, "completed": True}).status_code
                == 409
            )
            assert (
                client.post(
                    finish, headers=h, json={"score": 100, "completed": False, "cancelled": True}
                ).json()["coins_awarded"]
                == 0
            )
            assert (
                client.post(
                    "/api/minigames/runs/" + str(uuid4()) + "/finish",
                    headers=h,
                    json={"score": 0, "completed": False},
                ).status_code
                == 404
            )


def test_reward_is_once_capped_persistent_and_owner_only(app):
    with TestClient(app) as client:
        _, token = account(client, "FishScore", 3)
        _, other = account(client, "FishOther", 7)
        h = auth(token)
        with client.websocket_connect("/legacy/socket", headers=h) as ws:
            join(ws, "FishScore")
            run = client.post("/api/minigames/goldfishing/start", headers=h).json()
            finish = "/api/minigames/runs/" + run["id"] + "/finish"
            with client.websocket_connect("/legacy/socket", headers=auth(other)) as b:
                join(b, "FishOther")
                assert (
                    client.post(
                        finish, headers=auth(other), json={"score": 0, "completed": False}
                    ).status_code
                    == 404
                )
                assert (
                    client.get("/api/minigames/results", headers=auth(other)).json()["results"]
                    == []
                )
            age_run(client, app, run["id"])
            assert (
                client.post(
                    finish, headers=h, json={"score": 999999, "completed": True}
                ).status_code
                == 422
            )
            result = client.post(finish, headers=h, json={"score": 40000, "completed": True}).json()
            assert result["status"] == "finished" and result["coins_awarded"] == 100
            for score in [40000, 9999]:
                assert (
                    client.post(finish, headers=h, json={"score": score, "completed": True}).json()
                    == result
                )
            assert client.get("/api/inventory", headers=h).json()["coins"] == 100
        assert client.get("/api/minigames/results", headers=h).json()["results"][0] == result
        with client.websocket_connect("/legacy/socket", headers=h) as ws:
            join(ws, "FishScore")
            assert client.get("/api/inventory", headers=h).json()["coins"] == 100


def test_cancel_on_room_change_disconnect_and_original_entry(app):
    with TestClient(app) as client:
        ident, token = account(client, "FishAbort", 7)
        h = auth(token)
        with client.websocket_connect("/legacy/socket", headers=h) as ws:
            join(ws, "FishAbort")
            extension(ws, "rooms__changeRoom", grfCompunentId=81)
            assert "minigame__open" not in receive(ws)
            run = client.post("/api/minigames/goldfishing/start", headers=h).json()
            extension(ws, "rooms__jumpToRoom", nameId="Severburg")
            assert "joinOK" in receive(ws)
            finish = "/api/minigames/runs/" + run["id"] + "/finish"
            assert (
                client.post(finish, headers=h, json={"score": 500, "completed": True}).json()[
                    "status"
                ]
                == "cancelled"
            )
            peer = app.state.world.connections[ident]
            peer.player.x, peer.player.y = 50, 400
            extension(ws, "rooms__changeRoom", grfCompunentId=81)
            assert "minigame__open" not in receive(ws)
            peer.player.x, peer.player.y = 435, 305
            extension(ws, "rooms__changeRoom", grfCompunentId=81)
            assert '"isMultiGame": true' in receive(ws)
            assert "minigame__open" in receive(ws)
            run = client.post("/api/minigames/goldfishing/start", headers=h).json()
        history = client.get("/api/minigames/results", headers=h).json()["results"]
        assert next(row for row in history if row["id"] == run["id"])["status"] == "cancelled"
        assert client.get("/api/inventory", headers=h).json()["coins"] == 0


def test_early_exit_pays_coins_and_experience_once_before_full_round(app):
    with TestClient(app) as client:
        ident, token = account(client, "EarlyFish", 7)
        headers = auth(token)
        with client.websocket_connect("/legacy/socket", headers=headers) as ws:
            join(ws, "EarlyFish")
            run = client.post("/api/minigames/goldfishing/start", headers=headers).json()
            age_run(client, app, run["id"], seconds=10)
            finish = "/api/minigames/runs/" + run["id"] + "/finish"
            body = {"score": 2500, "completed": False}
            response = client.post(finish, headers=headers, json=body)
            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "stopped"
            assert result["coins_awarded"] == result["experience_awarded"] == 25
            assert client.post(finish, headers=headers, json=body).json() == result
            assert client.get("/api/inventory", headers=headers).json()["coins"] == 25
            profile = client.get("/api/social/profiles/" + str(ident), headers=headers).json()
            assert profile["score"] == 25
