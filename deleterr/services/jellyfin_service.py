"""
Jellyfin API service for fetching series metadata
"""

import logging
import requests
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class JellyfinService:
    """Jellyfin API service for fetching series information"""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({'X-MediaBrowser-Token': api_key})

    def get_series_external_ids(self, series_id: str) -> Optional[Dict[str, str]]:
        """
        Get series-level external IDs (TVDB, IMDB, TMDB) from Jellyfin.

        Args:
            series_id: Jellyfin series ID

        Returns:
            Dictionary with provider IDs: {'tvdb': '...', 'imdb': '...', 'tmdb': '...'}
            Returns None if request fails
        """
        if not series_id:
            return None

        try:
            # Query Jellyfin API for series details
            url = f"{self.url}/Items/{series_id}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            series_data = response.json()
            series_name = series_data.get('Name', 'Unknown')

            # Extract external provider IDs
            provider_ids = series_data.get('ProviderIds', {})

            external_ids = {
                'tvdb': provider_ids.get('Tvdb') or provider_ids.get('tvdb'),
                'imdb': provider_ids.get('Imdb') or provider_ids.get('imdb'),
                'tmdb': provider_ids.get('Tmdb') or provider_ids.get('tmdb'),
            }

            logger.info(f"Retrieved external IDs for series '{series_name}' from Jellyfin: TVDB={external_ids.get('tvdb')}, IMDB={external_ids.get('imdb')}, TMDB={external_ids.get('tmdb')}")

            return external_ids

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch series {series_id} from Jellyfin: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing Jellyfin response for series {series_id}: {e}")
            return None

    def test_connection(self) -> bool:
        """Test Jellyfin API connection"""
        try:
            response = self.session.get(f"{self.url}/System/Info", timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Jellyfin API connection test failed: {e}")
            return False
