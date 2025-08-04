"""
Configuration management for Searcherr using Pydantic
"""

from pydantic import Field, HttpUrl, validator
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Configuration settings for Searcherr loaded from .env file"""

    # API Configuration
    radarr_url: HttpUrl = Field(..., description="Radarr base URL")
    radarr_api_key: str = Field(..., description="Radarr API key")
    sonarr_url: HttpUrl = Field(..., description="Sonarr base URL")
    sonarr_api_key: str = Field(..., description="Sonarr API key")

    # Disk Space Configuration
    min_free_space_gb: int = Field(20, ge=1, description="Minimum free space in GB before searching")

    # Search Configuration
    search_interval_hours: int = Field(6, ge=1, description="Hours between search runs")
    max_concurrent_searches: int = Field(5, ge=1, description="Maximum concurrent search operations")
    stalled_download_hours: int = Field(4, ge=1, description="Hours before considering a download stalled")
    search_delay_minutes: int = Field(5, ge=1, description="Minutes to wait between individual searches")
    enable_scheduler: bool = Field(True, description="Enable automatic periodic searching")
    scheduler_interval_hours: int = Field(8, ge=1, description="Hours between automatic search runs")
    scheduler_run_on_startup: bool = Field(True, description="Run first search immediately on startup")

    # Application Configuration
    host: str = Field("0.0.0.0", description="Flask host")  # noqa: S104
    port: int = Field(5001, description="Flask port")
    debug: bool = Field(False, description="Enable debug mode")
    log_level: str = Field("INFO", description="Logging level")
    log_file: str = Field("/app/logs/searcherr.log", description="Log file path")

    @validator("radarr_url", "sonarr_url")
    def strip_trailing_slash(cls, v):  # noqa: N805
        if v is not None:
            return str(v).rstrip("/")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
