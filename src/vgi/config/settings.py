"""Secrets from .env / environment. Never written into manifests."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    hf_token: str = Field(default="", alias="HF_TOKEN")
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    ig_user_id: str = Field(default="", alias="IG_USER_ID")
    ig_access_token: str = Field(default="", alias="IG_ACCESS_TOKEN")

    def has_claude(self) -> bool:
        return bool(self.anthropic_api_key)


def load_secrets() -> Secrets:
    return Secrets()
