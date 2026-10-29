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
        self.session.headers.update({'Authorization': 'MediaBrowser Token="' + api_key + '"'})
        self.user_id = self._detect_user_id()

    def _detect_user_id(self) -> Optional[str]:
        """Detect a user ID for user-scoped item queries (required by Jellyfin 12+)."""
        try:
            response = self.session.get(f"{self.url}/Users", timeout=10)
            response.raise_for_status()
            users = response.json()
            if users:
                user_id = users[0]['Id']
                logger.info(f"Using Jellyfin user '{users[0].get('Name')}' for item queries")
                return user_id
            logger.warning("No Jellyfin users found for item queries")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to detect Jellyfin user ID: {e}")
        return None

    def get_item(self, item_id: str) -> Optional[Dict]:
        """
        Fetch a single item's raw JSON from Jellyfin by item ID.

        Used to rebuild the context (series name, season/episode numbers,
        provider IDs) of a deletion webhook whose payload was rendered after
        the parent items were already purged from the library.

        Args:
            item_id: Jellyfin item ID

        Returns:
            The item dict as returned by the API, or None if the item cannot
            be fetched (which is expected once it has really been deleted).
        """
        if not item_id:
            return None

        try:
            if self.user_id:
                url = f"{self.url}/Users/{self.user_id}/Items/{item_id}"
            else:
                url = f"{self.url}/Items/{item_id}"
            response = self.session.get(url, timeout=10)
            if response.status_code == 404:
                logger.debug(f"Jellyfin item {item_id} no longer exists (404)")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.debug(f"Could not fetch Jellyfin item {item_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing Jellyfin item {item_id}: {e}")
            return None

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
            if self.user_id:
                url = f"{self.url}/Users/{self.user_id}/Items/{series_id}"
            else:
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
            # Jellyfin 12+ silently ignores AnyProviderIdEquals, so search by
            # name once and verify external IDs on each result instead.
            known_ids = [(n, v) for n, v in
                         [('Tvdb', tvdb_id), ('Imdb', imdb_id), ('Tmdb', tmdb_id)] if v]
            if not known_ids:
                logger.warning(f"No external IDs to verify for '{item_name}', assuming it still exists")
                return True

            params = {
                'Recursive': 'true',
                'SearchTerm': item_name,
                'Limit': 10,
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

            # Verify a result actually carries one of the known provider IDs
            for item in items:
                provider_ids = item.get('ProviderIds', {})
                for provider_name, provider_id in known_ids:
                    if provider_ids.get(provider_name) == provider_id or provider_ids.get(provider_name.lower()) == provider_id:
                        logger.info(f"Found item '{item.get('Name')}' in Jellyfin by {provider_name} ID: {provider_id}")
                        return True

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
