"""One authoritative room in the single server event loop.

Membership changes and queueing never await: a join snapshot and subsequent
join/move/leave events have a consistent order. Socket I/O happens in each
peer's bounded writer queue, so a slow client cannot stall the room.
"""

import asyncio
from contextlib import asynccontextmanager
from hashlib import sha256
from time import monotonic

from fastapi import HTTPException

BUSY_MESSAGE = "Этот могоби уже находится в игре. Сначала выйдите из игры на другом устройстве."


class WorldHub:
    def __init__(self, server_name="Могоби"):
        self.server_name = server_name
        self.connections = {}
        self.players = {}
        self.reconnects = {}
        self.login_lock = asyncio.Lock()
        self.social_lock = asyncio.Lock()

    def prepare_reconnect(self, account_id, token):
        peer = self.connections.get(account_id)
        digest = sha256((token or "").encode()).hexdigest()
        if peer is None or peer.room is None or peer.session_digest != digest:
            raise HTTPException(409, "Нет активного подключения этой сессии")
        now = monotonic()
        self.reconnects = {key: value for key, value in self.reconnects.items() if value[2] > now}
        self.reconnects[account_id] = (digest, peer.room, now + 60)

    def consume_reconnect(self, account_id, digest):
        saved = self.reconnects.pop(account_id, None)
        if saved and saved[0] == digest and saved[2] > monotonic():
            return saved[1]
        return None

    def require_available(self, account_id):
        if account_id in self.connections:
            raise HTTPException(409, BUSY_MESSAGE)

    @asynccontextmanager
    async def login_guard(self, account_id):
        # Session rotation and world admission share a lock. A concurrent HTTP
        # login cannot revoke the token of a socket that has just entered.
        async with self.login_lock:
            self.require_available(account_id)
            yield

    async def claim(self, peer):
        async with self.login_guard(peer.account.id):
            self.connections[peer.account.id] = peer

    def members(self, room):
        return [p for p in self.connections.values() if p.room == room]

    def broadcast(self, room, packet, exclude=None):
        for peer in self.members(room):
            if peer is not exclude:
                peer.enqueue(packet)

    def release(self, peer):
        if self.connections.get(peer.account.id) is not peer:
            return
        self.connections.pop(peer.account.id)
        self.players.pop(peer.account.id, None)
        if peer.room is not None:
            # Static room and server-owned numeric ID; no untrusted XML values.
            self.broadcast(
                peer.room,
                f'<msg t="sys"><body action="userGone" r="{peer.room}">'
                f'<user id="{peer.account.id}"/></body></msg>',
            )
