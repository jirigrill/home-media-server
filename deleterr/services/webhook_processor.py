"""
Webhook processor for handling Jellyfin webhook events
"""

import logging
from typing import Optional

from models.media_item import MediaItem, MediaType
from services.sonarr_service import SonarrService
from services.radarr_service import RadarrService
from utils.parsers import MediaParser

logger = logging.getLogger(__name__)


class WebhookProcessor:
    """Processes Jellyfin webhook events and unmonitors items in *arr services"""
    
    def __init__(self, sonarr_service: SonarrService, radarr_service: RadarrService):
        self.sonarr = sonarr_service
        self.radarr = radarr_service
    
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
            
            # Route to appropriate service based on media type
            if item.media_type == MediaType.EPISODE:
                logger.debug(f"Routing to Sonarr for episode: {item}")
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
        return {
            'sonarr': self.sonarr.test_connection(),
            'radarr': self.radarr.test_connection()
        }