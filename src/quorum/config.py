from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration from QUORUM_* environment variables, validated at startup."""

    model_config = SettingsConfigDict(env_prefix="QUORUM_", env_file=".env", extra="ignore")

    database_url: str = Field(pattern=r"^postgres(ql)?://")
    secret_key: str = Field(min_length=32, description="Signs session cookies.")
    secure_cookies: bool = Field(default=False, description="Set true behind HTTPS.")
