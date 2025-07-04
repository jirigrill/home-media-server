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
        """Unmonitor a movie"""
        if item.media_type != MediaType.MOVIE:
            logger.warning(f"RadarrService can only unmonitor movies, got {item.media_type}")
            return False
        
        try:
            # Find movie
            movie_id = self._find_movie(item.movie_title, item.year)
            if not movie_id:
                return False
            
            # Get the full movie object first
            movie_response = self._make_request(f'movie/{movie_id}')
            if not movie_response:
                return False
            
            movie_data = movie_response.json()
            movie_data['monitored'] = False
            
            # Update the movie with monitored=False
            response = self._make_request(f'movie/{movie_id}', method='PUT', data=movie_data)
            if response:
                logger.info(f"Successfully unmonitored movie: {item}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error unmonitoring movie {item}: {e}")
            return False
    
    def _find_movie(self, movie_title: str, year: Optional[int] = None) -> Optional[int]:
        """Find movie ID by title and optional year"""
        response = self._make_request('movie')
        if not response:
            return None
        
        movies = response.json()
        
        # Debug: Log available movies for troubleshooting
        logger.debug(f"Found {len(movies)} movies in Radarr, looking for '{movie_title}' (year: {year})")
        for movie in movies[:5]:  # Log first 5 movies for debugging
            logger.debug(f"Available movie: '{movie['title']}' ({movie.get('year', 'No year')})")
        
        # Try exact match first
        for movie in movies:
            if movie['title'].lower() == movie_title.lower():
                if year is None or movie.get('year') == year:
                    logger.debug(f"Found movie '{movie_title}' with ID {movie['id']} (exact match)")
                    return movie['id']
        
        # If exact match fails and we have a year, try matching title without year suffix
        if year is not None:
            # Remove year suffix patterns like " (2025)" or " 2025"
            title_without_year = movie_title
            for pattern in [f' ({year})', f' {year}']:
                if title_without_year.lower().endswith(pattern.lower()):
                    title_without_year = title_without_year[:-len(pattern)].strip()
                    break
            
            # Try matching with cleaned title
            if title_without_year.lower() != movie_title.lower():
                for movie in movies:
                    if movie['title'].lower() == title_without_year.lower():
                        if movie.get('year') == year:
                            logger.debug(f"Found movie '{title_without_year}' with ID {movie['id']} (cleaned title match)")
                            return movie['id']
        
        logger.warning(f"Movie '{movie_title}' not found in Radarr")
        return None