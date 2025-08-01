"""
Radarr API service implementation
"""

import time
from typing import Any

from .base_service import BaseService


class RadarrService(BaseService):
    """Service for interacting with Radarr API."""

    def __init__(self, base_url: str, api_key: str, search_delay_minutes: int = 5):
        """Initialize RadarrService with configurable search delay."""
        super().__init__(base_url, api_key)
        self.search_delay_minutes = search_delay_minutes

    def get_missing_items(self) -> list[dict[str, Any]]:
        """
        Get list of missing movies from Radarr.

        Returns:
            List of missing movie items
        """
        try:
            # Get all movies with missing status
            response = self._make_request("GET", "movie", params={"monitored": "true"})

            missing_movies = []
            for movie in response:
                if not movie.get("hasFile", False) and movie.get("monitored", False):
                    missing_movies.append(
                        {
                            "id": movie["id"],
                            "title": movie["title"],
                            "year": movie.get("year"),
                            "tmdbId": movie.get("tmdbId"),
                            "imdbId": movie.get("imdbId"),
                            "monitored": movie["monitored"],
                            "hasFile": movie["hasFile"],
                        }
                    )

            self.logger.info(f"Found {len(missing_movies)} missing movies")
            return missing_movies

        except Exception as e:
            self.logger.error(f"Failed to get missing movies: {e}")
            return []

    def search_missing(self, item_id: int) -> bool:
        """
        Trigger search for a specific missing movie.

        Args:
            item_id: Radarr movie ID

        Returns:
            True if search was triggered successfully
        """
        try:
            # Trigger movie search command
            command_data = {"name": "MoviesSearch", "movieIds": [item_id]}

            response = self._make_request("POST", "command", data=command_data)

            if response.get("id"):
                self.logger.info(f"Search triggered for movie ID {item_id}")
                return True
            else:
                self.logger.error(f"Failed to trigger search for movie ID {item_id}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to search for movie ID {item_id}: {e}")
            return False

    def search_all_missing(self, missing_items: list[dict[str, Any]] | None = None) -> bool:
        """
        Trigger search for all missing movies one by one with 5-minute delays.

        Args:
            missing_items: Optional pre-fetched missing items list to avoid duplicate API call

        Returns:
            True if all searches were triggered successfully
        """
        try:
            # Use provided missing items or fetch them
            if missing_items is None:
                missing_movies = self.get_missing_items()
            else:
                missing_movies = missing_items

            if not missing_movies:
                self.logger.info("No missing movies found")
                return True

            self.logger.info(f"Starting search for {len(missing_movies)} missing movies")

            # Search each movie individually with 5-minute delay
            for i, movie in enumerate(missing_movies, 1):
                movie_id = movie["id"]
                movie_title = movie.get("title", "Unknown")

                self.logger.info(f"Searching for movie {i}/{len(missing_movies)}: {movie_title} (ID: {movie_id})")

                search_success = self.search_missing(movie_id)
                if not search_success:
                    self.logger.warning(f"Failed to trigger search for {movie_title}")

                # Wait configured delay before next search (except for the last item)
                if i < len(missing_movies):
                    self.logger.info(f"Waiting {self.search_delay_minutes} minutes before searching next movie...")
                    time.sleep(self.search_delay_minutes * 60)  # Convert minutes to seconds

            self.logger.info(f"Completed search cycle for all {len(missing_movies)} missing movies")
            return True

        except Exception as e:
            self.logger.error(f"Failed to search all missing movies: {e}")
            return False
