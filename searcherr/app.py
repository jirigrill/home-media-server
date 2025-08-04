"""
Searcherr - Automated missing media search service for Radarr and Sonarr
"""

import atexit
import logging
import threading
from datetime import datetime
from typing import Any

from flask import Flask, request

from config import Config
from scheduler import SearchScheduler
from services import RadarrService, SonarrService


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load configuration
    config = Config()

    # Initialize services
    radarr_service = RadarrService(config.radarr_url, config.radarr_api_key, config.search_delay_minutes)
    sonarr_service = SonarrService(config.sonarr_url, config.sonarr_api_key, config.search_delay_minutes)

    # Setup logging
    _setup_logging(config)

    # Register routes and error handlers
    _register_routes(app, config, radarr_service, sonarr_service)
    _register_error_handlers(app)

    # Start background scheduler if enabled
    if config.enable_scheduler:
        scheduler = SearchScheduler(
            interval_hours=config.scheduler_interval_hours,
            base_url=config.host,
            port=config.port,
            run_on_startup=config.scheduler_run_on_startup,
        )
        scheduler.start()

        # Ensure scheduler is stopped when app shuts down
        atexit.register(scheduler.stop)

        # Store scheduler in app config for potential access
        app.scheduler = scheduler

    return app


def _setup_logging(config: Config) -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(config.log_file), logging.StreamHandler()],
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting Searcherr application")


def _execute_background_search(
    service: str, config: Config, radarr_service: RadarrService, sonarr_service: SonarrService, logger
) -> None:
    """Execute search in background thread."""
    try:
        logger.info(f"Background search starting with service parameter: '{service}'")
        if service in ["radarr", "both"]:
            logger.info("Starting Radarr search...")
            result = radarr_service.search_stalled_missing_space_check(
                config.min_free_space_gb, "movies", config.stalled_download_hours
            )
            if "error" in result:
                logger.error(f"Radarr search failed: {result['message']}")
            else:
                logger.info(f"Radarr search completed: {result.get('count', 0)} items processed")

        if service in ["sonarr", "both"]:
            logger.info("Starting Sonarr search...")
            result = sonarr_service.search_stalled_missing_space_check(
                config.min_free_space_gb, "shows", config.stalled_download_hours
            )
            if "error" in result:
                logger.error(f"Sonarr search failed: {result['message']}")
            else:
                logger.info(f"Sonarr search completed: {result.get('count', 0)} items processed")

    except Exception as e:
        logger.error(f"Background search failed: {e}")


def _register_routes(
    app: Flask, config: Config, radarr_service: RadarrService, sonarr_service: SonarrService
) -> None:
    """Register application routes."""
    logger = logging.getLogger(__name__)

    @app.route("/")
    def index() -> dict[str, Any]:
        """Service information endpoint."""
        return {
            "service": "Searcherr",
            "version": "0.1.0",
            "description": "Automated missing media search service",
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
        }

    @app.route("/health")
    def health() -> dict[str, Any]:
        """Health check endpoint."""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {},
        }

        # Check Radarr connectivity
        radarr_connected = radarr_service.test_connection()
        health_status["services"]["radarr"] = {
            "status": "connected" if radarr_connected else "disconnected",
            "url": config.radarr_url,
        }

        # Check Sonarr connectivity
        sonarr_connected = sonarr_service.test_connection()
        health_status["services"]["sonarr"] = {
            "status": "connected" if sonarr_connected else "disconnected",
            "url": config.sonarr_url,
        }

        # Overall status
        if not radarr_connected or not sonarr_connected:
            health_status["status"] = "unhealthy"

        return health_status

    @app.route("/search", methods=["POST"])
    def search() -> dict[str, Any]:
        """Trigger manual search for missing media."""
        # Get service parameter (radarr, sonarr, or both)
        service = request.args.get("service", "both").lower()

        logger.info(f"Manual search triggered for service: {service}")

        # Start search in background thread
        threading.Thread(
            target=_execute_background_search,
            args=(service, config, radarr_service, sonarr_service, logger),
            daemon=True
        ).start()

        # Return immediate response
        return {
            "message": f"Search started in background for {service}",
            "service": service,
            "timestamp": datetime.utcnow().isoformat()
        }

    @app.route("/test", methods=["POST"])
    def test() -> dict[str, Any]:
        """Debug endpoint for testing."""
        data = request.get_json() or {}
        logger.info(f"Test endpoint called with data: {data}")

        return {
            "message": "Test endpoint",
            "received_data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }


def _register_error_handlers(app: Flask) -> None:
    """Register application error handlers."""
    logger = logging.getLogger(__name__)

    @app.errorhandler(404)
    def not_found(error) -> tuple[dict[str, str], int]:
        """Handle 404 errors."""
        return {"error": "Endpoint not found"}, 404

    @app.errorhandler(500)
    def internal_error(error) -> tuple[dict[str, str], int]:
        """Handle 500 errors."""
        logger.error(f"Internal server error: {error}")
        return {"error": "Internal server error"}, 500


def main():
    """Main entry point."""
    config = Config()
    app = create_app()

    app.run(host=config.host, port=config.port, debug=config.debug)


if __name__ == "__main__":
    main()
