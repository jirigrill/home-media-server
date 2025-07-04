"""
Base service class for *arr services
"""

import logging
import requests
from abc import ABC, abstractmethod
from typing import Optional

from models.media_item import MediaItem

logger = logging.getLogger(__name__)


class ArrService(ABC):
    """Base class for *arr services (Sonarr, Radarr)"""
    
    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({'X-Api-Key': api_key})
    
    def _make_request(self, endpoint: str, method: str = 'GET', 
                     data: Optional[dict] = None, 
                     params: Optional[dict] = None) -> Optional[requests.Response]:
        """Make HTTP request to *arr API"""
        try:
            url = f"{self.url}/api/v3/{endpoint}"
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {self.__class__.__name__}: {e}")
            return None
    
    @abstractmethod
    def unmonitor_item(self, item: MediaItem) -> bool:
        """Unmonitor a media item"""
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """Test API connection"""
        pass