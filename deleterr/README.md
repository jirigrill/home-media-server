# Deleterr

Jellyfin webhook receiver to automatically unmonitor deleted content in Sonarr/Radarr.

## Features

- Receives webhooks from Jellyfin when content is deleted
- Automatically unmonitors episodes in Sonarr
- Automatically unmonitors movies in Radarr
- Rebuilds missing series/season/episode context from the Jellyfin API when the
  webhook template renders it empty (Media Cleaner purges whole shows in one
  batch, so child `ItemDeleted` notifications can arrive with only the title)
- Clean, modular architecture with proper separation of concerns
- Health check and test endpoints

## Endpoints

- `POST /delete` - Main webhook endpoint for Jellyfin
- `GET /health` - Health check endpoint
- `POST /test` - Test webhook endpoint for debugging

`POST /delete` answers with one of three states:

| Result | HTTP | Meaning |
| --- | --- | --- |
| `success` | 200 | item unmonitored/deleted, or intentionally preserved |
| `ignored` | 200 | item could not be identified; nothing to act on |
| `error` | 500 | item identified but the Sonarr/Radarr call failed |

Unparseable bodies are logged in full (content type, length, first 500 bytes)
and answered with `400` instead of raising.

## Configuration

Configure via environment variables:

- `SONARR_URL` - Sonarr URL (default: http://sonarr:8989)
- `RADARR_URL` - Radarr URL (default: http://radarr:7878)
- `SONARR_API_KEY` - Sonarr API key (required)
- `RADARR_API_KEY` - Radarr API key (required)
- `JELLYFIN_URL` - Jellyfin URL (default: http://jellyfin:8096)
- `JELLYFIN_API_KEY` - Jellyfin API key (required for context recovery)
- `DELETERR_PORT` - Service port (default: 5000)
- `LOG_LEVEL` - Logging level (default: INFO)

## Jellyfin webhook configuration

The payload Deleterr expects is kept in
[`jellyfin-webhook-template.json`](jellyfin-webhook-template.json). It must be
installed as the *Template* of the Jellyfin Webhook plugin's generic webhook
(`http://deleterr:5000/delete`, `ItemDeleted` only).

Two rules matter:

- Every value is quoted. An unquoted placeholder such as `"Year": {{Year}}`
  renders as `"Year": ,` when the field is empty, which is invalid JSON and
  makes Jellyfin's delivery fail with `400`.
- `SeriesName`, `SeriesId`, `SeasonNumber` and `EpisodeNumber` are best-effort
  only. Deleterr recovers them from the Jellyfin API when they are empty.

`jellyfin/` is gitignored, so the live plugin XML is not versioned. Install the
template from the repo copy:

```sh
python3 - <<'PY'
import base64, re, pathlib

template = pathlib.Path("deleterr/jellyfin-webhook-template.json").read_text()
xml_path = pathlib.Path("jellyfin/plugins/configurations/Jellyfin.Plugin.Webhook.xml")
xml = xml_path.read_text()
encoded = base64.b64encode(template.encode()).decode()
xml_path.write_text(re.sub(r"<Template>[^<]*</Template>", f"<Template>{encoded}</Template>", xml))
PY
```

The plugin XML is root-owned, so run this with `sudo` and restart Jellyfin
afterwards to load the new template.

## Usage

1. Configure Jellyfin webhook to point to `http://deleterr:5000/delete`
2. Enable "Item Deleted" event in Jellyfin webhook settings
3. When content is deleted from Jellyfin, it will be automatically unmonitored in Sonarr/Radarr
