from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPESPED_", env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./spesped-dev.db"
    secret_key: str = "development-only-change-before-production"
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:8000"]
    cookie_name: str = "spesped_session"
    cookie_secure: bool = False
    session_hours: int = Field(default=8, ge=1, le=168)
    login_attempt_limit: int = Field(default=10, ge=3, le=100)
    login_lock_minutes: int = Field(default=15, ge=1, le=1440)

    @model_validator(mode="after")
    def safe_configuration(self):
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("Unsupported environment")
        for origin in self.allowed_origins:
            parsed = urlparse(origin)
            if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                    or parsed.path or parsed.query or parsed.fragment or parsed.username
                    or "*" in origin or not parsed.hostname):
                raise ValueError("Origins must be exact HTTP origins")
        if self.environment == "production":
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production requires PostgreSQL with psycopg")
            if (len(self.secret_key) < 32 or "development" in self.secret_key.lower()
                    or "replace" in self.secret_key.lower() or "placeholder" in self.secret_key.lower()):
                raise ValueError("Production requires a separately supplied strong secret")
            if not self.cookie_secure:
                raise ValueError("Production session cookies must be secure")
            if not self.allowed_origins or any(not x.startswith("https://") for x in self.allowed_origins):
                raise ValueError("Production requires explicit HTTPS origins")
            parsed = urlparse(self.database_url)
            if not parsed.password or parsed.password.lower() in {"password", "postgres", "replace_me"}:
                raise ValueError("Production requires explicit database credentials")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
