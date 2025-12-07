"""
Media parsers for extracting media information from various sources
"""

import html
import logging
import re
from typing import Optional

from models.media_item import MediaItem, MediaType

logger = logging.getLogger(__name__)


class MediaParser:
    """Utility class for parsing media information from various sources"""
    
    @staticmethod
    def parse_webhook_data(webhook_data: dict) -> Optional[MediaItem]:
        """Parse Jellyfin webhook data into MediaItem"""
        try:
            item_type = webhook_data.get('ItemType', '').lower()
            item_name = webhook_data.get('Name', '')

            if not item_name:
                logger.warning("No item name in webhook data")
                return None

            if item_type == 'episode':
                return MediaParser._parse_episode_webhook(webhook_data)
            elif item_type == 'movie':
                return MediaParser._parse_movie_webhook(webhook_data)
            elif item_type == 'series':
                return MediaParser._parse_tv_show_webhook(webhook_data)
            elif item_type == 'season':
                return MediaParser._parse_season_webhook(webhook_data)
            else:
                logger.warning(f"Unsupported item type: {item_type}")
                return None

        except Exception as e:
            logger.error(f"Error parsing webhook data: {e}")
            return None
    
    @staticmethod
    def _parse_episode_webhook(webhook_data: dict) -> Optional[MediaItem]:
        """Parse episode webhook data"""
        try:
            # Try to get structured data first
            series_name = webhook_data.get('SeriesName', '')
            season_number = webhook_data.get('SeasonNumber')
            episode_number = webhook_data.get('EpisodeNumber')

            # Extract external provider IDs (support both Jellyfin webhook format and API format)
            # NOTE: These are episode-level IDs, not series-level IDs
            imdb_id = webhook_data.get('Provider_imdb') or webhook_data.get('ImdbId') or webhook_data.get('imdbId')
            tvdb_id = webhook_data.get('Provider_tvdb') or webhook_data.get('TvdbId') or webhook_data.get('tvdbId')
            tmdb_id = webhook_data.get('Provider_tmdb') or webhook_data.get('TmdbId') or webhook_data.get('tmdbId')

            # Extract Jellyfin IDs
            item_id = webhook_data.get('ItemId')
            series_id = webhook_data.get('SeriesId')

            logger.debug(f"Parsing episode webhook - Series: {series_name}, Season: {season_number}, Episode: {episode_number}, ItemId: {item_id}, SeriesId: {series_id}, TVDB: {tvdb_id}, IMDB: {imdb_id}, TMDB: {tmdb_id}")

            # If structured data is available, use it
            # Check for empty strings in addition to None
            if series_name and season_number and episode_number:
                # Decode HTML entities in series name
                series_name = html.unescape(series_name)
                return MediaItem(
                    media_type=MediaType.EPISODE,
                    title=series_name,
                    season=int(season_number),
                    episode=int(episode_number),
                    imdb_id=imdb_id,
                    tvdb_id=tvdb_id,
                    tmdb_id=tmdb_id,
                    item_id=item_id,
                    series_id=series_id
                )

            # Fallback to parsing from item name
            item_name = webhook_data.get('Name', '')
            if item_name:
                return MediaParser._parse_episode_from_name(item_name)

            logger.warning("Could not parse episode information from webhook")
            return None

        except Exception as e:
            logger.error(f"Error parsing episode webhook: {e}")
            return None
    
    @staticmethod
    def _parse_movie_webhook(webhook_data: dict) -> Optional[MediaItem]:
        """Parse movie webhook data"""
        try:
            movie_title = webhook_data.get('Name', '')
            year = webhook_data.get('Year')

            # Extract external provider IDs (support both Jellyfin webhook format and API format)
            imdb_id = webhook_data.get('Provider_imdb') or webhook_data.get('ImdbId') or webhook_data.get('imdbId')
            tvdb_id = webhook_data.get('Provider_tvdb') or webhook_data.get('TvdbId') or webhook_data.get('tvdbId')
            tmdb_id = webhook_data.get('Provider_tmdb') or webhook_data.get('TmdbId') or webhook_data.get('tmdbId')

            # Extract Jellyfin item ID
            item_id = webhook_data.get('ItemId')

            if not movie_title:
                logger.warning("No movie title in webhook data")
                return None

            # Decode HTML entities (e.g., "The Accountant&#178;" -> "The Accountant²")
            movie_title = html.unescape(movie_title)

            # Convert year to int if it's a string
            parsed_year = None
            if year:
                try:
                    parsed_year = int(year)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid year format: {year}")

            logger.debug(f"Parsing movie webhook - Title: {movie_title}, Year: {parsed_year}, ItemId: {item_id}, IMDB: {imdb_id}, TMDB: {tmdb_id}")

            return MediaItem(
                media_type=MediaType.MOVIE,
                title=movie_title,
                year=parsed_year,
                imdb_id=imdb_id,
                tvdb_id=tvdb_id,
                tmdb_id=tmdb_id,
                item_id=item_id
            )

        except Exception as e:
            logger.error(f"Error parsing movie webhook: {e}")
            return None

    @staticmethod
    def _parse_tv_show_webhook(webhook_data: dict) -> Optional[MediaItem]:
        """Parse TV show (series) webhook data"""
        try:
            tv_show_title = webhook_data.get('Name', '')

            # Extract external provider IDs
            imdb_id = webhook_data.get('Provider_imdb') or webhook_data.get('ImdbId') or webhook_data.get('imdbId')
            tvdb_id = webhook_data.get('Provider_tvdb') or webhook_data.get('TvdbId') or webhook_data.get('tvdbId')
            tmdb_id = webhook_data.get('Provider_tmdb') or webhook_data.get('TmdbId') or webhook_data.get('tmdbId')

            # Extract Jellyfin item ID
            item_id = webhook_data.get('ItemId')

            if not tv_show_title:
                logger.warning("No TV show title in webhook data")
                return None

            # Decode HTML entities
            tv_show_title = html.unescape(tv_show_title)

            logger.debug(f"Parsing TV show webhook - Title: {tv_show_title}, ItemId: {item_id}, TVDB: {tvdb_id}, IMDB: {imdb_id}, TMDB: {tmdb_id}")

            return MediaItem(
                media_type=MediaType.TV_SHOW,
                title=tv_show_title,
                imdb_id=imdb_id,
                tvdb_id=tvdb_id,
                tmdb_id=tmdb_id,
                item_id=item_id
            )

        except Exception as e:
            logger.error(f"Error parsing TV show webhook: {e}")
            return None

    @staticmethod
    def _parse_season_webhook(webhook_data: dict) -> Optional[MediaItem]:
        """Parse season webhook data"""
        try:
            series_name = webhook_data.get('SeriesName', '')
            season_number = webhook_data.get('SeasonNumber')

            # Extract external provider IDs (these are season-level, not series-level)
            imdb_id = webhook_data.get('Provider_imdb') or webhook_data.get('ImdbId') or webhook_data.get('imdbId')
            tvdb_id = webhook_data.get('Provider_tvdb') or webhook_data.get('TvdbId') or webhook_data.get('tvdbId')
            tmdb_id = webhook_data.get('Provider_tmdb') or webhook_data.get('TmdbId') or webhook_data.get('tmdbId')

            # Extract Jellyfin IDs
            item_id = webhook_data.get('ItemId')
            series_id = webhook_data.get('SeriesId')

            # If SeriesName is empty, try to infer from Name field
            if not series_name:
                name_field = webhook_data.get('Name', '')
                # Remove "Season X" pattern to try to extract series name
                series_name = re.sub(r'\s*Season\s+\d+\s*', '', name_field, flags=re.IGNORECASE).strip()

            if not series_name or not season_number:
                logger.warning(f"Missing series name or season number in season webhook")
                return None

            # Decode HTML entities
            series_name = html.unescape(series_name)

            logger.debug(f"Parsing season webhook - Series: {series_name}, Season: {season_number}, ItemId: {item_id}, SeriesId: {series_id}, TVDB: {tvdb_id}, IMDB: {imdb_id}, TMDB: {tmdb_id}")

            return MediaItem(
                media_type=MediaType.SEASON,
                title=series_name,
                season=int(season_number),
                imdb_id=imdb_id,
                tvdb_id=tvdb_id,
                tmdb_id=tmdb_id,
                item_id=item_id,
                series_id=series_id
            )

        except Exception as e:
            logger.error(f"Error parsing season webhook: {e}")
            return None

    @staticmethod
    def _parse_episode_from_name(item_name: str) -> Optional[MediaItem]:
        """Parse episode information from item name using regex patterns"""
        # Decode HTML entities first
        item_name = html.unescape(item_name)

        # Common episode naming patterns
        patterns = [
            r'^(.+?)\s+S(\d+)E(\d+)',          # "Series Name S01E01"
            r'^(.+?)\s+-\s+S(\d+)E(\d+)',      # "Series Name - S01E01"
            r'^(.+?)\s+(\d+)x(\d+)',           # "Series Name 1x01"
            r'^(.+?)\s+Season\s+(\d+)\s+Episode\s+(\d+)',  # "Series Name Season 1 Episode 1"
        ]

        for pattern in patterns:
            match = re.match(pattern, item_name, re.IGNORECASE)
            if match:
                series_name = match.group(1).strip()
                season_num = int(match.group(2))
                episode_num = int(match.group(3))

                logger.debug(f"Parsed episode: {series_name} S{season_num:02d}E{episode_num:02d}")

                return MediaItem(
                    media_type=MediaType.EPISODE,
                    title=series_name,
                    season=season_num,
                    episode=episode_num
                )

        logger.warning(f"Could not parse episode info from: {item_name}")
        return None