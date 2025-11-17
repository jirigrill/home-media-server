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
        """Delete episode and clean up if it's the last one"""
        if item.media_type != MediaType.EPISODE:
            logger.warning(f"SonarrService can only process episodes, got {item.media_type}")
            return False

        try:
            # Find series - try external IDs first (faster and more reliable), then fallback to name
            external_ids = [
                ('tvdb', item.tvdb_id),  # Primary for TV shows
                ('imdb', item.imdb_id),  # Fallback
                ('tmdb', item.tmdb_id),  # Fallback
            ]

            series_id = self._try_external_id_lookups('series/lookup', external_ids)

            # Fallback to name-based search if all ID lookups fail
            if not series_id:
                logger.info(f"External ID lookups failed, falling back to name search for: {item.series_name}")
                series_id = self._find_series_by_name(item.series_name)

            if not series_id:
                logger.error(f"Could not find series for {item} in Sonarr")
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

                # Check if we should delete the entire series (if ended and no files left)
                self._check_and_delete_series_if_ended(series_id, item)

            return success
        except Exception as e:
            logger.error(f"Error processing episode {item}: {e}")
            return False
    
    def _find_series_by_name(self, series_name: str) -> Optional[int]:
        """
        Find series ID by name using lookup API (fallback when external IDs unavailable).
        Uses fuzzy matching to handle name variations.
        """
        if not series_name:
            return None

        # Use base class method to get lookup results
        results = self._lookup_by_name('series/lookup', series_name)
        if not results:
            return None

        series_name_clean = self._clean_series_name(series_name)

        # First try exact match on results that are already in library
        for result in results:
            if result.get('id'):  # Has ID = already in library
                if result['title'].lower() == series_name.lower():
                    logger.info(f"Found exact name match for '{series_name}' with ID {result['id']}")
                    return result['id']

        # Then try fuzzy matching on results in library
        for result in results:
            if result.get('id'):  # Has ID = already in library
                result_title_clean = self._clean_series_name(result['title'])
                if result_title_clean == series_name_clean:
                    logger.info(f"Found fuzzy name match for '{series_name}' -> '{result['title']}' with ID {result['id']}")
                    return result['id']

        logger.warning(f"Series '{series_name}' not found in Sonarr library (searched by name)")
        return None
    
    def _clean_series_name(self, name: str) -> str:
        """Clean series name for fuzzy matching"""
        # Remove common variations: years, special chars, extra spaces
        cleaned = re.sub(r'\s*\(\d{4}\)\s*', '', name)  # Remove (YYYY)
        cleaned = re.sub(r'\s*\[\d{4}\]\s*', '', cleaned)  # Remove [YYYY]
        cleaned = re.sub(r'[^\w\s]', '', cleaned)  # Remove special chars
        cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()  # Normalize spaces
        return cleaned
    
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