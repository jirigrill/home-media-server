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
    
    def test_connection(self) -> bool:
        """Test Sonarr API connection"""
        response = self._make_request('system/status')
        return response is not None

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
            external_ids = [
                ('tvdb', item.tvdb_id),  # Primary for TV shows
                ('imdb', item.imdb_id),  # Fallback
                ('tmdb', item.tmdb_id),  # Fallback
            ]

            series_id = self._try_external_id_lookups('series/lookup', external_ids)

            if not series_id:
                logger.error(f"Could not find series for {item} in Sonarr using external IDs (TVDB: {item.tvdb_id}, IMDB: {item.imdb_id}, TMDB: {item.tmdb_id}). Ensure SeriesId is in webhook and Jellyfin API is accessible.")
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

    def _check_and_delete_series_if_ended(self, series_id: int, item: MediaItem) -> None:
        """Delete entire series if it's ended and has no more episode files"""
        try:
            # Get series details
            series_response = self._make_request(f'series/{series_id}')
            if not series_response:
                return

            series_data = series_response.json()
            series_status = series_data.get('status', '').lower()
            series_title = series_data.get('title', 'Unknown')

            # Only proceed if series has ended
            if series_status != 'ended':
                logger.debug(f"Series '{series_title}' is {series_status}, not deleting")
                return

            # Check if there are any remaining episode files
            episodes_response = self._make_request('episode', params={'seriesId': series_id})
            if not episodes_response:
                return

            episodes = episodes_response.json()
            episodes_with_files = [ep for ep in episodes if ep.get('hasFile', False)]

            if len(episodes_with_files) == 0:
                # No more episode files - delete the entire series
                logger.info(f"Series '{series_title}' has ended and has no episode files, deleting from Sonarr")

                params = {
                    'deleteFiles': 'true',  # Delete any remaining metadata
                    'addImportListExclusion': 'false'  # Allow re-adding if needed
                }

                delete_response = self._make_request(f'series/{series_id}', method='DELETE', params=params)
                if delete_response:
                    logger.info(f"Successfully deleted ended series '{series_title}' from Sonarr")
                else:
                    logger.error(f"Failed to delete series '{series_title}'")
            else:
                logger.debug(f"Series '{series_title}' still has {len(episodes_with_files)} episode(s) with files, keeping in Sonarr")

        except Exception as e:
            logger.error(f"Error checking/deleting series: {e}")
    
    def _check_and_unmonitor_season_if_empty(self, series_id: int, season_number: int) -> None:
        """
        Check if all episodes in a season are unmonitored, and if so, unmonitor the season itself.
        Combines checking and unmonitoring logic into a single method.
        """
        try:
            # Fetch all episodes for the series
            response = self._make_request('episode', params={'seriesId': series_id})
            if not response:
                return

            episodes = response.json()
            season_episodes = [ep for ep in episodes if ep['seasonNumber'] == season_number]

            if not season_episodes:
                logger.debug(f"No episodes found for season {season_number}")
                return

            # Check if all episodes in the season are unmonitored
            monitored_episodes = [ep for ep in season_episodes if ep.get('monitored', True)]

            logger.debug(f"Season {season_number}: {len(season_episodes)} total episodes, {len(monitored_episodes)} monitored")

            # If there are still monitored episodes, don't unmonitor the season
            if len(monitored_episodes) > 0:
                return

            # All episodes are unmonitored, so unmonitor the season
            logger.info(f"All episodes in season {season_number} are unmonitored, unmonitoring season")

            # Get series data to modify season monitoring
            series_response = self._make_request(f'series/{series_id}')
            if not series_response:
                return

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
                return

            # Update the series with modified season monitoring
            update_response = self._make_request(f'series/{series_id}', method='PUT', data=series_data)
            if update_response:
                logger.info(f"Successfully unmonitored season {season_number} for series ID {series_id}")
            else:
                logger.error(f"Failed to update season monitoring for series ID {series_id}")

        except Exception as e:
            logger.error(f"Error checking/unmonitoring season {season_number}: {e}")

    def _delete_tv_show(self, item: MediaItem) -> bool:
        """Delete entire TV show from Sonarr"""
        try:
            # Find series using external IDs (TVDB, IMDB, TMDB)
            external_ids = [
                ('tvdb', item.tvdb_id),  # Primary for TV shows
                ('imdb', item.imdb_id),  # Fallback
                ('tmdb', item.tmdb_id),  # Fallback
            ]

            series_id = self._try_external_id_lookups('series/lookup', external_ids)

            if not series_id:
                logger.error(f"Could not find TV show '{item.title}' in Sonarr using external IDs (TVDB: {item.tvdb_id}, IMDB: {item.imdb_id}, TMDB: {item.tmdb_id})")
                return False

            # Delete the entire series
            params = {
                'deleteFiles': 'true',  # Delete all files
                'addImportListExclusion': 'false'  # Allow re-adding if needed
            }

            response = self._make_request(f'series/{series_id}', method='DELETE', params=params)
            if response:
                logger.info(f"Successfully deleted TV show from Sonarr: {item}")
                return True
            else:
                logger.error(f"Failed to delete TV show '{item.title}' from Sonarr")
                return False

        except Exception as e:
            logger.error(f"Error deleting TV show {item}: {e}")
            return False

    def _delete_season(self, item: MediaItem) -> bool:
        """Delete all episodes in a season and unmonitor it"""
        try:
            # Find series using external IDs (TVDB, IMDB, TMDB)
            # These should be series-level IDs enriched from Jellyfin API via SeriesId
            external_ids = [
                ('tvdb', item.tvdb_id),  # Primary for TV shows
                ('imdb', item.imdb_id),  # Fallback
                ('tmdb', item.tmdb_id),  # Fallback
            ]

            series_id = self._try_external_id_lookups('series/lookup', external_ids)

            if not series_id:
                logger.error(f"Could not find TV show '{item.title}' in Sonarr using external IDs (TVDB: {item.tvdb_id}, IMDB: {item.imdb_id}, TMDB: {item.tmdb_id}). Ensure SeriesId is in webhook and Jellyfin API is accessible.")
                return False

            # Get all episodes for this series
            episodes_response = self._make_request('episode', params={'seriesId': series_id})
            if not episodes_response:
                return False

            episodes = episodes_response.json()
            season_episodes = [ep for ep in episodes if ep['seasonNumber'] == item.season]

            if not season_episodes:
                logger.warning(f"No episodes found for {item.title} Season {item.season}")
                return False

            logger.info(f"Found {len(season_episodes)} episodes in {item.title} Season {item.season}")

            # Delete episode files and unmonitor all episodes in the season
            deleted_count = 0
            for episode in season_episodes:
                episode_file_id = episode.get('episodeFileId')

                # Delete the episode file if it exists
                if episode_file_id:
                    delete_response = self._make_request(f'episodefile/{episode_file_id}', method='DELETE')
                    if delete_response:
                        deleted_count += 1
                        logger.debug(f"Deleted file for S{episode['seasonNumber']:02d}E{episode['episodeNumber']:02d}")

                # Unmonitor the episode
                episode['monitored'] = False
                self._make_request(f'episode/{episode["id"]}', method='PUT', data=episode)

            logger.info(f"Deleted {deleted_count} episode file(s) from {item.title} Season {item.season}")

            # Unmonitor the season itself
            self._check_and_unmonitor_season_if_empty(series_id, item.season)

            # NOTE: We do NOT auto-delete the series when processing season deletions
            # Series deletion should only happen when user explicitly deletes the TV show from Jellyfin
            # (which sends a TV_SHOW webhook) to avoid accidentally removing ongoing series

            return True

        except Exception as e:
            logger.error(f"Error deleting season {item}: {e}")
            return False