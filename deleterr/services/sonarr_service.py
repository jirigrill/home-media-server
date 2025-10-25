"""
Sonarr API service
"""

import logging
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
            # Find series
            series_id = self._find_series(item.series_name)
            if not series_id:
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
    
    def _find_series(self, series_name: str) -> Optional[int]:
        """Find series ID by name with fuzzy matching"""
        response = self._make_request('series')
        if not response:
            return None
        
        series_list = response.json()
        series_name_clean = self._clean_series_name(series_name)
        
        # First try exact match
        for series in series_list:
            if series['title'].lower() == series_name.lower():
                logger.debug(f"Found exact match for series '{series_name}' with ID {series['id']}")
                return series['id']
        
        # Then try fuzzy matching
        for series in series_list:
            sonarr_title_clean = self._clean_series_name(series['title'])
            if sonarr_title_clean == series_name_clean:
                logger.debug(f"Found fuzzy match for series '{series_name}' -> '{series['title']}' with ID {series['id']}")
                return series['id']
        
        # Log available series for debugging
        available_series = [s['title'] for s in series_list]
        logger.warning(f"Series '{series_name}' not found in Sonarr. Available series: {available_series[:10]}{'...' if len(available_series) > 10 else ''}")
        return None
    
    def _clean_series_name(self, name: str) -> str:
        """Clean series name for fuzzy matching"""
        import re
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
        """Check if season has no monitored episodes and unmonitor season if empty"""
        try:
            if self._is_season_completely_unmonitored(series_id, season_number):
                logger.info(f"All episodes in season {season_number} are unmonitored, unmonitoring season")
                self._unmonitor_season(series_id, season_number)
        except Exception as e:
            logger.error(f"Error checking/unmonitoring season {season_number}: {e}")
    
    def _is_season_completely_unmonitored(self, series_id: int, season_number: int) -> bool:
        """Check if all episodes in a season are unmonitored"""
        try:
            response = self._make_request('episode', params={'seriesId': series_id})
            if not response:
                return False
            
            episodes = response.json()
            season_episodes = [ep for ep in episodes if ep['seasonNumber'] == season_number]
            
            if not season_episodes:
                logger.debug(f"No episodes found for season {season_number}")
                return False
            
            # Check if all episodes in the season are unmonitored
            monitored_episodes = [ep for ep in season_episodes if ep.get('monitored', True)]
            
            logger.debug(f"Season {season_number}: {len(season_episodes)} total episodes, {len(monitored_episodes)} monitored")
            return len(monitored_episodes) == 0
            
        except Exception as e:
            logger.error(f"Error checking season {season_number} monitoring status: {e}")
            return False
    
    def _unmonitor_season(self, series_id: int, season_number: int) -> bool:
        """Unmonitor a specific season"""
        try:
            # Get series data to modify season monitoring
            response = self._make_request(f'series/{series_id}')
            if not response:
                return False
            
            series_data = response.json()
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
                return True
            
            # Update the series with modified season monitoring
            response = self._make_request(f'series/{series_id}', method='PUT', data=series_data)
            if response:
                logger.info(f"Successfully unmonitored season {season_number} for series ID {series_id}")
                return True
            else:
                logger.error(f"Failed to update season monitoring for series ID {series_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error unmonitoring season {season_number}: {e}")
            return False