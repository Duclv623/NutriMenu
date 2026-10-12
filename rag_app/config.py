from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    app_env: Literal["development", "production"] = "development"
    openai_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_grounding_model: str = "gemini-3.1-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dimensions: int = Field(default=768, ge=128, le=3072)
    gemini_timeout: float = Field(default=45, ge=5, le=120)
    gemini_request_interval: float = Field(default=6.1, ge=0, le=15)
    gemini_burst_requests: int = Field(default=3, ge=1, le=10)
    openai_base_url: str = ""
    openai_model: str = "gpt-4.1-mini"
    grounding_model: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_mode: Literal["gemini", "openai"] = "gemini"
    answer_mode: Literal["gemini", "openai"] = "gemini"
    storage_dir: Path = ROOT / "storage"
    source_manifest: Path = ROOT / "config" / "sources.json"
    top_k: int = Field(default=5, ge=1, le=10)
    chunk_tokens: int = Field(default=420, ge=100, le=1000)
    chunk_overlap: int = Field(default=60, ge=0)
    openai_timeout: float = Field(default=45, ge=5, le=120)
    openai_max_retries: int = Field(default=1, ge=0, le=3)
    rate_limit_per_minute: int = Field(default=20, ge=1, le=300)
    history_retention_days: int = Field(default=7, ge=1, le=30)
    min_dense_score: float = Field(default=0.3, ge=0, le=1)
    jwt_public_key_path: Path | None = None
    jwt_issuer: str = ""
    jwt_audience: str = ""
    food_api_base_url: str = ""

    @model_validator(mode="before")
    @classmethod
    def empty_key_path(cls, values):
        if isinstance(values, dict) and values.get("jwt_public_key_path") == "":
            values["jwt_public_key_path"] = None
        return values

    @model_validator(mode="after")
    def validate_config(self):
        if self.chunk_overlap >= self.chunk_tokens:
            raise ValueError("CHUNK_OVERLAP phải nhỏ hơn CHUNK_TOKENS")
        for field in ("storage_dir", "source_manifest"):
            path = getattr(self, field)
            if not path.is_absolute():
                setattr(self, field, ROOT / path)
        if self.jwt_public_key_path and not self.jwt_public_key_path.is_absolute():
            self.jwt_public_key_path = ROOT / self.jwt_public_key_path
        if self.app_env == "production" and not (
            self.jwt_public_key_path
            and self.jwt_public_key_path.is_file()
            and self.jwt_issuer
            and self.jwt_audience
        ):
            raise ValueError("Production cần JWT_PUBLIC_KEY_PATH, JWT_ISSUER, JWT_AUDIENCE từ TV1")
        if self.food_api_base_url:
            from urllib.parse import urlparse

            url = urlparse(self.food_api_base_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.netloc
                or url.username
                or url.password
            ):
                raise ValueError("FOOD_API_BASE_URL không hợp lệ")
        return self

    @property
    def has_key(self) -> bool:
        key = (self.gemini_api_key if self.answer_mode == 'gemini' else self.openai_api_key).get_secret_value().strip()
        return bool(key) and key not in {"your_key_here", "key_cua_ban"}

    @property
    def active_model(self) -> str:
        return self.gemini_model if self.answer_mode == 'gemini' else self.openai_model

    @property
    def active_embedding_model(self) -> str:
        return self.gemini_embedding_model if self.embedding_mode == 'gemini' else self.embedding_model

    @property
    def embedding_identity(self) -> str:
        if self.embedding_mode == 'gemini':
            return f'gemini:{self.gemini_embedding_model}:dims={self.gemini_embedding_dimensions}:retrieval-v1'
        return self.embedding_model
