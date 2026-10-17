import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_multiplayer import account, auth, join
from test_shops import ADMIN, setup_shop
from test_world import receive, send

from src.auth.models import Account
from src.profiles.progression import MAX_EXPERIENCE, level
from src.shops.commands import give


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, 1),
        (999, 1),
        (1000, 2),
        (1999, 2),
        (2000, 3),
        (124000, 9),
        (1024000, 12),
        (MAX_EXPERIENCE, 12),
    ],
)
def test_original_level_thresholds_are_numeric(score, expected):
    assert level(score) == expected


def until(ws, predicate):
    frames = []
    while True:
        frame = receive(ws)
        frames.append(frame)
        if predicate(frame):
            return frames


def test_purchase_reward_is_persistent_atomic_and_uses_original_score_event(app):
    with TestClient(app) as client:
        ident, token, offer = setup_shop(client, app, price=10)
        h = auth(token)
        client.post(ADMIN + "/accounts/ShopAdmin/balance", headers=h, json={"coins": 50})
        client.put(ADMIN + "/test/offers/1", headers=h, json={**offer, "experience": 1500})
        with client.websocket_connect("/legacy/socket", headers=h) as ws:
            join(ws, "ShopAdmin")
            result = client.post(
                "/api/shops/test/buy", headers=h, json={"item_id": 1, "expected_price": 10}
            )
            assert result.status_code == 200 and result.json()["experience_awarded"] == 1500
            assert result.json()["score"] == 1500 and result.json()["level"] == 2
            frames = until(
                ws,
                lambda x: (
                    x.startswith("{")
                    and json.loads(x)["b"]["o"]["_cmd"] == "user__worldScoreChange"
                ),
            )
            assert json.loads(frames[-1])["b"]["o"]["score"] == 1500
            assert any("score" in f and "1500" in f for f in frames if f.startswith("<"))
            assert (
                client.post(
                    "/api/shops/test/buy", headers=h, json={"item_id": 1, "expected_price": 10}
                ).status_code
                == 409
            )
        profile = client.get("/api/social/profiles/" + str(ident), headers=h).json()
        assert profile["score"] == 1500 and profile["level"] == 2 and profile["mo_1"] == 40
        assert client.get("/api/social/profiles/999999", headers=h).status_code == 404


def test_failed_reward_overflow_rolls_back_money_stock_and_item(app):
    with TestClient(app) as client:
        ident, token, offer = setup_shop(client, app, price=10)
        h = auth(token)
        client.post(ADMIN + "/accounts/ShopAdmin/balance", headers=h, json={"coins": 50})

        async def near_limit():
            async with app.state.sessions() as db:
                await db.execute(
                    update(Account).where(Account.id == ident).values(experience=MAX_EXPERIENCE - 1)
                )
                await db.commit()

        client.portal.call(near_limit)
        assert (
            client.post(
                "/api/shops/test/buy", headers=h, json={"item_id": 1, "expected_price": 10}
            ).status_code
            == 409
        )
        assert client.get("/api/inventory", headers=h).json() == {"items": [], "coins": 50}
        assert client.get(ADMIN + "/test/catalog", headers=h).json()["offers"][0]["stock"] == 1
        assert (
            client.get("/api/social/profiles/" + str(ident), headers=h).json()["score"]
            == MAX_EXPERIENCE - 1
        )


def test_account_directory_roles_and_give_permissions_change_without_relogin(app):
    with TestClient(app) as client:
        admin_id, admin, offer = setup_shop(client, app)
        user_id, user = account(client, "GiveUser", 7)
        ah, uh = auth(admin), auth(user)
        assert client.get(ADMIN + "/accounts", headers=uh).status_code == 403
        assert (
            client.put(
                ADMIN + f"/accounts/{user_id}/admin", headers=uh, json={"is_admin": True}
            ).status_code
            == 403
        )
        assert (
            client.put(
                ADMIN + f"/accounts/{admin_id}/admin", headers=ah, json={"is_admin": False}
            ).status_code
            == 409
        )
        listing = client.get(ADMIN + "/accounts?q=gIvEu&limit=1", headers=ah).json()
        assert listing["total"] == 1 and listing["accounts"][0]["id"] == user_id
        assert not {"password_hash", "parent_email", "token_hash"} & listing["accounts"][0].keys()
        with client.websocket_connect("/legacy/socket", headers=uh) as ws:
            join(ws, "GiveUser")
            send(
                ws,
                '<msg t="sys"><body action="pubMsg"><txt>speak__/give exp 500</txt></body></msg>',
            )
            until(ws, lambda x: "Команда доступна только администраторам" in x)
            assert (
                client.get("/api/social/profiles/" + str(user_id), headers=ah).json()["score"] == 0
            )
            assert (
                client.put(
                    ADMIN + f"/accounts/{user_id}/admin", headers=ah, json={"is_admin": True}
                ).status_code
                == 200
            )
            # The command service re-reads role from SQLite for this existing session.
            client.portal.call(give, app, user_id, "/give exp 1500")
            until(
                ws,
                lambda x: (
                    x.startswith("{")
                    and json.loads(x)["b"]["o"]["_cmd"] == "user__worldScoreChange"
                ),
            )
            assert (
                client.get("/api/social/profiles/" + str(user_id), headers=ah).json()["score"]
                == 1500
            )
            client.portal.call(give, app, user_id, "/give item 1")
            assert client.get("/api/inventory", headers=uh).json()["items"][0]["typeId"] == 1
            with pytest.raises(HTTPException) as duplicate:
                client.portal.call(give, app, user_id, "/give item 1")
            assert duplicate.value.status_code == 409
            assert (
                client.put(
                    ADMIN + f"/accounts/{user_id}/admin", headers=ah, json={"is_admin": False}
                ).status_code
                == 200
            )
            with pytest.raises(HTTPException) as denied:
                client.portal.call(give, app, user_id, "/give exp 500")
            assert denied.value.status_code == 403
            assert (
                client.get("/api/social/profiles/" + str(user_id), headers=ah).json()["isMember"]
                is False
            )


@pytest.mark.parametrize(
    "command",
    [
        "/give",
        "/give item -1",
        "/give exp 0",
        "/give exp 1.5",
        "/give exp 1000001",
        "/give nope 1",
        "/give exp １２",
        "/give exp 3 extra",
    ],
)
def test_give_rejects_malformed_amounts(app, command):
    with TestClient(app) as client:
        ident, token, _ = setup_shop(client, app)
        with pytest.raises(HTTPException) as invalid:
            client.portal.call(give, app, ident, command)
        assert invalid.value.status_code == 422
        assert (
            client.get("/api/social/profiles/" + str(ident), headers=auth(token)).json()["score"]
            == 0
        )
