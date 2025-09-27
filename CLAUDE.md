# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Structure

This is a Docker-based home media server stack with a custom Python service called Deleterr. The main components are:

- **Docker Compose Stack**: Orchestrates the complete media server ecosystem with 8 services
- **Core Media Services**:
  - **Jellyfin**: Media streaming server with hardware transcoding support
  - **qBittorrent**: Torrent client with web interface for content acquisition
- **Content Management (*arr suite)**:
  - **Prowlarr**: Indexer manager/proxy that coordinates search across torrent sites
  - **Sonarr**: TV show automation, monitoring, and library management
  - **Radarr**: Movie automation, monitoring, and library management
  - **Bazarr**: Subtitle automation and management for movies and TV shows
- **Maintenance & Cleanup**:
  - **Cleanuparr**: Automated cleanup tool for managing disk space and old downloads
  - **Deleterr**: Custom Flask application that receives webhooks from Jellyfin and automatically unmonitors deleted content in Sonarr/Radarr

## Common Commands

### Docker Operations
```bash
# Start the entire media server stack
docker-compose up -d

# Stop the stack
docker-compose down

# View logs for specific service
docker-compose logs -f deleterr

# Rebuild and restart a specific service
docker-compose up -d --build deleterr

# Pull latest images and restart
docker-compose pull && docker-compose up -d
```

### Deleterr Development
```bash
# Enter the deleterr directory for development
cd deleterr

# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=. --cov-report=html

# Format code
black .

# Lint code
flake8

# Type checking
mypy .

# Run the application locally (requires environment variables)
python app.py
```

### Network Setup
```bash
# Create the required external network (run once)
docker network create media_server
```

## Configuration

### Environment Variables
Create a `.env` file with required configuration:

**Service Ports**:
- `JELLYFIN_PORT` (default: 8096)
- `QBITTORRENT_UI_PORT` (default: 8080) and `QBITTORRENT_TORRENT_PORT` (default: 6881)
- `PROWLARR_PORT` (default: 9696)
- `SONARR_PORT` (default: 8989)
- `RADARR_PORT` (default: 7878)
- `BAZARR_PORT` (default: 6767)
- `CLEANUPARR_PORT` (default: 11011)
- `DELETERR_PORT` (default: 5000)

**API Keys** (required for service integration):
- `SONARR_API_KEY` and `RADARR_API_KEY` (required for Deleterr)

**System Configuration**:
- Memory limits for each service (`*_MEM_LIMIT`)
- File paths (`DOWNLOADS_PATH`, `SHOWS_PATH`, `MOVIES_PATH`)
- User permissions (`PUID`, `PGID`)
- Timezone (`TZ`)
- Hardware acceleration (`RENDER_GROUP`, `RENDER_DEVICE`)

### Service Dependencies
The stack has the following dependency hierarchy:
- **Prowlarr & qBittorrent**: Foundation services that others depend on
- **Sonarr & Radarr**: Depend on Prowlarr and qBittorrent for indexers and downloads
- **Bazarr**: Depends on Sonarr and Radarr for media library integration
- **Cleanuparr**: Depends on Sonarr, Radarr, and qBittorrent for cleanup coordination
- **Deleterr**: Depends on Sonarr and Radarr for API connectivity validation
- **Jellyfin**: Independent media server that serves the organized content

## Deleterr Architecture

### Key Components
- **Flask App** (`app.py`): Main application with webhook endpoints
- **Configuration** (`config.py`): Environment-based configuration with validation
- **Services Layer**: 
  - `base_service.py`: Abstract base for API services
  - `sonarr_service.py` / `radarr_service.py`: Specific API implementations
  - `webhook_processor.py`: Processes Jellyfin webhooks and coordinates unmonitoring
- **Models** (`models/media_item.py`): Data structures for media items

### API Endpoints
- `POST /delete`: Main webhook endpoint for Jellyfin item removal events
- `GET /health`: Health check with service connectivity status
- `POST /test`: Debug endpoint for webhook testing
- `GET /`: Service information

### Webhook Flow
1. Jellyfin sends ItemRemoved webhook to `/delete`
2. WebhookProcessor parses the payload
3. Determines if content is TV show (Sonarr) or movie (Radarr)
4. Calls appropriate service to unmonitor the content
5. Returns success/failure response

## Development Notes

### Python Environment
- Uses Python 3.11+ with type hints
- Flask for web framework, requests for HTTP client
- Structured with dataclasses and proper separation of concerns

### Code Quality Tools
- Black for formatting (line length 88)
- MyPy for type checking with strict settings
- Pytest for testing with coverage reporting
- Flake8 for linting

### Docker Development
The Deleterr service builds from local Dockerfile. For development changes, rebuild the container with `docker-compose up -d --build deleterr`.