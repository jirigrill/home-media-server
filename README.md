# Docker Media Server Stack

A comprehensive media server setup using Docker Compose with 9 services, featuring Jellyfin as the media server along with content acquisition, management, cleanup, and automation tools.

## Features

- **Jellyfin**: Media streaming server with hardware transcoding support
- **QBittorrent**: Torrent client with web interface
- **Prowlarr**: Indexer manager/proxy for coordinating searches
- **Sonarr**: TV shows automation and management
- **Radarr**: Movies automation and management
- **Bazarr**: Subtitles automation and management
- **Huntarr**: Automated missing content discovery and quality upgrade tool
- **Cleanuparr**: Automated cleanup tool for managing disk space and old downloads
- **Deleterr**: Custom webhook service that automatically unmonitors deleted content

## Prerequisites

- Docker and Docker Compose installed
- Sufficient storage space for media content
- Basic understanding of Docker and networking

## Installation

1. Clone this repository:
```bash
git clone git@github.com:jirigrill/home-media-server.git
cd home-media-server
```

2. Create an `.env` file from the example template:
```bash
cp .env.example .env
```
Then edit `.env` with your actual paths, ports, and API keys. See `.env.example` for all available configuration options including memory limits, service ports, and hardware acceleration settings.

3. Create the external network:
```bash
docker network create media_server
```

4. Start the stack:
```bash
docker-compose up -d
```

## Service Access

Default ports (configurable in `.env.example`):
- Jellyfin: 8096
- QBittorrent: 8080 (Web UI), 6881 (Torrenting)
- Prowlarr: 9696
- Sonarr: 8989
- Radarr: 7878
- Bazarr: 6767
- Huntarr: 9705
- Cleanuparr: 11011
- Deleterr: 5000

## Configuration

### Directory Structure

The stack expects the following directory structure (configurable in `.env.example`):
```
/path/to/
├── downloads/
│   └── torrent_downloads/
└── media/
    ├── movies/
    └── shows/
```

### Service Configuration

Each service requires initial configuration through their respective web interfaces:

1. **QBittorrent**
   - Configure default credentials
   - Set up download paths and connection settings

2. **Prowlarr**
   - Add and configure indexers
   - Set up connections to Sonarr and Radarr

3. **Sonarr/Radarr**
   - Configure download clients (QBittorrent)
   - Set up quality profiles
   - Connect to Prowlarr for indexers

4. **Bazarr**
   - Configure subtitle languages
   - Connect to Sonarr and Radarr
   - Set up subtitle providers

5. **Jellyfin**
   - Set up libraries pointing to /movies and /shows
   - Configure transcoding settings
   - Create user accounts

## Resource Management

- Memory limits are configurable through environment variables in the `.env` file (see `.env.example` for defaults)
- User/Group permissions are managed through PUID/PGID in the `.env` file

## Maintenance

### Backup

Important data to backup:
- Named volumes (service configurations)
- Media directories
- `.env` file

### Updates

Update container images:
```bash
docker-compose pull
docker-compose up -d
```

## Troubleshooting

1. **Permission Issues**
   - Verify PUID/PGID in `.env` match your user
   - Check directory permissions

2. **Network Issues**
   - Confirm media_server network exists
   - Check for port conflicts in `.env` (see `.env.example` for defaults)

3. **Resource Issues**
   - Monitor container memory usage
   - Adjust memory limits in `.env` (see `.env.example` for recommended values)

## Security Notes

- Change default credentials immediately
- Use secure passwords for all services
- Consider using a VPN
- Avoid exposing services directly to the internet
- Keep `.env` file secure and out of version control

## Contributing

Feel free to submit issues and enhancement requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
