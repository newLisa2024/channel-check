"""Settings from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    database_url: str = "postgresql+asyncpg://bot:bot@postgres:5432/channelcheck"
    redis_url: str = "redis://redis:6379/0"

    admin_ids: str = ""            # comma-separated Telegram IDs allowed to use admin commands
    alert_chat_id: int | None = None  # where the worker reports unexpected errors
    support_contact: str = ""      # e.g. @your_support_username, shown in /paysupport

    free_checks_on_start: int = 1
    checks_per_hour_limit: int = 10
    cache_hours: int = 6           # reuse a channel's fresh result for anyone
    own_repeat_hours: int = 24     # the same user re-opens the same channel for free
    max_posts: int = 100

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x) for x in self.admin_ids.replace(" ", "").split(",") if x}


@lru_cache
def get_settings() -> Settings:
    return Settings()
