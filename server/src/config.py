from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MOGOBE_", env_file=ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite+aiosqlite:///{(ROOT / 'data/mogobe.sqlite3').as_posix()}"
    session_hours: int = Field(default=24, ge=1, le=720)
    remembered_session_days: int = Field(default=30, ge=1, le=90)
    registration_minutes: int = Field(default=30, ge=1, le=120)
    bootstrap_defaults: bool = True
    cookie_secure: bool = False  # The packaged client uses an HTTP loopback gateway.
    server_name: str = "Локальный сервер"
    login_limit: int = Field(default=12, ge=1)
    login_window_seconds: int = Field(default=300, ge=1)
