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
        """Unmonitor an episode"""
        if item.media_type != MediaType.EPISODE:
            logger.warning(f"SonarrService can only unmonitor episodes, got {item.media_type}")
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
            
            # Unmonitor episode
            success = self._unmonitor_episode(episode_id, item)
            
            if success:
                # Check and unmonitor season if all episodes are unmonitored
                self._check_and_unmonitor_season_if_empty(series_id, item.season)
            
            return success
        except Exception as e:
            logger.error(f"Error unmonitoring episode {item}: {e}")
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
    
    def _unmonitor_episode(self, episode_id: int, item: MediaItem) -> bool:
        """Unmonitor a single episode"""
        try:
            response = self._make_request(f'episode/{episode_id}', method='PUT', data={'monitored': False})
            if response:
                logger.info(f"Successfully unmonitored episode: {item}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error unmonitoring episode {item}: {e}")
            return False
    
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