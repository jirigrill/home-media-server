"""
Radarr API service
"""

import logging
from typing import Optional

from models.media_item import MediaItem, MediaType
from services.base_service import ArrService

logger = logging.getLogger(__name__)


class RadarrService(ArrService):
    """Radarr API service for managing movies"""
    
    def test_connection(self) -> bool:
        """Test Radarr API connection"""
        response = self._make_request('system/status')
        return response is not None

    def unmonitor_item(self, item: MediaItem) -> bool:
        """Delete a movie completely from Radarr"""
        if item.media_type != MediaType.MOVIE:
            logger.warning(f"RadarrService can only delete movies, got {item.media_type}")
            return False

        try:
            # Find movie - try external IDs first (faster and more reliable), then fallback to name
            external_ids = [
                ('tmdb', item.tmdb_id),  # Primary for movies
                ('imdb', item.imdb_id),  # Fallback
            ]

            movie_id = self._try_external_id_lookups('movie/lookup', external_ids)

            # Fallback to name-based search if all ID lookups fail
            if not movie_id:
                logger.info(f"External ID lookups failed, falling back to name search for: {item.movie_title}")
                movie_id = self._find_movie_by_name(item.movie_title, item.year)

            if not movie_id:
                logger.error(f"Could not find movie for {item} in Radarr")
                return False

            # Delete the movie with deleteFiles=true to remove all metadata and folder
            # addImportExclusion=false allows the movie to be re-added later if needed
            params = {
                'deleteFiles': 'true',
                'addImportExclusion': 'false'
            }

            response = self._make_request(f'movie/{movie_id}', method='DELETE', params=params)
            if response:
                logger.info(f"Successfully deleted movie from Radarr: {item}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting movie {item}: {e}")
            return False
    
    def _find_movie_by_name(self, movie_title: str, year: Optional[int] = None) -> Optional[int]:
        """
        Find movie ID by title using lookup API (fallback when external IDs unavailable).
        Optionally filters by year for better accuracy.
        """
        if not movie_title:
            return None

        # Use base class method to get lookup results
        results = self._lookup_by_name('movie/lookup', movie_title)
        if not results:
            return None

        # Try exact match first (with optional year filtering)
        for result in results:
            if result.get('id'):  # Has ID = already in library
                if result['title'].lower() == movie_title.lower():
                    if year is None or result.get('year') == year:
                        logger.info(f"Found exact name match for '{movie_title}' with ID {result['id']}")
                        return result['id']

        # If we have a year, try matching title without year suffix
        if year is not None:
            title_without_year = movie_title
            for pattern in [f' ({year})', f' {year}']:
                if title_without_year.lower().endswith(pattern.lower()):
                    title_without_year = title_without_year[:-len(pattern)].strip()
                    break

            # Try matching with cleaned title
            if title_without_year.lower() != movie_title.lower():
                for result in results:
                    if result.get('id'):  # Has ID = already in library
                        if result['title'].lower() == title_without_year.lower():
                            if result.get('year') == year:
                                logger.info(f"Found name match (cleaned) for '{title_without_year}' with ID {result['id']}")
                                return result['id']

        logger.warning(f"Movie '{movie_title}' (year: {year}) not found in Radarr library (searched by name)")
        return None