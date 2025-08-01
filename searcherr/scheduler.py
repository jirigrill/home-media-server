"""
Background scheduler for periodic search operations
"""

import logging
import threading
import time

import requests


class SearchScheduler:
    """Background scheduler that periodically calls the search endpoint."""

    def __init__(self, interval_hours: int, base_url: str, port: int, run_on_startup: bool = True):
        """
        Initialize the scheduler.

        Args:
            interval_hours: Hours between search runs
            base_url: Base URL for the Flask app
            port: Port number for the Flask app
            run_on_startup: Whether to run first search immediately on startup
        """
        self.interval_hours = interval_hours
        self.interval_seconds = interval_hours * 3600
        # Use localhost for internal calls instead of 0.0.0.0
        internal_host = "127.0.0.1" if base_url == "0.0.0.0" else base_url  # noqa: S104
        self.search_url = f"http://{internal_host}:{port}/search"
        self.run_on_startup = run_on_startup
        self.logger = logging.getLogger(self.__class__.__name__)
        self.running = False
        self.thread = None

    def start(self) -> None:
        """Start the background scheduler."""
        if self.running:
            self.logger.warning("Scheduler is already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        self.logger.info(f"Started search scheduler (interval: {self.interval_hours}h)")

    def stop(self) -> None:
        """Stop the background scheduler."""
        if not self.running:
            return

        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.logger.info("Stopped search scheduler")

    def _run_scheduler(self) -> None:
        """Main scheduler loop that runs in background thread."""
        if self.run_on_startup:
            self.logger.info("Waiting for Flask app to be ready...")
            time.sleep(10)  # Give Flask time to start accepting connections
            self.logger.info("Running initial search on startup...")
            self._trigger_search()
            self.logger.info(f"Next scheduled search will run in {self.interval_hours} hours")
        else:
            self.logger.info(f"First scheduled search will run in {self.interval_hours} hours")

        while self.running:
            # Wait for the interval (check every 60 seconds if we should stop)
            for _ in range(self.interval_seconds // 60):
                if not self.running:
                    return
                time.sleep(60)

            # Handle remaining seconds
            remaining_seconds = self.interval_seconds % 60
            if remaining_seconds > 0 and self.running:
                time.sleep(remaining_seconds)

            if not self.running:
                return

            # Trigger search
            self._trigger_search()

    def _trigger_search(self) -> None:
        """Trigger a search by calling the /search endpoint."""
        try:
            self.logger.info("Triggering scheduled search...")
            # Short timeout just to verify the search started successfully
            response = requests.post(self.search_url, timeout=5)

            if response.status_code == 200:
                result = response.json()
                count = result.get("count", 0)
                stalled_info = result.get("stalled_downloads", {})
                blocklisted = stalled_info.get("blocklisted_count", 0)

                self.logger.info(
                    f"Scheduled search initiated: {count} missing items to search, "
                    f"{blocklisted} stalled downloads blocklisted. Search will continue in background."
                )
            else:
                self.logger.error(
                    f"Failed to start scheduled search with status {response.status_code}: {response.text}"
                )

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to trigger scheduled search: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during scheduled search: {e}")
