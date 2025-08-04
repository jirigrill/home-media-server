"""
Sonarr API service implementation
"""

import time
from typing import Any

from .base_service import BaseService


class SonarrService(BaseService):
    """Service for interacting with Sonarr API."""

    def __init__(self, base_url: str, api_key: str, search_delay_minutes: int = 5):
        """Initialize SonarrService with configurable search delay."""
        super().__init__(base_url, api_key)
        self.search_delay_minutes = search_delay_minutes

    def get_missing_items(self) -> list[dict[str, Any]]:
        """
        Get list of missing episodes from Sonarr.

        Returns:
            List of missing episode items
        """
        try:
            # Get all series with missing episodes
            response = self._make_request("GET", "series", params={"monitored": "true"})

            missing_episodes = []
            for series in response:
                if series.get("monitored", False):
                    # Get episodes for this series
                    try:
                        episodes_response = self._make_request(
                            "GET", "episode", params={"seriesId": series["id"]}
                        )

                        for episode in episodes_response:
                            if (
                                not episode.get("hasFile", False)
                                and episode.get("monitored", False)
                                and not episode.get("unverifiedSceneNumbering", False)
                            ):
                                missing_episodes.append(
                                    {
                                        "id": episode["id"],
                                        "seriesId": series["id"],
                                        "title": (
                                            f"{series['title']} - "
                                            f"S{episode.get('seasonNumber', 0):02d}"
                                            f"E{episode.get('episodeNumber', 0):02d}"
                                        ),
                                        "seriesTitle": series["title"],
                                        "seasonNumber": episode.get("seasonNumber"),
                                        "episodeNumber": episode.get("episodeNumber"),
                                        "episodeTitle": episode.get("title", "Unknown"),
                                        "airDate": episode.get("airDate"),
                                        "monitored": episode["monitored"],
                                        "hasFile": episode["hasFile"],
                                    }
                                )
                    except Exception as e:
                        self.logger.warning(f"Failed to get episodes for series {series['title']}: {e}")
                        continue

            self.logger.info(f"Found {len(missing_episodes)} missing episodes")
            return missing_episodes

        except Exception as e:
            self.logger.error(f"Failed to get missing episodes: {e}")
            return []

    def search_missing(self, item_id: int) -> bool:
        """
        Trigger search for a specific missing episode.

        Args:
            item_id: Sonarr episode ID

        Returns:
            True if search was triggered successfully
        """
        try:
            # Trigger episode search command
            command_data = {"name": "EpisodeSearch", "episodeIds": [item_id]}

            response = self._make_request("POST", "command", data=command_data)

            if response.get("id"):
                self.logger.info(f"Search triggered for episode ID {item_id}")
                return True
            else:
                self.logger.error(f"Failed to trigger search for episode ID {item_id}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to search for episode ID {item_id}: {e}")
            return False

    def search_all_missing(self, missing_items: list[dict[str, Any]] | None = None) -> bool:
        """
        Trigger search for all missing episodes one by one with configurable delays.

        Args:
            missing_items: Optional pre-fetched missing items list to avoid duplicate API call

        Returns:
            True if all searches were triggered successfully
        """
        try:
            # Use provided missing items or fetch them
            if missing_items is None:
                missing_episodes = self.get_missing_items()
            else:
                missing_episodes = missing_items

            if not missing_episodes:
                self.logger.info("No missing episodes found")
                return True

            self.logger.info(f"Starting search for {len(missing_episodes)} missing episodes")

            # Search each episode individually with configurable delay
            for i, episode in enumerate(missing_episodes, 1):
                episode_id = episode["id"]
                episode_title = episode.get("title", "Unknown")

                self.logger.info(
                    f"Searching for episode {i}/{len(missing_episodes)}: {episode_title} (ID: {episode_id})"
                )

                search_success = self.search_missing(episode_id)
                if not search_success:
                    self.logger.warning(f"Failed to trigger search for {episode_title}")

                # Wait configured delay before next search (except for the last item)
                if i < len(missing_episodes):
                    self.logger.info(f"Waiting {self.search_delay_minutes} minutes before searching next episode...")
                    time.sleep(self.search_delay_minutes * 60)  # Convert minutes to seconds

            self.logger.info(f"Completed search cycle for all {len(missing_episodes)} missing episodes")
            return True

        except Exception as e:
            self.logger.error(f"Failed to search all missing episodes: {e}")
            return False

