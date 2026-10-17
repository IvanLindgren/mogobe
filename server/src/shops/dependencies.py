from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request

from src.auth.dependencies import CurrentAccount
from src.auth.models import Account


def require_admin(account: CurrentAccount, request: Request) -> Account:
    if not account.is_admin:
        raise HTTPException(403, "Нужны права администратора")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Запрос с другого сайта отклонён")
    return account


AdminAccount = Annotated[Account, Depends(require_admin)]
