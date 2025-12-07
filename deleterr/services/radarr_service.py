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

    # Delete parameters for movie removal
    DELETE_PARAMS = {
        'deleteFiles': 'true',
        'addImportExclusion': 'false'
    }

    def test_connection(self) -> bool:
        """Test Radarr API connection"""
        response = self._make_request('system/status')
        return response is not None

    def _find_movie_by_external_ids(self, item: MediaItem) -> Optional[int]:
        """Find movie ID using external IDs with standardized error handling"""
        external_ids = [
            ('tmdb', item.tmdb_id),  # Primary for movies
            ('imdb', item.imdb_id),  # Fallback
        ]
        movie_id = self._try_external_id_lookups('movie/lookup', external_ids)

        if not movie_id:
            logger.error(
                f"Could not find movie '{item.title}' in Radarr "
                f"(TMDB: {item.tmdb_id}, IMDB: {item.imdb_id})"
            )
        return movie_id

    def unmonitor_item(self, item: MediaItem) -> bool:
        """Delete a movie completely from Radarr"""
        if item.media_type != MediaType.MOVIE:
            logger.warning(f"RadarrService can only delete movies, got {item.media_type}")
            return False

        try:
            # Find movie using external IDs (TMDB, IMDB)
            movie_id = self._find_movie_by_external_ids(item)
            if not movie_id:
                return False

            # Delete the movie using class constant
            response = self._make_request(f'movie/{movie_id}', method='DELETE', params=self.DELETE_PARAMS)
            if response:
                logger.info(f"Successfully deleted movie from Radarr: {item}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting movie {item}: {e}")
            return False
