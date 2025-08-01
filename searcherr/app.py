"""
Searcherr - Automated missing media search service for Radarr and Sonarr
"""

import logging
from datetime import datetime
from typing import Any

from flask import Flask, request

from config import Config
from services import RadarrService


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load configuration
    config = Config()

    # Initialize services
    radarr_service = RadarrService(config.radarr_url, config.radarr_api_key, config.search_delay_minutes)

    # Setup logging
    _setup_logging(config)

    # Register routes and error handlers
    _register_routes(app, config, radarr_service)
    _register_error_handlers(app)

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


def _register_routes(app: Flask, config: Config, radarr_service: RadarrService) -> None:
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

        if config.sonarr_url:
            health_status["services"]["sonarr"] = {
                "status": "not_implemented",
                "url": config.sonarr_url,
            }

        # Overall status
        if not radarr_connected:
            health_status["status"] = "unhealthy"

        return health_status

    @app.route("/search", methods=["POST"])
    def search() -> dict[str, Any]:
        """Trigger manual search for missing media."""
        logger.info("Manual search triggered")

        # Use the new BaseService method for movies
        result = radarr_service.search_stalled_missing_space_check(
            config.min_free_space_gb, "movies", config.stalled_download_hours
        )

        # Return appropriate HTTP status code based on result
        if "error" in result:
            if "Insufficient disk space" in result["error"]:
                return result, 400
            else:
                return result, 500

        return result

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
