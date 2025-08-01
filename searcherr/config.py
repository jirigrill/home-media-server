"""
Configuration management for Searcherr using Pydantic
"""


from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Configuration settings for Searcherr loaded from .env file"""

    # API Configuration
    radarr_url: str = Field(..., description="Radarr base URL")
    radarr_api_key: str = Field(..., description="Radarr API key")
    sonarr_url: str | None = Field(None, description="Sonarr base URL (future use)")
    sonarr_api_key: str | None = Field(
        None, description="Sonarr API key (future use)"
    )

    # Disk Space Configuration
    min_free_space_gb: int = Field(
        20, description="Minimum free space in GB before searching"
    )

    # Search Configuration
    search_interval_hours: int = Field(6, description="Hours between search runs")
    max_concurrent_searches: int = Field(
        5, description="Maximum concurrent search operations"
    )
    stalled_download_hours: int = Field(
        4, description="Hours before considering a download stalled"
    )
    search_delay_minutes: int = Field(
        5, description="Minutes to wait between individual searches"
    )

    # Application Configuration
    host: str = Field("0.0.0.0", description="Flask host")  # noqa: S104
    port: int = Field(5001, description="Flask port")
    debug: bool = Field(False, description="Enable debug mode")
    log_level: str = Field("INFO", description="Logging level")
    log_file: str = Field("/app/logs/searcherr.log", description="Log file path")

    @validator("min_free_space_gb")
    def validate_min_space(cls, v):  # noqa: N805
        if v < 1:
            raise ValueError("min_free_space_gb must be at least 1")
        return v

    @validator("search_interval_hours")
    def validate_interval(cls, v):  # noqa: N805
        if v < 1:
            raise ValueError("search_interval_hours must be at least 1")
        return v

    @validator("stalled_download_hours")
    def validate_stalled_hours(cls, v):  # noqa: N805
        if v < 1:
            raise ValueError("stalled_download_hours must be at least 1")
        return v

    @validator("search_delay_minutes")
    def validate_search_delay(cls, v):  # noqa: N805
        if v < 1:
            raise ValueError("search_delay_minutes must be at least 1")
        return v

    @validator("radarr_url")
    def validate_radarr_url(cls, v):  # noqa: N805
        if not v:
            raise ValueError("radarr_url is required")
        if not v.startswith(("http://", "https://")):
            raise ValueError("radarr_url must start with http:// or https://")
        return v.rstrip("/")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
