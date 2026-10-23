# Docker Media Server Stack

A comprehensive media server setup using Docker Compose, featuring Jellyfin as the media server along with content acquisition, management, cleanup, and automation tools.

## Features

### Media Streaming
- **Jellyfin**: Media streaming server with hardware transcoding support

### Content Acquisition
- **QBittorrent**: Torrent client with web interface
- **Prowlarr**: Indexer manager/proxy for coordinating searches across torrent sites
- **FlareSolverr**: Proxy server to bypass Cloudflare and DDoS-GUARD protection on indexers
- **AudioBookBay**: Audiobook tracker with no working Prowlarr definition, exposed through the custom `abb-torznab` bridge (see below)

### Content Management (*arr Suite)
- **Sonarr**: TV shows automation, monitoring, and library management
  - Includes custom ffmpeg installation for sample file detection
- **Radarr**: Movies automation, monitoring, and library management
  - Includes custom ffmpeg installation for fake release detection
- **Bazarr**: Subtitles automation and management

### Automation & Maintenance
- **Houndarr**: Polite missing/cutoff search scheduler for Sonarr/Radarr
- **Cleanuparr**: Automated cleanup tool for managing disk space and stuck downloads
  - **QueueCleaner**: Removes stalled/failed downloads from Sonarr/Radarr queue
  - **DownloadCleaner**: Manages orphaned torrents in qBittorrent
- **Deleterr**: Custom webhook service that automatically deletes content from Sonarr/Radarr when removed from Jellyfin

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

Default ports (configurable in `.env`):
- Jellyfin: 8096
- QBittorrent: 8080 (Web UI), 6881 (Torrenting)
- FlareSolverr: 8191
- Prowlarr: 9696
- Sonarr: 8989
- Radarr: 7878
- Bazarr: 6767
- Houndarr: 8877
- Cleanuparr: 11011
- Deleterr: 5000
- abb-torznab: 8095 (bound to 127.0.0.1, Torznab API for Prowlarr)

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
   - Configure categories (e.g., `sonarr`, `radarr`, `tv-sonarr`)

2. **FlareSolverr**
   - No configuration needed - automatically used by Prowlarr
   - Provides Cloudflare bypass for protected indexers

3. **Prowlarr**
   - Add and configure indexers
   - Set up connections to Sonarr and Radarr
   - Configure FlareSolverr proxy for protected indexers (URL: http://flaresolverr:8191)

4. **Sonarr/Radarr**
   - Configure download clients (QBittorrent)
   - Set up quality profiles
   - Connect to Prowlarr for indexers
   - **Note**: Both Sonarr and Radarr automatically install ffmpeg on startup for sample/fake file detection

5. **Bazarr**
   - Configure subtitle languages
   - Connect to Sonarr and Radarr
   - Set up subtitle providers

6. **Cleanuparr**
   - Configure QueueCleaner settings (strike limits, cleanup rules)
   - Configure DownloadCleaner to monitor qBittorrent categories
   - Set up notifications (optional)

7. **Deleterr**
   - Configure Jellyfin webhook: Point to `http://deleterr:5000/delete`
   - Event: ItemRemoved
   - No other configuration needed (uses Sonarr/Radarr API keys from environment)

8. **Jellyfin**
   - Set up libraries pointing to /movies and /shows
   - Configure transcoding settings
   - Create user accounts
   - Set up webhook for Deleterr integration

9. **abb-torznab**
   - Has no web interface; it is a Torznab endpoint for Prowlarr
   - In Prowlarr: Indexers → Add → Torznab, base URL `http://abb-torznab:8088`, API path `/api`, API key = `ABB_TORZNAB_API_KEY` from `.env`
   - Enable `Prefer magnet URL` so grabs go straight to qBittorrent
   - See `abb-torznab/README.md` for details and troubleshooting

## Special Features

### Sonarr & Radarr - Automatic ffmpeg Installation

Both Sonarr and Radarr require ffmpeg/ffprobe to detect sample files and prevent importing fake releases. This stack includes custom initialization scripts that automatically install ffmpeg on every container startup.

**Locations**:
- `./sonarr/custom-cont-init.d/install-ffmpeg.sh`
- `./radarr/custom-cont-init.d/install-ffmpeg.sh`

The scripts:
- Run automatically on container startup
- Check if ffmpeg is already installed
- Install ffmpeg via Alpine's package manager if needed
- Survive container recreations and updates

No manual configuration required - it just works!

### Cleanuparr - Dual Cleanup System

Cleanuparr provides comprehensive cleanup with two independent systems:

**QueueCleaner**:
- Monitors Sonarr/Radarr download queues
- Removes stuck/stalled downloads automatically
- Uses a 3-strike system before removal
- Triggers automatic re-searches

**DownloadCleaner**:
- Finds orphaned torrents in qBittorrent
- Moves unlinked downloads to `cleanuparr-unlinked` category
- Monitors categories: `radarr`, `sonarr`, `tv-sonarr`
- Runs hourly to keep your download client clean

### Deleterr - Smart Content Deletion

Deleterr automatically manages content removal when you delete items from Jellyfin:

**For Movies**:
- Completely removes the movie from Radarr
- Deletes all metadata files (posters, backdrops, .nfo files)
- Removes the entire movie folder

**For TV Shows**:
- Deletes the episode file from disk
- Unmonitors the episode to prevent re-download
- If series has ended AND it was the last episode → Deletes entire series from Sonarr
- If series is continuing or has other episodes → Keeps series in Sonarr

**Webhook Configuration**: Point Jellyfin's ItemRemoved webhook to `http://deleterr:5000/delete`

### abb-torznab - AudioBookBay Torznab Bridge

AudioBookBay has no maintained Prowlarr/Jackett definition, and its `.torrent`
endpoint requires a member login. The public search and detail pages are still
readable, so `abb-torznab` scrapes them and exposes the results over Torznab
with magnet links built from the info hash published on each detail page.

That makes ABB usable by Prowlarr (and therefore ReadMeABook, Sonarr, or
Radarr) without an account.

**Endpoints**

| Path | Purpose |
| --- | --- |
| `GET /api?t=caps` | Torznab capabilities (Audio/Audiobook, 3030) |
| `GET /api?t=search&q=...` | Search; returns magnets with `infohash` |
| `GET /healthz` | Liveness probe |

**How it works**

- Scrapes `/?s=<query>` and each result's detail page for the 40-hex info hash and trackers.
- Caches searches for 10 minutes and detail pages for 6 hours to stay polite.
- Falls back to FlareSolverr when Cloudflare challenges a request.
- Strips stopwords from queries: ABB's search is very fuzzy and a leading "The" returns unrelated books.
- Requires ≥80% of query tokens to appear in a result title, which rejects lookalike books.
- Prefers English results when a translated edition also matches.
- Serves the front page for query-less searches, because Prowlarr validates a new indexer that way.

**Configuration** (`.env`)

| Variable | Default | Notes |
| --- | --- | --- |
| `ABB_TORZNAB_PORT` | `8095` | Host port, bound to 127.0.0.1 only |
| `ABB_TORZNAB_API_KEY` | – | Shared secret Prowlarr sends as `apikey` |
| `ABB_BASE` | `https://audiobookbay.lu` | Mirror to scrape |
| `ABB_ASSUMED_SEEDERS` | `5` | ABB publishes no seeder counts |
| `ABB_TORZNAB_MEM_LIMIT` | `128m` | Container memory cap |

**Known limitations**

- **Seeder counts are invented.** ABB does not expose them, so every result
  reports `ABB_ASSUMED_SEEDERS`. A dead torrent therefore looks healthy to the
  download client and can stall at 0%.
- **Search is fuzzy.** The bridge filters aggressively, but a very generic title
  can still match the wrong edition.
- **No releases exist for many titles.** They will sit in `awaiting_search` and
  be retried hourly, which is expected behavior.

**Verifying it**

```bash
curl -s "http://127.0.0.1:8095/healthz"
curl -s "http://127.0.0.1:8095/api?t=caps&apikey=$ABB_TORZNAB_API_KEY"
curl -s "http://127.0.0.1:8095/api?t=search&q=the+pragmatic+programmer&apikey=$ABB_TORZNAB_API_KEY"
docker logs -f abb-torznab
```

### Updating Services

Updates are applied manually with `make update`, which pulls the latest images and
recreates the containers. Watchtower was removed because it was crash-looping
against the host's Docker API (client 1.25 vs. minimum 1.40) and had silently
stopped applying updates.

```bash
make update          # pull all images + recreate containers
make pull            # pull images only
docker system prune  # remove old images afterwards
```

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

Updates are manual:
```bash
make update
# or
docker compose pull && docker compose up -d
# Or use the Makefile
make update
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

4. **Audiobook searches time out**
   - FlareSolverr handles one challenge at a time and a solve can take 30-100s.
     Indexers behind it blow any client timeout when several searches run at once.
   - Keep FlareSolverr-tagged indexers out of *audiobook* categories in the
     client's indexer settings (they can stay enabled for other media types).
   - Check `docker logs abb-torznab` when AudioBookBay itself misbehaves.

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
