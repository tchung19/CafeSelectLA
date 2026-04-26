"""
CafeSelect — Pipeline Configuration
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_HERE = Path(__file__).parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_HERE.parent.parent / "pre_build_validation" / ".env"),
            str(_HERE.parent.parent / ".env"),
            str(_HERE.parent / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_places_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""


def require(name: str, value: str) -> str:
    if not value:
        raise EnvironmentError(f"{name} is not set — add it to .env")
    return value


settings = Settings()
