"""
Configuration module for Deleterr
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Application configuration"""
    # Server settings
    host: str = '0.0.0.0'
    port: int = 5000
    debug: bool = False
    
    # Sonarr settings
    sonarr_url: str = 'http://sonarr:8989'
    sonarr_api_key: Optional[str] = None
    
    # Radarr settings
    radarr_url: str = 'http://radarr:7878'
    radarr_api_key: Optional[str] = None

    # Jellyfin settings (optional - for enhanced series lookup)
    jellyfin_url: Optional[str] = None
    jellyfin_api_key: Optional[str] = None

    # Logging settings
    log_level: str = 'INFO'
    log_file: str = '/app/logs/deleterr.log'
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Create configuration from environment variables"""
        return cls(
            host=os.getenv('DELETERR_HOST', '0.0.0.0'),
            port=int(os.getenv('DELETERR_PORT', '5000')),
            debug=os.getenv('DELETERR_DEBUG', 'false').lower() == 'true',
            
            sonarr_url=os.getenv('SONARR_URL', 'http://sonarr:8989'),
            sonarr_api_key=os.getenv('SONARR_API_KEY'),

            radarr_url=os.getenv('RADARR_URL', 'http://radarr:7878'),
            radarr_api_key=os.getenv('RADARR_API_KEY'),

            jellyfin_url=os.getenv('JELLYFIN_URL', 'http://jellyfin:8096'),
            jellyfin_api_key=os.getenv('JELLYFIN_API_KEY'),

            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            log_file=os.getenv('LOG_FILE', '/app/logs/deleterr.log')
        )
    
    def validate(self) -> None:
        """Validate configuration"""
        if not self.sonarr_api_key:
            raise ValueError("SONARR_API_KEY is required")
        if not self.radarr_api_key:
            raise ValueError("RADARR_API_KEY is required")