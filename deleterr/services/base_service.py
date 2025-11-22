"""
Base service class for *arr services
"""

import logging
import requests
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple

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

    def _lookup_by_external_id(self, lookup_endpoint: str, provider: str, external_id: str) -> Optional[int]:
        """
        Lookup item by external provider ID using *arr's lookup endpoint.

        Args:
            lookup_endpoint: The lookup endpoint ('series/lookup' or 'movie/lookup')
            provider: Provider name ('tvdb', 'imdb', or 'tmdb')
            external_id: The external ID value

        Returns:
            Item ID if found in library, None otherwise
        """
        if not external_id:
            return None

        try:
            response = self._make_request(lookup_endpoint, params={'term': f'{provider}:{external_id}'})
            if not response:
                return None

            results = response.json()
            if not results:
                logger.debug(f"No results found for {provider}:{external_id}")
                return None

            # If the item is in the library, it will have an 'id' field
            for result in results:
                if result.get('id'):
                    item_id = result['id']
                    item_title = result.get('title', 'Unknown')
                    logger.info(f"Found '{item_title}' (ID: {item_id}) using {provider.upper()}:{external_id}")
                    return item_id

            # Item exists in indexer but not in library
            logger.warning(f"Item found in indexer for {provider}:{external_id} but not in library")
            return None

        except Exception as e:
            logger.error(f"Error looking up by {provider}:{external_id}: {e}")
            return None

    def _try_external_id_lookups(self, lookup_endpoint: str, external_ids: List[Tuple[str, Optional[str]]]) -> Optional[int]:
        """
        Try looking up item by multiple external IDs in priority order.

        Args:
            lookup_endpoint: The lookup endpoint ('series/lookup' or 'movie/lookup')
            external_ids: List of (provider, id) tuples to try in order

        Returns:
            Item ID if found, None otherwise
        """
        for provider, external_id in external_ids:
            if external_id:
                logger.info(f"Looking up using {provider.upper()} ID: {external_id}")
                item_id = self._lookup_by_external_id(lookup_endpoint, provider, external_id)
                if item_id:
                    return item_id
                logger.debug(f"{provider.upper()} lookup failed, trying next provider")

        return None

    @abstractmethod
    def unmonitor_item(self, item: MediaItem) -> bool:
        """Unmonitor a media item"""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test API connection"""
        pass