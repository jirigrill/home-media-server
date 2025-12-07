"""
Sonarr API service
"""

import logging
import re
from typing import Optional

from models.media_item import MediaItem, MediaType
from services.base_service import ArrService

logger = logging.getLogger(__name__)


class SonarrService(ArrService):
    """Sonarr API service for managing TV shows"""

    # Delete parameters for series removal
    DELETE_PARAMS = {
        'deleteFiles': 'true',
        'addImportListExclusion': 'false'
    }

    def test_connection(self) -> bool:
        """Test Sonarr API connection"""
        response = self._make_request('system/status')
        return response is not None

    def _find_series_by_external_ids(self, item: MediaItem, log_error: bool = True) -> Optional[int]:
        """Find series ID using external IDs with standardized error handling

        Args:
            item: MediaItem with external IDs to search
            log_error: Whether to log an error if series not found (default: True)
        """
        external_ids = [
            ('tvdb', item.tvdb_id),  # Primary for TV shows
            ('imdb', item.imdb_id),  # Fallback
            ('tmdb', item.tmdb_id),  # Fallback
        ]
        series_id = self._try_external_id_lookups('series/lookup', external_ids)

        if not series_id and log_error:
            logger.error(
                f"Could not find series '{item.title}' in Sonarr "
                f"(TVDB: {item.tvdb_id}, IMDB: {item.imdb_id}, TMDB: {item.tmdb_id})"
            )
        return series_id

    def unmonitor_item(self, item: MediaItem) -> bool:
        """Delete episode/season/TV show and clean up as needed"""
        if item.media_type == MediaType.TV_SHOW:
            return self._delete_tv_show(item)
        elif item.media_type == MediaType.SEASON:
            return self._delete_season(item)
        elif item.media_type == MediaType.EPISODE:
            return self._process_episode(item)
        else:
            logger.warning(f"SonarrService can only process TV shows, seasons, and episodes, got {item.media_type}")
            return False

    def _process_episode(self, item: MediaItem) -> bool:
        """Delete episode and clean up if it's the last one"""
        try:
            # Find series using external IDs (TVDB, IMDB, TMDB)
            # These should be series-level IDs enriched from Jellyfin API via SeriesId
            series_id = self._find_series_by_external_ids(item)
            if not series_id:
                logger.error("Ensure SeriesId is in webhook and Jellyfin API is accessible.")
                return False

            # Find episode
            episode_id = self._find_episode(series_id, item.season, item.episode)
            if not episode_id:
                return False

            # Delete episode file and unmonitor
            success = self._delete_and_unmonitor_episode(episode_id, item)

            if success:
                # Check if season should be unmonitored (all episodes deleted)
                self._check_and_unmonitor_season_if_empty(series_id, item.season)

                # NOTE: We do NOT auto-delete the series when processing individual episodes
                # Series deletion should only happen when user explicitly deletes the TV show from Jellyfin
                # (which sends a TV_SHOW webhook) to avoid accidentally removing ongoing series

            return success
        except Exception as e:
            logger.error(f"Error processing episode {item}: {e}")
            return False
    
    
    def _find_episode(self, series_id: int, season_number: int, episode_number: int) -> Optional[int]:
        """Find episode ID by series ID, season, and episode number"""
        response = self._make_request('episode', params={'seriesId': series_id})
        if not response:
            return None
        
        episodes = response.json()
        for episode in episodes:
            if (episode['seasonNumber'] == season_number and 
                episode['episodeNumber'] == episode_number):
                logger.debug(f"Found episode S{season_number:02d}E{episode_number:02d} with ID {episode['id']}")
                return episode['id']
        
        logger.warning(f"Episode S{season_number:02d}E{episode_number:02d} not found for series ID {series_id}")
        return None
    
    def _delete_and_unmonitor_episode(self, episode_id: int, item: MediaItem) -> bool:
        """Delete episode file and unmonitor the episode"""
        try:
            # Get episode details to find the file ID
            episode_response = self._make_request(f'episode/{episode_id}')
            if not episode_response:
                return False

            episode_data = episode_response.json()
            episode_file_id = episode_data.get('episodeFileId')

            # Delete the episode file if it exists
            if episode_file_id:
                delete_response = self._make_request(f'episodefile/{episode_file_id}', method='DELETE')
                if delete_response:
                    logger.info(f"Successfully deleted episode file for: {item}")
                else:
                    logger.warning(f"Failed to delete episode file for: {item}")

            # Unmonitor the episode so it doesn't re-download
            episode_data['monitored'] = False
            response = self._make_request(f'episode/{episode_id}', method='PUT', data=episode_data)
            if response:
                logger.info(f"Successfully unmonitored episode: {item}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error processing episode {item}: {e}")
            return False

    def _get_season_episodes(self, series_id: int, season_number: int) -> list:
        """Fetch all episodes for a specific season"""
        response = self._make_request('episode', params={'seriesId': series_id})
        if not response:
            return []

        episodes = response.json()
        return [ep for ep in episodes if ep['seasonNumber'] == season_number]

    def _has_monitored_episodes(self, episodes: list) -> bool:
        """Check if any episodes in the list are still monitored"""
        return any(ep.get('monitored', True) for ep in episodes)

    def _unmonitor_season(self, series_id: int, season_number: int) -> bool:
        """Set season monitored=False in series data"""
        series_response = self._make_request(f'series/{series_id}')
        if not series_response:
            return False

        series_data = series_response.json()
        seasons = series_data.get('seasons', [])

        # Find and unmonitor the specific season
        season_updated = False
        for season in seasons:
            if season['seasonNumber'] == season_number:
                if season.get('monitored', True):
                    season['monitored'] = False
                    season_updated = True
                    logger.debug(f"Marking season {season_number} as unmonitored")
                break

        if not season_updated:
            logger.debug(f"Season {season_number} was already unmonitored or not found")
            return False

        # Update the series with modified season monitoring
        update_response = self._make_request(f'series/{series_id}', method='PUT', data=series_data)
        if update_response:
            logger.info(f"Successfully unmonitored season {season_number} for series ID {series_id}")
            return True
        else:
            logger.error(f"Failed to update season monitoring for series ID {series_id}")
            return False

    def _check_and_unmonitor_season_if_empty(self, series_id: int, season_number: int) -> None:
        """
        Check if all episodes in a season are unmonitored, and if so, unmonitor the season itself.
        After unmonitoring, check if series should be deleted (ended + all seasons unmonitored).
        """
        try:
            # Fetch all episodes for the season
            season_episodes = self._get_season_episodes(series_id, season_number)
            if not season_episodes:
                logger.debug(f"No episodes found for season {season_number}")
                return

            # Check if any episodes are still monitored
            if self._has_monitored_episodes(season_episodes):
                monitored_count = len([ep for ep in season_episodes if ep.get('monitored', True)])
                logger.debug(f"Season {season_number}: {len(season_episodes)} total episodes, {monitored_count} monitored")
                return

            # All episodes are unmonitored, so unmonitor the season
            logger.info(f"All episodes in season {season_number} are unmonitored, unmonitoring season")
            season_unmonitored = self._unmonitor_season(series_id, season_number)

            # After successfully unmonitoring a season, check if series should be deleted
            if season_unmonitored:
                self._check_and_delete_ended_series_if_fully_unmonitored(series_id)

        except Exception as e:
            logger.error(f"Error checking/unmonitoring season {season_number}: {e}")

    def _check_and_delete_ended_series_if_fully_unmonitored(self, series_id: int) -> None:
        """
        Check if series is ended and all seasons unmonitored, then delete it.

        Deletion criteria:
        1. Series status must be "ended"
        2. All regular seasons (excluding season 0/specials) must be unmonitored

        Args:
            series_id: Sonarr series ID to check
        """
        try:
            # Fetch series details from Sonarr
            series_response = self._make_request(f'series/{series_id}')
            if not series_response:
                logger.error(f"Failed to fetch series data for ID {series_id}")
                return

            series_data = series_response.json()
            title = series_data.get('title', 'Unknown')
            status = series_data.get('status', '').lower()
            seasons = series_data.get('seasons', [])

            # Check 1: Must be ended
            if status != 'ended':
                logger.debug(f"Series '{title}' status is '{status}', not ended. Skipping deletion.")
                return

            # Check 2: All regular seasons must be unmonitored (ignore season 0/specials)
            regular_seasons = [s for s in seasons if s.get('seasonNumber', 0) > 0]
            monitored_seasons = [s for s in regular_seasons if s.get('monitored', False)]

            if monitored_seasons:
                season_nums = [s['seasonNumber'] for s in monitored_seasons]
                logger.debug(f"Series '{title}' has monitored seasons: {season_nums}. Skipping deletion.")
                return

            # All criteria met - delete the show
            logger.info(f"Series '{title}' is ended and all seasons unmonitored. Deleting entire show.")
            self._delete_tv_show_by_id(series_id, title)

        except Exception as e:
            logger.error(f"Error checking/deleting ended series {series_id}: {e}")

    def _delete_tv_show_by_id(self, series_id: int, title: str = "Unknown") -> bool:
        """Delete TV show from Sonarr using series ID directly"""
        try:
            params = self.DELETE_PARAMS
            response = self._make_request(f'series/{series_id}', method='DELETE', params=params)
            if response:
                logger.info(f"Successfully deleted TV show '{title}' (ID: {series_id}) from Sonarr")
                return True
            else:
                logger.error(f"Failed to delete TV show '{title}' (ID: {series_id}) from Sonarr")
                return False
        except Exception as e:
            logger.error(f"Error deleting TV show '{title}' (ID: {series_id}): {e}")
            return False

    def _delete_tv_show(self, item: MediaItem) -> bool:
        """Delete entire TV show from Sonarr"""
        try:
            # Find series using external IDs (TVDB, IMDB, TMDB)
            # Don't log error if not found - handle it gracefully below
            series_id = self._find_series_by_external_ids(item, log_error=False)
            if not series_id:
                # Series not found in Sonarr - it may have already been deleted by auto-cleanup
                # This is not an error when processing TV show deletion webhooks
                logger.info(f"Series '{item.title}' not found in Sonarr - already deleted or never added")
                return True  # Return success since the goal (series removed) is achieved

            # Reuse helper method for actual deletion
            return self._delete_tv_show_by_id(series_id, item.title)

        except Exception as e:
            logger.error(f"Error deleting TV show {item}: {e}")
            return False

    def _delete_season_files(self, episodes: list) -> int:
        """Delete all episode files in the list, return count deleted"""
        deleted = 0
        for episode in episodes:
            file_id = episode.get('episodeFileId')
            if file_id:
                delete_response = self._make_request(f'episodefile/{file_id}', method='DELETE')
                if delete_response:
                    deleted += 1
                    logger.debug(f"Deleted file for S{episode['seasonNumber']:02d}E{episode['episodeNumber']:02d}")
        return deleted

    def _unmonitor_episodes(self, episodes: list) -> None:
        """Set monitored=False for all episodes"""
        for episode in episodes:
            episode['monitored'] = False
            self._make_request(f'episode/{episode["id"]}', method='PUT', data=episode)

    def _delete_season(self, item: MediaItem) -> bool:
        """Delete all episodes in a season and unmonitor it"""
        try:
            # Find series using external IDs (TVDB, IMDB, TMDB)
            # These should be series-level IDs enriched from Jellyfin API via SeriesId
            series_id = self._find_series_by_external_ids(item)
            if not series_id:
                logger.error("Ensure SeriesId is in webhook and Jellyfin API is accessible.")
                return False

            # Get all episodes for the season
            season_episodes = self._get_season_episodes(series_id, item.season)
            if not season_episodes:
                logger.warning(f"No episodes found for {item.title} Season {item.season}")
                return False

            logger.info(f"Found {len(season_episodes)} episodes in {item.title} Season {item.season}")

            # Delete episode files and unmonitor all episodes
            deleted = self._delete_season_files(season_episodes)
            logger.info(f"Deleted {deleted} episode file(s) from {item.title} Season {item.season}")

            self._unmonitor_episodes(season_episodes)

            # Unmonitor the season itself
            self._check_and_unmonitor_season_if_empty(series_id, item.season)

            # NOTE: Auto-deletion now happens via _check_and_delete_ended_series_if_fully_unmonitored()
            # called within _check_and_unmonitor_season_if_empty(). This ensures we only delete
            # series that are truly ended AND have all seasons unmonitored.

            return True

        except Exception as e:
            logger.error(f"Error deleting season {item}: {e}")
            return False