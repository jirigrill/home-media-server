# Searcherr

Missing media search service for Radarr and Sonarr with intelligent download management.

## Overview

Searcherr is a Python service that searches for missing media in your Radarr and Sonarr libraries. It monitors disk space, detects stalled downloads, and performs controlled searches to ensure your media collection stays complete while respecting storage limits and maintaining download queue health.

## Features

- **Stalled Download Detection**: Automatically detects and blocklists downloads running longer than configured time
- **Intelligent Search Strategy**: Searches missing items one-by-one with 5-minute delays to avoid overwhelming indexers
- **Disk Space Management**: Respects minimum free space requirements before searching
- **Download Queue Monitoring**: Provides detailed information about active and stalled downloads
- **Multi-Service Support**: Works with Radarr (currently) and Sonarr (planned)
- **Flask Web Interface**: Simple web endpoints for health checks and manual operations

## Requirements

- Python 3.11+
- Radarr instance with API access
- Access to media library paths for disk space monitoring

## Installation

### Using Make (Recommended)

```bash
# Clone or navigate to the searcherr directory
cd searcherr

# Install development dependencies
make dev-install

# Run the application
make run
```

### Using UV directly

```bash
# Install production dependencies
uv sync --no-dev

# Install development dependencies
uv sync --extra dev

# Run the application
uv run python app.py
```

## Configuration

Copy `.env.example` to `.env` and configure your settings:

```bash
cp .env.example .env
```

### Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RADARR_URL` | *required* | Radarr base URL (e.g., `http://radarr:7878`) |
| `RADARR_API_KEY` | *required* | Radarr API key |
| `MIN_FREE_SPACE_GB` | `20` | Minimum free space in GB before searching |
| `STALLED_DOWNLOAD_HOURS` | `4` | Hours before considering a download stalled |
| `SEARCH_DELAY_MINUTES` | `5` | Minutes to wait between individual searches |
| `SEARCH_INTERVAL_HOURS` | `6` | Hours between search runs (for future scheduling) |
| `HOST` | `0.0.0.0` | Flask host (use 0.0.0.0 for containers) |
| `PORT` | `5001` | Flask port |
| `LOG_LEVEL` | `INFO` | Logging level |

Then edit `.env` with your specific configuration values.

## API Endpoints

### `GET /`
Service information endpoint.

**Response:**
```json
{
  "service": "Searcherr",
  "version": "0.1.0",
  "description": "Automated missing media search service",
  "status": "running",
  "timestamp": "2025-08-01T09:34:03.696958"
}
```

### `GET /health`
Health check with service connectivity status.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-08-01T09:34:03.696958",
  "services": {
    "radarr": {
      "status": "connected",
      "url": "http://radarr:7878"
    }
  }
}
```

### `POST /search`
Trigger manual search for missing media. Checks for stalled downloads, validates disk space, and searches for missing items.

**Response:**
```json
{
  "count": 18,
  "missing_items": ["Movie 1", "Movie 2", "..."],
  "path": "/movies",
  "free_gb": 33.38,
  "stalled_downloads": {
    "queue_items_total": 3,
    "stalled_items": [
      {
        "title": "Stalled Movie",
        "item_id": 123,
        "hours_running": 6.5,
        "download_id": "abc123"
      }
    ],
    "blocklisted_count": 1,
    "researched_count": 1,
    "active_downloads": [
      {
        "title": "Active Download",
        "hours_running": 2.3
      }
    ]
  },
  "timestamp": "2025-08-01T09:34:03.696958"
}
```

### `POST /test`
Debug endpoint for testing webhook payloads and service functionality.

## Development

### Available Commands

```bash
# See all available commands
make help

# Code quality
make format      # Format code with ruff
make lint        # Lint code with ruff
make lint-fix    # Auto-fix linting issues
make typecheck   # Type checking with mypy

# Testing
make test        # Run tests
make test-cov    # Run tests with coverage report

# Maintenance
make clean       # Clean build artifacts and cache
```

### Project Structure

- `config.py` - Configuration management using Pydantic
- `services/` - API service implementations for Radarr/Sonarr
- `test_config.py` - Configuration testing utility

## License

MIT License