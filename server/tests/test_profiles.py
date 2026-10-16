import json
from datetime import UTC, datetime, timedelta, timezone
from xml.etree.ElementTree import fromstring

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_multiplayer import account, auth, join
from test_world import extension, receive

from src.auth.models import Account
from src.profiles.models import Friendship
from src.profiles.service import days_registered


@pytest.mark.parametrize(
    "elapsed,expected", [(0, 0), (86399, 0), (86400, 1), (86400 * 17 + 200, 17), (-86400, 0)]
)
def test_profile_age_is_elapsed_registration_days(elapsed, expected):
    instant = datetime(2026, 10, 16, 12, 0)
    assert days_registered(instant - timedelta(seconds=elapsed), instant) == expected


def test_registration_days_normalizes_utc_offsets():
    instant = datetime(2026, 10, 16, 12, tzinfo=UTC)
    created = datetime(2026, 10, 15, 15, tzinfo=timezone(timedelta(hours=3)))
    assert days_registered(created, instant) == 1


def reply(ws, command):
    updates = []
    while True:
        message = receive(ws)
        if message.startswith("{"):
            data = json.loads(message)["b"]["o"]
            assert data["_cmd"] == command
            return data, updates
        updates.append(fromstring(message))


def test_cards_counters_private_inventory_and_offline_lookup(app):
    with TestClient(app) as client:
        first, token = account(client, "Profile_1", 3)
        second, _ = account(client, "Profile_2", 7)

        async def seed_age():
            async with app.state.sessions() as db:
                await db.execute(
                    update(Account)
                    .where(Account.id == first)
                    .values(
                        created_at=datetime.now(UTC).replace(tzinfo=None)
                        - timedelta(days=5, hours=2)
                    )
                )
                await db.commit()

        client.portal.call(seed_age)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            body = join(ws, "Profile_1")
            own = body.find("uLs/u/vars")
            assert own.find('var[@n="age"]').text == "5"
            assert own.find('var[@n="friends"]').text == "0"

            # A newly stored friendship must refresh an already online user's
            # SFS variables when a card is opened, without a relogin.
            async def seed_friend():
                async with app.state.sessions() as db:
                    db.add(Friendship(first_id=first, second_id=second))
                    await db.commit()

            client.portal.call(seed_friend)
            extension(ws, "user__getUserCardInfo", userId=first, userName="Profile_1")
            data, updates = reply(ws, "user__getUserCardInfo")
            assert data["age"] == 5 and data["friends"] == 1 and data["newMsgs"] == 0
            assert updates[0].find('body/vars/var[@n="friends"]').text == "1"
            assert app.state.world.connections[first].state["friends"] == 1
            extension(ws, "user__getUserCard", userName="profile_2")
            data, _ = reply(ws, "user__getUserCard")
            assert data["userId"] == second and data["userName"] == "Profile_2"
            assert data["online"] is False and data["friends"] == 1 and data["age"] == 0
            assert data["color"] == 7
            assert (
                not {"password_hash", "parent_email", "newsletter", "created_at", "chat_mode"}
                & data.keys()
            )
            extension(ws, "user__getInventoryItems", userId=first, mainType=1)
            assert reply(ws, "user__getInventoryItems")[0]["items"] == []
            extension(ws, "user__getInventoryItems", userId=second, mainType=1)
            assert reply(ws, "user__getInventoryItems")[0]["errorId"] == 11
            for params in (
                {"userId": True},
                {"userId": 999999},
                {"userId": first, "userName": "Profile_2"},
            ):
                extension(ws, "user__getUserCard", **params)
                data, _ = reply(ws, "user__getUserCard")
                assert data == {"_cmd": "user__getUserCard", "errorId": 11}
