from hashlib import sha256
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from src.auth.dependencies import CurrentAccount, get_token


def current_player(account: CurrentAccount, request: Request):
    peer = request.app.state.world.connections.get(account.id)
    digest = sha256((get_token(request) or "").encode()).hexdigest()
    if peer is None or peer.room is None or peer.session_digest != digest:
        raise HTTPException(409, "Сначала войдите в игровой мир этой сессией")
    return peer


CurrentPlayer = Annotated[object, Depends(current_player)]
