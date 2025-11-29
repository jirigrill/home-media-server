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

    def item_exists_in_library(self, item_name: str, tvdb_id: Optional[str] = None,
                               imdb_id: Optional[str] = None, tmdb_id: Optional[str] = None,
                               item_type: Optional[str] = None) -> bool:
        """
        Check if an item still exists in Jellyfin's library.
        This is used to distinguish between quality upgrades (item still exists with new file)
        and actual deletions (item completely removed from library).

        Args:
            item_name: Name of the movie/show to search for
            tvdb_id: TVDB ID for TV shows
            imdb_id: IMDB ID
            tmdb_id: TMDB ID
            item_type: Optional item type filter ('Movie', 'Series', 'Episode')

        Returns:
            True if the item exists in the library, False otherwise
        """
        try:
            # Try each external ID using Jellyfin's AnyProviderIdEquals parameter
            for provider_id, provider_name in [(tvdb_id, 'Tvdb'), (imdb_id, 'Imdb'), (tmdb_id, 'Tmdb')]:
                if not provider_id:
                    continue

                params = {
                    'Recursive': 'true',
                    'AnyProviderIdEquals': provider_id,
                    'Limit': 1,
                    'Fields': 'ProviderIds',
                }

                # Set item type filter
                if item_type:
                    if item_type.lower() in ['episode', 'season', 'series', 'tv_show', 'tvshow']:
                        params['IncludeItemTypes'] = 'Series'
                    elif item_type.lower() == 'movie':
                        params['IncludeItemTypes'] = 'Movie'

                response = self.session.get(
                    f"{self.url}/Items",
                    params=params,
                    timeout=10
                )
                response.raise_for_status()
                result = response.json()
                items = result.get('Items', [])

                # Verify the returned item actually has the provider ID we searched for
                if items:
                    item = items[0]
                    provider_ids = item.get('ProviderIds', {})

                    # Check if the provider ID matches (case-insensitive)
                    if provider_ids.get(provider_name) == provider_id or provider_ids.get(provider_name.lower()) == provider_id:
                        logger.info(f"Found item '{item.get('Name')}' in Jellyfin by {provider_name} ID: {provider_id}")
                        return True
                    else:
                        logger.debug(f"Item returned but provider ID doesn't match (expected {provider_name}={provider_id}, got {provider_ids})")

            logger.info(f"Item '{item_name}' not found in Jellyfin library (IDs: TVDB={tvdb_id}, IMDB={imdb_id}, TMDB={tmdb_id})")
            return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to search Jellyfin library: {e}")
            # Fail-safe: assume item exists on error to avoid accidental unmonitoring
            return True
        except Exception as e:
            logger.error(f"Error checking if item exists in Jellyfin: {e}")
            # Fail-safe: assume item exists on error to avoid accidental unmonitoring
            return True

    def test_connection(self) -> bool:
        """Test Jellyfin API connection"""
        try:
            response = self.session.get(f"{self.url}/System/Info", timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Jellyfin API connection test failed: {e}")
            return False
