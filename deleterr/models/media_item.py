"""
Media item data models for Deleterr
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class MediaType(Enum):
    """Media type enumeration"""
    EPISODE = "episode"
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    SEASON = "season"


@dataclass
class MediaItem:
    """Represents a media item (episode or movie)"""
    media_type: MediaType
    title: str
    season: Optional[int] = None
    episode: Optional[int] = None
    year: Optional[int] = None
    # External provider IDs for more reliable matching
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    # Jellyfin IDs
    item_id: Optional[str] = None  # Jellyfin item ID (for existence check)
    series_id: Optional[str] = None  # Jellyfin series ID (for episodes/seasons - used to query series-level external IDs)
    
    def __post_init__(self):
        """Validate media item after initialization"""
        if self.media_type == MediaType.EPISODE:
            if self.season is None or self.episode is None:
                raise ValueError("Episode items require season and episode numbers")
        elif self.media_type == MediaType.SEASON:
            if self.season is None:
                raise ValueError("Season items require season number")
            if self.episode is not None:
                raise ValueError("Season items should not have episode numbers")
        elif self.media_type == MediaType.TV_SHOW:
            if self.season is not None or self.episode is not None:
                raise ValueError("TV show items should not have season or episode numbers")
        elif self.media_type == MediaType.MOVIE:
            if self.season is not None or self.episode is not None:
                raise ValueError("Movie items should not have season or episode numbers")
    
    @property
    def series_name(self) -> str:
        """Get series name for episodes"""
        if self.media_type != MediaType.EPISODE:
            raise ValueError("series_name only available for episodes")
        return self.title

    @property
    def tv_show_title(self) -> str:
        """Get TV show title"""
        if self.media_type != MediaType.TV_SHOW:
            raise ValueError("tv_show_title only available for TV shows")
        return self.title

    @property
    def movie_title(self) -> str:
        """Get movie title for movies"""
        if self.media_type != MediaType.MOVIE:
            raise ValueError("movie_title only available for movies")
        return self.title
    
    def __str__(self) -> str:
        """String representation of media item"""
        if self.media_type == MediaType.EPISODE:
            return f"{self.title} S{self.season:02d}E{self.episode:02d}"
        elif self.media_type == MediaType.SEASON:
            return f"{self.title} Season {self.season}"
        elif self.media_type == MediaType.TV_SHOW:
            return f"{self.title} (TV Show)"
        else:  # MOVIE
            year_str = f" ({self.year})" if self.year else ""
            return f"{self.title}{year_str}"