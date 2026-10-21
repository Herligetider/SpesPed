from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AIProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=80)
    endpoint: str
    capabilities: set[Literal["generation", "ocr", "speech", "embeddings"]] = Field(min_length=1)
    kind: Literal["local_openai", "remote_openai"] = "local_openai"
    api_key: SecretStr | None = Field(default=None, repr=False)


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
    evidence_storage_root: Path | None = None
    evidence_clamd_socket: Path | None = None
    evidence_ocr_enabled: bool = False
    evidence_tesseract: str = "tesseract"
    evidence_pdftoppm: str = "pdftoppm"
    evidence_ocr_language: str = "nor+eng"
    evidence_tessdata_dir: Path | None = None
    ai_providers: list[AIProviderSettings] = Field(default_factory=list)
    ai_private_networks: list[str] = Field(default_factory=lambda: ["127.0.0.0/8", "::1/128"])
    ai_remote_synthetic_development: bool = False
    ai_synthetic_manifest: Path | None = None
    ai_evaluation_suites: Path | None = None

    @model_validator(mode="after")
    def safe_configuration(self):
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("Unsupported environment")
        if len({p.key for p in self.ai_providers}) != len(self.ai_providers):
            raise ValueError("AI provider keys must be unique")
        if self.environment != "development" and (
            self.ai_remote_synthetic_development
            or self.ai_synthetic_manifest is not None
            or any(p.kind == "remote_openai" for p in self.ai_providers)
        ):
            raise ValueError("Remote AI and synthetic source attestations require development mode")
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
