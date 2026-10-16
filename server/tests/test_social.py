import json

from fastapi.testclient import TestClient
from test_multiplayer import account, auth, join
from test_world import extension, receive, send

from src.legacy.messages import (
    AVATAR_EFFECTS,
    CHAT_PHRASES,
    EMOTIONS,
    ROOM_EFFECTS,
    validated_message,
)


def until(ws, command):
    packets = []
    while True:
        packet = receive(ws)
        if packet.startswith("{"):
            data = json.loads(packet)["b"]["o"]
            if data["_cmd"] == command:
                return data, packets
        packets.append(packet)


def test_original_message_allowlist_and_sender_identity():
    members = {1, 2}
    assert CHAT_PHRASES["1010"] == "Привет!"
    for phrase in CHAT_PHRASES:
        assert validated_message("closeChat__" + phrase, 1, members) == "closeChat__" + phrase
    for bad in [
        "closeChat__999999",
        "closeChat__1000",
        "closeChat__1010__2",
        "closeChat__",
        "closeChat__01010",
    ]:
        assert validated_message(bad, 1, members) is None
    for emotion in EMOTIONS:
        text = "emoticons__" + emotion
        assert validated_message(text, 1, members) == text
    for effect in AVATAR_EFFECTS:
        text = "effect__" + effect + "__2"
        assert validated_message(text, 1, members) == text
    for effect in ROOM_EFFECTS:
        assert (
            validated_message(f"effect__{effect}__999__300:390__false", 1, members)
            == f"effect__{effect}__1__300:390__false"
        )
    for text in [
        "emoticons__Missing",
        "effect__Ico_rain__999",
        "effect__Ico_rain__2__1:2__false",
        "speak__",
        "effect__Ico_Fireworks__1__nan:12__false",
        "effect__Ico_teeth1__1__768:10__false",
        "effect__Ico_teeth2__1__5:8__true",
        "avatarAction__x__2",
        "closeChat__x",
        "emoticons__Ico_mad__2",
    ]:
        assert validated_message(text, 1, members) is None
    assert validated_message("speak__hello__999", 1, members) == "speak__hello_999"


def test_real_friend_requests_accept_best_mute_and_reconnect(app):
    with TestClient(app) as client:
        aid, atoken = account(client, "Social_1", 3)
        bid, btoken = account(client, "Social_2", 7)
        with client.websocket_connect("/legacy/socket", headers=auth(atoken)) as a:
            join(a, "Social_1")
            with client.websocket_connect("/legacy/socket", headers=auth(btoken)) as b:
                join(b, "Social_2")
                receive(a)
                extension(a, "buddyList__acceptBuddyRequest", buddyId=bid)
                assert until(a, "buddyList__acceptBuddyRequest")[0]["errorId"] == 11
                extension(a, "buddyList__addBuddyRequest", buddyId=bid, buddyName="Social_2")
                assert until(a, "buddyList__addBuddyRequest")[0]["msgId"] == -1
                # Forging userId cannot read another user's list or accept
                # an outgoing request on behalf of the recipient.
                extension(a, "buddyList__getUserBuddies", userId=bid)
                assert until(a, "buddyList__getUserBuddies")[0]["buddies"] == []
                extension(b, "buddyList__getUserBuddies")
                data, _ = until(b, "buddyList__getUserBuddies")
                assert data["buddies"][0]["buddyId"] == aid and data["buddies"][0]["status"] == 1
                extension(b, "buddyList__acceptBuddyRequest", buddyId=aid)
                assert until(b, "buddyList__acceptBuddyRequest")[0]["msgId"] == -1
                extension(a, "buddyList__getUserBuddies")
                data, _ = until(a, "buddyList__getUserBuddies")
                assert data["buddies"][0]["status"] == 2 and data["buddies"][0]["serverName"]
                extension(a, "buddyList__addToBestBuddy", buddyId=bid)
                until(a, "buddyList__addToBestBuddy")
                extension(a, "buddyList__getUserBuddies")
                assert until(a, "buddyList__getUserBuddies")[0]["buddies"][0]["status"] == 4
                extension(a, "buddyList__blockBuddy", buddyName="Social_2")
                until(a, "buddyList__blockBuddy")
                extension(a, "user__getUserCardInfo", userId=bid)
                data, _ = until(a, "user__getUserCardInfo")
                assert data["isBlock"] is True and data["isAllowToAdd"] is False
                assert app.state.world.connections[aid].muted_ids == {bid}
                # Barrier: queued public messages would precede this reply.
                send(b, '<msg t="sys"><body action="pubMsg"><txt>speak__muted</txt></body></msg>')
                extension(b, "user__getMyMoney")
                _, echo = until(b, "user__getMyMoney")
                assert any("speak__muted" in msg for msg in echo)
                extension(a, "user__getMyMoney")
                _, packets = until(a, "user__getMyMoney")
                assert not any("speak__muted" in msg for msg in packets)
                response = client.get("/api/social/me", headers=auth(atoken))
                assert response.json()["muted_names"] == ["Social_2"]
            # Muted settings persist across both the peer's departure and our
            # reconnect. Accepted links still contribute to the friend count.
        with client.websocket_connect("/legacy/socket", headers=auth(atoken)) as a:
            join(a, "Social_1")
            assert app.state.world.connections[aid].muted_ids == {bid}
            extension(a, "buddyList__getUserBuddies")
            data, _ = until(a, "buddyList__getUserBuddies")
            assert data["buddies"][0]["status"] == 3 and data["buddies"][0]["serverName"] is None
            extension(a, "buddyList__deleteBuddy", buddyId=bid)
            until(a, "buddyList__deleteBuddy")
            assert app.state.world.connections[aid].muted_ids == set()
            extension(a, "user__getUserCard", userId=aid)
            assert until(a, "user__getUserCard")[0]["friends"] == 1
            extension(a, "buddyList__deleteBuddy", buddyId=bid)
            until(a, "buddyList__deleteBuddy")
            extension(a, "user__getUserCard", userId=aid)
            assert until(a, "user__getUserCard")[0]["friends"] == 0


def test_unfriend_preserves_other_players_personal_mute(app):
    from src.profiles.models import Friendship, SocialPreference
    from src.profiles.social import muted_ids, operate

    with TestClient(app) as client:
        first, _ = account(client, "MuteOwner_1", 3)
        second, _ = account(client, "MuteOwner_2", 7)

        async def check():
            async with app.state.sessions() as db:
                db.add(Friendship(first_id=first, second_id=second))
                db.add(SocialPreference(owner_id=second, buddy_id=first, muted=True, best=True))
                await db.commit()
                await operate(db, first, "deleteBuddy", {"buddyId": second})
                assert await db.get(Friendship, (first, second)) is None
                preference = await db.get(SocialPreference, (second, first))
                assert preference.muted is True and preference.best is False
                assert await muted_ids(db, second) == {first}

        client.portal.call(check)


def test_mute_set_is_idempotent_private_and_updates_active_connection(app):
    with TestClient(app) as client:
        owner, token = account(client, "SetMute_1", 3)
        buddy, other = account(client, "SetMute_2", 7)
        with client.websocket_connect("/legacy/socket", headers=auth(token)) as ws:
            join(ws, "SetMute_1")
            for value in (True, True, False, False, True):
                response = client.post(
                    "/api/social/mute",
                    headers=auth(token),
                    json={"username": "setmute_2", "muted": value},
                )
                assert response.status_code == 200
                assert response.json() == {"username": "SetMute_2", "muted": value}
                assert app.state.world.connections[owner].muted_ids == ({buddy} if value else set())
            assert client.get("/api/social/me", headers=auth(other)).json()["muted_names"] == []
            for name, status in (("SetMute_1", 400), ("Missing_1", 404)):
                assert (
                    client.post(
                        "/api/social/mute",
                        headers=auth(token),
                        json={"username": name, "muted": True},
                    ).status_code
                    == status
                )
            assert (
                client.post(
                    "/api/social/mute",
                    headers=auth(token),
                    json={"username": "SetMute_2", "muted": "false"},
                ).status_code
                == 422
            )
        client.cookies.clear()
        assert (
            client.post(
                "/api/social/mute", json={"username": "SetMute_2", "muted": True}
            ).status_code
            == 401
        )


def test_original_ready_phrases_reach_both_players_and_respect_mute(app):
    with TestClient(app) as client:
        aid, atoken = account(client, "Phrase_1", 3)
        bid, btoken = account(client, "Phrase_2", 7)
        with client.websocket_connect("/legacy/socket", headers=auth(atoken)) as a:
            join(a, "Phrase_1")
            with client.websocket_connect("/legacy/socket", headers=auth(btoken)) as b:
                join(b, "Phrase_2")
                receive(a)
                for phrase in ["1010", "1030", "2010"]:
                    app.state.world.connections[aid].last_chat = 0
                    send(
                        a,
                        '<msg t="sys"><body action="pubMsg"><txt>closeChat__'
                        + phrase
                        + "</txt></body></msg>",
                    )
                    for peer in [a, b]:
                        packet = receive(peer)
                        assert '<user id="' + str(aid) + '"/>' in packet
                        assert "<txt>closeChat__" + phrase + "</txt>" in packet
                response = client.post(
                    "/api/social/mute",
                    headers=auth(btoken),
                    json={"username": "Phrase_1", "muted": True},
                )
                assert response.status_code == 200
                for peer in [a, b]:
                    extension(peer, "user__getMyMoney")
                    until(peer, "user__getMyMoney")
                app.state.world.connections[aid].last_chat = 0
                send(
                    a, '<msg t="sys"><body action="pubMsg"><txt>closeChat__1010</txt></body></msg>'
                )
                assert "closeChat__1010" in receive(a)
                extension(b, "user__getMyMoney")
                _, packets = until(b, "user__getMyMoney")
                assert not any("closeChat__" in packet for packet in packets)
