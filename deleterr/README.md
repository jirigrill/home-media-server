# Deleterr

Jellyfin webhook receiver to automatically unmonitor deleted content in Sonarr/Radarr.

## Features

- Receives webhooks from Jellyfin when content is deleted
- Automatically unmonitors episodes in Sonarr
- Automatically unmonitors movies in Radarr
- Clean, modular architecture with proper separation of concerns
- Health check and test endpoints

## Endpoints

- `POST /delete` - Main webhook endpoint for Jellyfin
- `GET /health` - Health check endpoint
- `POST /test` - Test webhook endpoint for debugging

## Configuration

Configure via environment variables:

- `SONARR_URL` - Sonarr URL (default: http://sonarr:8989)
- `RADARR_URL` - Radarr URL (default: http://radarr:7878)
- `SONARR_API_KEY` - Sonarr API key (required)
- `RADARR_API_KEY` - Radarr API key (required)
- `DELETERR_PORT` - Service port (default: 5000)
- `LOG_LEVEL` - Logging level (default: INFO)

## Usage

1. Configure Jellyfin webhook to point to `http://deleterr:5000/delete`
2. Enable "Item Deleted" event in Jellyfin webhook settings
3. When content is deleted from Jellyfin, it will be automatically unmonitored in Sonarr/Radarr