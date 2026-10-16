"""Live presence comes from joined sockets, never from saved HTTP sessions."""

from src.profiles.social import friend_ids


def online_ids(hub):
    return {
        ident
        for ident, peer in hub.connections.items()
        if peer.room is not None and peer.user is not None
    }


async def server_snapshot(db, owner, hub):
    online = online_ids(hub)
    friends = await friend_ids(db, owner)
    return {
        "id": 1,
        "name": hub.server_name,
        "online": len(online),
        "friends": len(online & friends),
        "percentage": min(100, len(online)),
    }
