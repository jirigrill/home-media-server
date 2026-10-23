# abb-torznab

A small Torznab bridge that makes **AudioBookBay** searchable from Prowlarr.

AudioBookBay has no maintained Prowlarr/Jackett definition, and its `.torrent`
download endpoint requires a member login. The public search and detail pages
are still readable though, so this service scrapes them and emits **magnet
links built from the info hash** published on each detail page. Prowlarr (and
therefore ReadMeABook, Sonarr, Radarr, ...) can then search and grab ABB
releases without an account.

Standard library only — no dependencies beyond `python:3.12-alpine`.

## Endpoints

| Path | Purpose |
| --- | --- |
| `GET /api?t=caps` | Torznab capabilities |
| `GET /api?t=search&q=<query>` | Search |
| `GET /healthz` | Liveness probe |

All `/api` calls require `apikey=<ABB_API_KEY>` when that variable is set.

Results carry `<link>` (the magnet), a `magneturl` attribute, `infohash`,
`size`, `seeders`, and category `3030` (Audio/Audiobook).

## How a search works

1. Build candidate queries from the request. Stopwords (`the`, `a`, `of`, ...)
   are removed and the query is progressively shortened, because ABB's search
   is extremely fuzzy: a query starting with "The" returns a page of unrelated
   books.
2. Scrape `/?s=<query>` and parse the result rows (title, category, language,
   format, bitrate, size, posted date).
3. Score each result by the fraction of query tokens present in its title.
   Only candidates with **≥80% coverage** (and at least two matching tokens)
   are kept, which filters out lookalike books such as "Shadow Eagle" for
   "The Eagle's Shadow". Full matches are preferred.
4. Prefer English rows when a translated edition also matches.
5. Fetch each detail page in parallel (4 workers) to read the info hash and
   tracker list, then render the Torznab XML.

A query-less search serves the front page (8 newest posts) because Prowlarr
validates a new indexer with a query-less request.

### Caching

- Search pages: 10 minutes (`ABB_SEARCH_CACHE_TTL`)
- Detail pages: 6 hours (`ABB_DETAIL_CACHE_TTL`)

### Cloudflare

Requests go out as a normal browser first. If the response looks like a
challenge, the bridge retries through FlareSolverr (`FLARESOLVERR_URL`,
default `http://flaresolverr:8191/v1`).

### Title reshaping

ABB titles read `Book Title Subtitle - Author`. Clients commonly judge a title
as a complete match only when the requested title is followed by a separator
such as ` - `, so the bridge rewrites titles to
`Book Title - Author - Subtitle [FORMAT]` (trailing edition numbers are
bracketed, e.g. `The Art of the Start [2.0]`). This keeps automatic selection
working instead of scoring every ABB release as a partial match.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `ABB_PORT` | `8088` | Listen port inside the container |
| `ABB_BASE` | `https://audiobookbay.lu` | Mirror to scrape |
| `ABB_API_KEY` | – | Shared secret; empty disables auth |
| `ABB_ASSUMED_SEEDERS` | `5` | Reported seeder count (see caveat) |
| `ABB_TIMEOUT` | `25` | Per-request timeout in seconds |
| `ABB_SEARCH_CACHE_TTL` | `600` | Search cache, seconds |
| `ABB_DETAIL_CACHE_TTL` | `21600` | Detail cache, seconds |
| `ABB_DETAIL_WORKERS` | `4` | Parallel detail fetches |
| `ABB_MAX_RESULTS` | `25` | Cap on returned items |
| `ABB_FALLBACKS` | `https://audiobookbay.la,https://audiobookbay.is` | Mirrors tried in order |
| `FLARESOLVERR_URL` | `http://flaresolverr:8191/v1` | Optional challenge solver |

In the stack, `docker-compose.yml` maps `127.0.0.1:${ABB_TORZNAB_PORT:-8095}`
to container port 8088 and passes `ABB_TORZNAB_API_KEY` as `ABB_API_KEY`.

## Adding it to Prowlarr

1. Indexers → Add Indexer → **Torznab**.
2. Base URL `http://abb-torznab:8088`, API path `/api`,
   API key = `ABB_TORZNAB_API_KEY` from `.env`.
3. Categories: `3030` (Audio/Audiobook).
4. Enable *Prefer magnet URL* so grabs are handed to the download client as
   magnets instead of proxied `.torrent` requests.

Prowlarr's download endpoint then answers with a `301` to `magnet:?xt=urn:btih:...`,
which clients follow transparently.

## Known limitations

- **Seeder counts are invented.** ABB publishes none, so every result reports
  `ABB_ASSUMED_SEEDERS`. Dead torrents look healthy and may stall at 0%.
- **Fuzzy search.** Aggressive token filtering helps, but a very generic title
  can still resolve to the wrong edition.
- **Availability.** Many niche titles simply are not uploaded to ABB; those
  searches will legitimately return nothing.

## Running standalone

```bash
docker build -t abb-torznab .
docker run --rm -p 8095:8088 -e ABB_API_KEY=test abb-torznab

curl -s "http://127.0.0.1:8095/healthz"
curl -s "http://127.0.0.1:8095/api?t=caps&apikey=test"
curl -s "http://127.0.0.1:8095/api?t=search&q=pragmatic+programmer&apikey=test"
```

Logs are written to stdout with an `[abb-torznab]` prefix; each search reports
how many rows were scraped, how many matched, and at which threshold.
