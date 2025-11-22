"""
Webhook processor for handling Jellyfin webhook events
"""

import logging
from typing import Optional

from models.media_item import MediaItem, MediaType
from services.sonarr_service import SonarrService
from services.radarr_service import RadarrService
from services.jellyfin_service import JellyfinService
from utils.parsers import MediaParser

logger = logging.getLogger(__name__)


class WebhookProcessor:
    """Processes Jellyfin webhook events and unmonitors items in *arr services"""

    def __init__(self, sonarr_service: SonarrService, radarr_service: RadarrService, jellyfin_service: Optional[JellyfinService] = None):
        self.sonarr = sonarr_service
        self.radarr = radarr_service
        self.jellyfin = jellyfin_service
    
    def process_removal(self, webhook_data: dict) -> bool:
        """Process item removal webhook from Jellyfin"""
        try:
            logger.debug(f"Starting webhook processing for data: {webhook_data}")

            # Parse webhook data into MediaItem
            item = MediaParser.parse_webhook_data(webhook_data)
            if not item:
                logger.warning("Could not parse webhook data into MediaItem")
                return False

            logger.info(f"Processing removal for: {item}")

            # For episodes/seasons with SeriesId, enrich with series-level external IDs from Jellyfin
            if item.media_type in (MediaType.EPISODE, MediaType.SEASON) and item.series_id and self.jellyfin:
                logger.debug(f"Enriching item with series-level external IDs from Jellyfin (SeriesId: {item.series_id})")
                series_ids = self.jellyfin.get_series_external_ids(item.series_id)
                if series_ids:
                    # Replace episode/season-level IDs with series-level IDs for better matching
                    item.tvdb_id = series_ids.get('tvdb') or item.tvdb_id
                    item.imdb_id = series_ids.get('imdb') or item.imdb_id
                    item.tmdb_id = series_ids.get('tmdb') or item.tmdb_id
                    logger.debug(f"Updated external IDs - TVDB: {item.tvdb_id}, IMDB: {item.imdb_id}, TMDB: {item.tmdb_id}")
                else:
                    logger.warning(f"Could not retrieve series external IDs from Jellyfin for SeriesId: {item.series_id}")

            # Route to appropriate service based on media type
            if item.media_type == MediaType.EPISODE:
                logger.debug(f"Routing to Sonarr for episode: {item}")
                return self.sonarr.unmonitor_item(item)
            elif item.media_type == MediaType.TV_SHOW:
                logger.debug(f"Routing to Sonarr for TV show: {item}")
                return self.sonarr.unmonitor_item(item)
            elif item.media_type == MediaType.SEASON:
                logger.debug(f"Routing to Sonarr for season: {item}")
                return self.sonarr.unmonitor_item(item)
            elif item.media_type == MediaType.MOVIE:
                logger.debug(f"Routing to Radarr for movie: {item}")
                return self.radarr.unmonitor_item(item)
            else:
                logger.warning(f"Unsupported media type: {item.media_type}")
                return False
        
        except Exception as e:
            logger.error(f"Error processing removal webhook: {e}")
            return False
    
    def test_connections(self) -> dict:
        """Test connections to all *arr services"""
        connections = {
            'sonarr': self.sonarr.test_connection(),
            'radarr': self.radarr.test_connection()
        }
        if self.jellyfin:
            connections['jellyfin'] = self.jellyfin.test_connection()
        return connections