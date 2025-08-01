"""
Base service class for API interactions
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

import requests


class BaseService(ABC):
    """Abstract base class for API services."""

    def __init__(self, base_url: str, api_key: str):
        """
        Initialize the service.

        Args:
            base_url: The base URL for the API
            api_key: The API key for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.logger = logging.getLogger(self.__class__.__name__)
        self.session = requests.Session()
        self.session.headers.update({"X-Api-Key": self.api_key, "Content-Type": "application/json"})

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without leading slash)
            data: JSON data to send in request body
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            requests.RequestException: If the request fails
        """
        url = f"{self.base_url}/api/v3/{endpoint}"

        self.logger.debug(f"Making {method} request to {url}")

        try:
            response = self.session.request(method=method, url=url, json=data, params=params, timeout=30)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {e}")
            raise

    def test_connection(self) -> bool:
        """
        Test the connection to the API.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            self._make_request("GET", "system/status")
            self.logger.info("Connection test successful")
            return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False

    @abstractmethod
    def get_missing_items(self) -> list[dict[str, Any]]:
        """
        Get list of missing media items.

        Returns:
            List of missing items
        """
        pass

    @abstractmethod
    def search_missing(self, item_id: int) -> bool:
        """
        Trigger search for a specific missing item.

        Args:
            item_id: ID of the item to search for

        Returns:
            True if search was triggered successfully
        """
        pass

    @abstractmethod
    def search_all_missing(self, missing_items: list[dict[str, Any]] | None = None) -> bool:
        """
        Trigger search for all missing items.

        Args:
            missing_items: Optional pre-fetched missing items list to avoid duplicate API call

        Returns:
            True if search was triggered successfully
        """
        pass

    def get_system_status(self) -> dict[str, Any]:
        """
        Get system status information.

        Returns:
            System status information
        """
        try:
            return self._make_request("GET", "system/status")
        except Exception as e:
            self.logger.error(f"Failed to get system status: {e}")
            return {}

    def get_disk_space(self) -> list[dict[str, Any]]:
        """
        Get disk space information.

        Returns:
            List of disk space information
        """
        try:
            response = self._make_request("GET", "diskspace")
            return response
        except Exception as e:
            self.logger.error(f"Failed to get disk space: {e}")
            return []

    def check_disk_space_for_path(self, path: str, min_free_gb: int) -> dict[str, Any]:
        """Check if a specific path has sufficient disk space."""
        try:
            disk_space_info = self.get_disk_space()
            if not disk_space_info:
                return {"error": "No disk space information available", "path": path}

            # Find exact path match
            matching_disk = next((disk for disk in disk_space_info if disk.get("path") == path), None)

            if not matching_disk:
                return {
                    "error": f"Path {path} not found in disk space info",
                    "path": path,
                }

            free_gb = round(matching_disk.get("freeSpace", 0) / (1024**3), 2)
            sufficient = free_gb >= min_free_gb

            return {
                "path": path,
                "free_gb": free_gb,
                "min_required_gb": min_free_gb,
                "sufficient_space": sufficient,
            }

        except Exception as e:
            return {"error": f"Failed to check disk space: {str(e)}", "path": path}

    def search_stalled_missing_space_check(
        self, min_free_gb: int, media_type: str, stalled_hours: int
    ) -> dict[str, Any]:
        """
        Check for stalled downloads, blocklist them, and search for missing items if there's sufficient disk space.

        Args:
            min_free_gb: Minimum required free space in GB
            media_type: Type of media ('movies' or 'shows')
            stalled_hours: Hours after which a download is considered stalled

        Returns:
            Dictionary with search results and status
        """
        # Check for stalled downloads first
        self.logger.info("Checking for stalled downloads...")
        stalled_check_results = self.check_and_blocklist_search_stalled_downloads(stalled_hours)

        # Use standard media path
        path = f"/{media_type}"

        # Check disk space
        space_check = self.check_disk_space_for_path(path, min_free_gb)

        if space_check.get("error"):
            return {
                "error": "Disk space check failed",
                "message": space_check["error"],
                "path": path,
                "timestamp": datetime.utcnow().isoformat(),
            }

        if not space_check["sufficient_space"]:
            return {
                "error": "Insufficient disk space",
                "message": f"Path has {space_check['free_gb']}GB free, need {min_free_gb}GB minimum",
                "path": path,
                "free_gb": space_check["free_gb"],
                "required_gb": min_free_gb,
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Space is sufficient, proceed with search
        try:
            missing_items = self.get_missing_items()

            if not missing_items:
                return {
                    "message": "No missing items found",
                    "count": 0,
                    "path": path,
                    "free_gb": space_check["free_gb"],
                    "timestamp": datetime.utcnow().isoformat(),
                }

            # Trigger search for all missing items (pass the items to avoid duplicate API call)
            search_success = self.search_all_missing(missing_items)

            return {
                "message": "Search triggered successfully" if search_success else "Search failed",
                "count": len(missing_items),
                "missing_items": [item.get("title", "Unknown") for item in missing_items[:10]],  # Show first 10
                "success": search_success,
                "path": path,
                "free_gb": space_check["free_gb"],
                "stalled_downloads": stalled_check_results,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return {
                "error": "Search failed",
                "message": str(e),
                "path": path,
                "timestamp": datetime.utcnow().isoformat(),
            }

    def check_and_blocklist_search_stalled_downloads(self, stalled_hours: int) -> dict[str, Any]:
        """
        Check for downloads running longer than specified hours and blocklist them.

        Args:
            stalled_hours: Hours after which a download is considered stalled

        Returns:
            Dictionary with check results and statistics
        """
        try:
            # Get current queue
            queue_response = self._make_request("GET", "queue")
            queue_items = queue_response.get("records", [])

            result = {
                "queue_items_total": len(queue_items),
                "stalled_items": [],
                "blocklisted_count": 0,
                "researched_count": 0,
                "active_downloads": [],
            }

            if not queue_items:
                self.logger.info("No items in download queue")
                return result

            stalled_threshold = datetime.utcnow() - timedelta(hours=stalled_hours)

            for item in queue_items:
                try:
                    item_title = item.get("title", "Unknown")
                    item_id = item.get("movieId") or item.get("seriesId")

                    # Parse the added timestamp
                    added_str = item.get("added", "")
                    if not added_str:
                        result["active_downloads"].append({"title": item_title, "status": "unknown_time"})
                        continue

                    # Handle different timestamp formats
                    added_str = added_str.replace("Z", "+00:00")
                    added_time = datetime.fromisoformat(added_str.replace("+00:00", "")).replace(tzinfo=None)
                    hours_running = (datetime.utcnow() - added_time).total_seconds() / 3600

                    # Check if download is stalled
                    if added_time < stalled_threshold:
                        download_id = item.get("downloadId")
                        if not download_id:
                            continue

                        # Add to stalled items list
                        stalled_item = {
                            "title": item_title,
                            "item_id": item_id,
                            "hours_running": round(hours_running, 1),
                            "download_id": download_id,
                        }
                        result["stalled_items"].append(stalled_item)

                        # Blocklist the download
                        blocklist_data = {
                            "downloadId": download_id,
                            "reason": f"Stalled download (>{stalled_hours} hours)",
                        }
                        self._make_request("POST", "blocklist", data=blocklist_data)
                        result["blocklisted_count"] += 1

                        # Trigger new search for the item
                        if item_id:
                            self.search_missing(item_id)
                            result["researched_count"] += 1

                        self.logger.info(
                            f"Blocklisted stalled download: {item_title} "
                            f"(ID: {item_id}, running for {hours_running:.1f}h)"
                        )
                    else:
                        # Add to active downloads
                        result["active_downloads"].append(
                            {
                                "title": item_title,
                                "hours_running": round(hours_running, 1),
                            }
                        )

                except Exception as e:
                    self.logger.error(f"Error processing queue item: {e}")
                    continue

            if result["blocklisted_count"] > 0:
                self.logger.info(
                    f"Blocklisted {result['blocklisted_count']} stalled downloads, "
                    f"triggered {result['researched_count']} new searches"
                )
            else:
                self.logger.info("No stalled downloads found")

            return result

        except Exception as e:
            self.logger.error(f"Failed to check stalled downloads: {e}")
            return {
                "error": f"Failed to check stalled downloads: {str(e)}",
                "queue_items_total": 0,
                "stalled_items": [],
                "blocklisted_count": 0,
                "researched_count": 0,
                "active_downloads": [],
            }
