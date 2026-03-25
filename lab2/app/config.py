from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""

    APP_NAME: str = "Redis API & Notes Service"
    REDIS_URL: str = "redis://localhost:6379"
    DB_URL: str = "sqlite+aiosqlite:///./notes.db"

    class Config:
        env_file = ".env"

settings = Settings()