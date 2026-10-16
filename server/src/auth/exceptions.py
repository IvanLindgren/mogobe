from fastapi import HTTPException


class InvalidCredentials(HTTPException):
    def __init__(self):
        super().__init__(401, "Неверное имя или пароль")


class UsernameTaken(HTTPException):
    def __init__(self):
        super().__init__(409, "Это имя уже занято")


class RegistrationExpired(HTTPException):
    def __init__(self):
        super().__init__(401, "Регистрация истекла. Начните заново с выбора цвета")
