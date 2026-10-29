"""
Webhook processor for handling Jellyfin webhook events
"""

import json
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

    def process_removal(self, webhook_data: dict) -> Optional[bool]:
        """Process item removal webhook from Jellyfin.

        Returns:
            True  - handled (unmonitored/deleted, or intentionally preserved)
            False - the item was identified but the *arr call failed
            None  - the item could not be identified; nothing to act on
        """
        try:
            logger.debug(f"Starting webhook processing for data: {webhook_data}")

            # Parse webhook data into MediaItem
            item = MediaParser.parse_webhook_data(webhook_data)

            if not item:
                # Jellyfin renders its template from metadata that may already be
                # gone by the time the notification is sent (Media Cleaner purges
                # a whole show/season in one batch). Try to rebuild the context
                # from the Jellyfin API before giving up.
                item = self._reparse_with_jellyfin(webhook_data)

            if not item:
                logger.warning(
                    "Could not identify item from webhook payload; nothing to unmonitor. "
                    f"Payload: {json.dumps(webhook_data, default=str)[:1000]}"
                )
                return None

            logger.info(f"Processing removal for: {item}")

            # IMPORTANT: Check if movie still exists in Jellyfin library before unmonitoring
            # This prevents unmonitoring movies during quality upgrades (old file deleted, new file added)
            if self.jellyfin and item.media_type == MediaType.MOVIE:
                logger.debug(f"Checking if movie '{item.title}' still exists in Jellyfin library")
                item_exists = self.jellyfin.item_exists_in_library(
                    item_name=item.title,
                    tvdb_id=item.tvdb_id,
                    imdb_id=item.imdb_id,
                    tmdb_id=item.tmdb_id,
                    item_type=item.media_type.value
                )

                if item_exists:
                    logger.info(f"[SKIP] Skipping unmonitor - movie still exists in Jellyfin (likely a quality upgrade): {item.title}")
                    return True  # Return success since no error occurred
                else:
                    logger.info(f"[OK] Movie confirmed deleted from Jellyfin - proceeding with unmonitor")

            # For episodes/seasons with SeriesId, enrich with series-level external IDs from Jellyfin
            # This ensures we have series IDs for proper Sonarr matching
            if item.media_type in (MediaType.EPISODE, MediaType.SEASON) and item.series_id and self.jellyfin:
                logger.debug(f"Enriching item with series-level external IDs from Jellyfin (SeriesId: {item.series_id})")
                series_ids = self.jellyfin.get_series_external_ids(item.series_id)
                if series_ids:
                    # Replace episode/season-level IDs with series-level IDs for better matching in Sonarr
                    item.tvdb_id = series_ids.get('tvdb') or item.tvdb_id
                    item.imdb_id = series_ids.get('imdb') or item.imdb_id
                    item.tmdb_id = series_ids.get('tmdb') or item.tmdb_id
                    logger.debug(f"Updated external IDs - TVDB: {item.tvdb_id}, IMDB: {item.imdb_id}, TMDB: {item.tmdb_id}")
                else:
                    logger.warning(f"Could not retrieve series external IDs from Jellyfin for SeriesId: {item.series_id}")

            # Route to appropriate service based on media type
            if item.media_type == MediaType.TV_SHOW:
                # A "continuing" show must only be preserved when it still exists
                # in Jellyfin (the user deleted some seasons). If the whole show is
                # gone, delete it from Sonarr regardless of its airing status.
                series_exists = None
                if self.jellyfin:
                    series_exists = self.jellyfin.item_exists_in_library(
                        item_name=item.title,
                        tvdb_id=item.tvdb_id,
                        imdb_id=item.imdb_id,
                        tmdb_id=item.tmdb_id,
                        item_type=item.media_type.value
                    )
                logger.debug(f"Routing to Sonarr for TV show: {item} (exists in Jellyfin: {series_exists})")
                return self.sonarr.unmonitor_item(item, series_exists_in_jellyfin=series_exists)
            elif item.media_type == MediaType.EPISODE:
                logger.debug(f"Routing to Sonarr for episode: {item}")
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

    def _reparse_with_jellyfin(self, webhook_data: dict) -> Optional[MediaItem]:
        """Rebuild a MediaItem from the Jellyfin API using the webhook's ItemId.

        This recovers the series/season/episode context that Jellyfin's template
        failed to render. Returns None when the item is already purged from
        Jellyfin (the common case for full deletions) or when no ID is present.
        """
        if not self.jellyfin:
            return None

        item_id = webhook_data.get('ItemId')
        if not item_id:
            logger.debug("No ItemId in webhook payload - cannot re-parse via Jellyfin")
            return None

        item_data = self.jellyfin.get_item(item_id)
        if not item_data:
            logger.debug(f"Item {item_id} is no longer present in Jellyfin - cannot re-parse")
            return None

        item = MediaParser.enrich_from_jellyfin_item(webhook_data, item_data)
        if item:
            logger.info(f"Recovered item from Jellyfin API: {item}")
        return item

    def test_connections(self) -> dict:
        """Test connections to all *arr services"""
        connections = {
            'sonarr': self.sonarr.test_connection(),
            'radarr': self.radarr.test_connection()
        }
        if self.jellyfin:
            connections['jellyfin'] = self.jellyfin.test_connection()
        return connections
