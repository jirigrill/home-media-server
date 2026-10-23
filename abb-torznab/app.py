#!/usr/bin/env python3
"""abb-torznab — Torznab bridge for AudioBookBay.

AudioBookBay (ABB) has no Prowlarr/Jackett definition any more and its
.torrent download endpoint requires a member login. The public search and
detail pages are still readable, so this service exposes ABB over Torznab
by scraping them and emitting magnet links built from the published info
hash.

Endpoints
  GET /api?t=caps                     Torznab capabilities
  GET /api?t=search&q=...             search
  GET /healthz                        liveness

Only the Python standard library is used.
"""

from __future__ import annotations

import gzip
import html as html_mod
import json
import os
import re
import socket
import threading
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.sax.saxutils as sax
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import format_datetime, formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

PORT = int(os.environ.get("ABB_PORT", "8088"))
BASE = os.environ.get("ABB_BASE", "https://audiobookbay.lu").rstrip("/")
FALLBACKS = [
    u.strip().rstrip("/")
    for u in os.environ.get("ABB_FALLBACKS", "https://audiobookbay.la,https://audiobookbay.is").split(",")
    if u.strip()
]
API_KEY = os.environ.get("ABB_API_KEY", "").strip()
FS_URL = os.environ.get("FLARESOLVERR_URL", "http://flaresolverr:8191/v1").strip()
ASSUMED_SEEDERS = max(1, int(os.environ.get("ABB_ASSUMED_SEEDERS", "5")))
TIMEOUT = float(os.environ.get("ABB_TIMEOUT", "25"))
SEARCH_TTL = int(os.environ.get("ABB_SEARCH_CACHE_TTL", "600"))       # 10 min
DETAIL_TTL = int(os.environ.get("ABB_DETAIL_CACHE_TTL", "21600"))     # 6 h
MAX_DETAIL_WORKERS = int(os.environ.get("ABB_DETAIL_WORKERS", "4"))
MAX_RESULTS = int(os.environ.get("ABB_MAX_RESULTS", "25"))

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

CATEGORY = 3030  # Audio/Audiobook

_log_lock = threading.Lock()


def log(msg: str) -> None:
    with _log_lock:
        print(f"[abb-torznab] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

CHALLENGE_MARKERS = (
    "just a moment",
    "cf-challenge",
    "attention required! | cloudflare",
    "enable javascript and cookies to continue",
    "checking your browser before accessing",
)


def http_get(url: str, timeout: float | None = None) -> tuple[str, int, str]:
    """GET a URL, following redirects. Returns (final_url, status, body)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": BASE + "/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            return resp.geturl(), resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        if exc.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return url, exc.code, raw.decode("utf-8", "replace")
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        return url, 0, f"__error__:{exc}"


def flaresolverr_get(url: str) -> tuple[str, int, str]:
    payload = json.dumps(
        {"cmd": "request.get", "url": url, "maxTimeout": 60000}
    ).encode("utf-8")
    req = urllib.request.Request(
        FS_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    if data.get("status") != "ok":
        raise RuntimeError(f"FlareSolverr: {data.get('message') or data.get('status')}")
    solution = data.get("solution") or {}
    return solution.get("url") or url, int(solution.get("status") or 200), solution.get("response") or ""


def is_challenge(status: int, body: str) -> bool:
    if status in (403, 429, 503):
        return True
    low = body[:4000].lower()
    return any(marker in low for marker in CHALLENGE_MARKERS)


def fetch(url: str) -> tuple[str, int, str]:
    """Fetch a page, falling back to FlareSolverr when Cloudflare interferes."""
    final_url, status, body = http_get(url)
    if status == 200 and not is_challenge(status, body):
        return final_url, status, body

    if is_challenge(status, body) and FS_URL:
        try:
            final_url, status, body = flaresolverr_get(url)
            log(f"flaresolverr fallback ok ({status}) {url}")
            return final_url, status, body
        except Exception as exc:  # noqa: BLE001 - keep the original response
            log(f"flaresolverr fallback failed: {exc} ({url})")

    return final_url, status, body


# --------------------------------------------------------------------------- #
# Scraping
# --------------------------------------------------------------------------- #

POST_TITLE_RE = re.compile(
    r'<div class="postTitle"><h2><a href="([^"]+)"[^>]*>(.*?)</a>', re.S
)
CATEGORY_RE = re.compile(r"Category:\s*(.*?)\s*<br", re.S | re.I)
LANGUAGE_RE = re.compile(r"Language:\s*(.*?)\s*<span", re.S | re.I)
POSTED_RE = re.compile(r"Posted:\s*([^<]+?)\s*<br", re.I)
FORMAT_RE = re.compile(r"Format:\s*<span[^>]*>\s*([^<]+?)\s*</span>", re.I)
BITRATE_RE = re.compile(r"Bitrate:\s*<span[^>]*>\s*([^<]+?)\s*</span>", re.I)
SIZE_RE = re.compile(r"File\s*Size:\s*<span[^>]*>\s*([\d.,]+)\s*</span>\s*([KMGTP]?)B", re.I)

INFO_HASH_RE = re.compile(
    r"Info\s*Hash:?\s*</td>\s*<td[^>]*>\s*([0-9a-fA-F]{40})\s*</td>", re.I
)
TRACKER_RE = re.compile(r"(?:udp|https?)://[^\s\"'<>]+?/announce[^\s\"'<>]*", re.I)

SIZE_UNITS = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}

_search_cache: dict[str, tuple[float, list[dict]]] = {}
_detail_cache: dict[str, tuple[float, dict | None]] = {}
_cache_lock = threading.Lock()
_active_base = BASE


def clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value or "")
    text = html_mod.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_size(block: str) -> int:
    match = SIZE_RE.search(block)
    if not match:
        return 0
    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return 0
    return int(number * SIZE_UNITS.get(match.group(2).upper(), 1))


def parse_posted(block: str) -> datetime:
    match = POSTED_RE.search(block)
    if match:
        raw = clean_text(match.group(1))
        for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return datetime.now(timezone.utc)


def parse_posts(body: str, base: str) -> list[dict]:
    posts = []
    for block in re.split(r'<div class="post">', body)[1:]:
        title_match = POST_TITLE_RE.search(block)
        if not title_match:
            continue

        href = html_mod.unescape(title_match.group(1)).strip()
        title = clean_text(title_match.group(2))
        if not href or not title:
            continue

        category_match = CATEGORY_RE.search(block)
        language_match = LANGUAGE_RE.search(block)
        format_match = FORMAT_RE.search(block)
        bitrate_match = BITRATE_RE.search(block)

        posts.append(
            {
                "url": urllib.parse.urljoin(base, href),
                "title": title,
                "category": clean_text(category_match.group(1)) if category_match else "",
                "language": clean_text(language_match.group(1)) if language_match else "",
                "posted": parse_posted(block),
                "format": clean_text(format_match.group(1)) if format_match else "",
                "bitrate": clean_text(bitrate_match.group(1)) if bitrate_match else "",
                "size": parse_size(block),
            }
        )
    return posts


def working_base(url: str) -> str:
    """Keep scraped detail links on the host that actually answered."""
    parsed = urllib.parse.urlparse(url)
    base = urllib.parse.urlparse(_active_base)
    if parsed.netloc and base.netloc and parsed.netloc != base.netloc:
        return parsed._replace(scheme=base.scheme, netloc=base.netloc).geturl()
    return url


def search_page(query: str) -> list[dict]:
    global _active_base

    now = time.time()
    with _cache_lock:
        cached = _search_cache.get(query)
    if cached and now - cached[0] < SEARCH_TTL:
        return cached[1]

    bases = [BASE] + [b for b in FALLBACKS if b != BASE]
    posts: list[dict] = []
    for base in bases:
        url = f"{base}/?s={urllib.parse.quote_plus(query)}"
        final_url, status, body = fetch(url)
        if status == 200 and not is_challenge(status, body):
            posts = parse_posts(body, base)
            _active_base = base
            if query:
                log(f'search "{query}" on {base} -> {len(posts)} rows')
            break

    with _cache_lock:
        _search_cache[query] = (now, posts)
    return posts


LATEST_KEY = "__latest__"


def latest_page() -> list[dict]:
    """Recent audiobooks from the ABB front page (used for empty queries/RSS)."""
    global _active_base

    now = time.time()
    with _cache_lock:
        cached = _search_cache.get(LATEST_KEY)
    if cached and now - cached[0] < SEARCH_TTL:
        return cached[1]

    posts: list[dict] = []
    for base in [BASE] + [b for b in FALLBACKS if b != BASE]:
        final_url, status, body = fetch(base + "/")
        if status == 200 and not is_challenge(status, body):
            posts = parse_posts(body, base)
            _active_base = base
            log(f"latest page on {base} -> {len(posts)} rows")
            break

    with _cache_lock:
        _search_cache[LATEST_KEY] = (now, posts)
    return posts


def detail_info(detail_url: str) -> dict | None:
    now = time.time()
    with _cache_lock:
        cached = _detail_cache.get(detail_url)
    if cached and now - cached[0] < DETAIL_TTL:
        return cached[1]

    info = None
    final_url, status, body = fetch(working_base(detail_url))
    if status == 200:
        hash_match = INFO_HASH_RE.search(body)
        if hash_match:
            trackers: list[str] = []
            for tracker in TRACKER_RE.findall(body):
                tracker = html_mod.unescape(tracker).strip()
                if tracker not in trackers:
                    trackers.append(tracker)
            info = {"hash": hash_match.group(1).lower(), "trackers": trackers[:10]}
    else:
        log(f"detail fetch failed ({status}) {detail_url}")

    with _cache_lock:
        _detail_cache[detail_url] = (now, info)
    return info


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #

STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "to", "in", "on", "for", "with", "by",
    "from", "at", "as", "is", "are", "was", "were", "be", "been", "being", "it",
    "its", "this", "that", "these", "those", "audiobook", "audiobooks", "audio",
    "book", "books", "unabridged", "abridged", "edition", "series", "novel",
    "complete", "vol", "volume", "part", "narrated", "narrator",
}


def norm_tokens(text: str) -> list[str]:
    ascii_text = (
        unicodedata.normalize("NFKD", text or "")
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return [w for w in ascii_text.split() if len(w) > 1 and w not in STOPWORDS]


def stem(word: str) -> str:
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def coverage(query_tokens: list[str], title_tokens: list[str]) -> tuple[float, int]:
    if not query_tokens:
        return 0.0, 0
    title_set = {stem(w) for w in title_tokens}
    hits = sum(1 for word in query_tokens if stem(word) in title_set)
    return hits / len(query_tokens), hits


def candidate_queries(query: str) -> list[str]:
    """Build ABB search terms.

    ABB's search is extremely fuzzy and a leading article such as "The"
    makes it return a page of unrelated books. Searching the significant
    words only is dramatically more precise, and keeping the author helps
    further, so try the full token set first and shorten from there.
    """
    query = query.strip()
    if not query:
        return []

    tokens = norm_tokens(query)
    candidates: list[str] = []
    if tokens:
        candidates.append(" ".join(tokens))
        for count in (6, 4, 3, 2):
            if len(tokens) > count:
                candidates.append(" ".join(tokens[:count]))
    if query not in candidates:
        candidates.append(query)

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique[:6]


def find_results(query: str) -> list[dict]:
    query_tokens = norm_tokens(query)
    if not query_tokens:
        return []

    pool: dict[str, dict] = {}
    for candidate in candidate_queries(query):
        for post in search_page(candidate):
            if post["url"] in pool:
                continue
            score, hits = coverage(query_tokens, norm_tokens(post["title"]))
            post = dict(post, score=score, hits=hits)
            pool[post["url"]] = post

        best = max((p["score"] for p in pool.values()), default=0.0)
        if best >= 0.85:
            break

    candidates = list(pool.values())
    # ABB has no seeder data and its search is very fuzzy, so require a
    # near-complete token match. A 0.6 floor let through unrelated books
    # that merely shared two generic words with the query.
    for threshold in (1.0, 0.8):
        selected = [
            p
            for p in candidates
            if p["score"] >= threshold and p["hits"] >= min(2, len(query_tokens))
        ]
        if selected:
            selected.sort(key=lambda p: (p["score"], p["size"]), reverse=True)
            english = [
                p
                for p in selected
                if not p["language"] or p["language"].lower().startswith("english")
            ]
            if english:
                selected = english
            log(
                f'"{query}" matched {len(selected)}/{len(candidates)} rows '
                f"(threshold {threshold:.1f})"
            )
            return selected[:MAX_RESULTS]

    log(f'"{query}" returned {len(candidates)} rows but none matched')
    return []


# --------------------------------------------------------------------------- #
# Torznab rendering
# --------------------------------------------------------------------------- #

def build_magnet(info: dict, title: str) -> str:
    magnet = f"magnet:?xt=urn:btih:{info['hash']}&dn={urllib.parse.quote(title, safe='')}"
    for tracker in info["trackers"]:
        magnet += "&tr=" + urllib.parse.quote(tracker, safe="")
    return magnet


def plain_tokens(text: str) -> list[str]:
    ascii_text = (
        unicodedata.normalize("NFKD", text or "")
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).split()


def retitle(title: str, query: str) -> str:
    """Separate the book title from a run-on subtitle with " - ".

    ABB posts are titled "Book Title Subtitle - Author". Downstream ranking
    treats a torrent title as a *complete* match only when the text after the
    requested title starts with a separator such as " - ". Without one,
    "Tiny Experiments How to Live Freely..." scores as a partial match and
    falls below the automatic-pick threshold, so split the title where the
    query stops matching and rejoin with " - ".
    """
    query_tokens = plain_tokens(query)
    if not query_tokens:
        return title

    raw_words = title.split()
    matched = 0
    qi = 0
    for raw_word in raw_words:
        word_tokens = plain_tokens(raw_word)
        if not word_tokens:
            break
        if query_tokens[qi:qi + len(word_tokens)] != word_tokens:
            break
        qi += len(word_tokens)
        matched += 1
        if qi >= len(query_tokens):
            break

    if matched == 0 or matched >= len(raw_words):
        return title

    head = " ".join(raw_words[:matched]).rstrip(" :,;|–—-")
    tail = " ".join(raw_words[matched:]).lstrip(" :-–—,;|")
    if not head or not tail:
        return title

    # Downstream title matching keys on the last *significant* word, so a
    # trailing edition number ("The Art of the Start 2.0") leaves "2.0" dangling
    # between the title and the separator. Bracket it so the separator follows
    # the significant word directly, while the full title still reads correctly.
    head_words = head.split()
    edition: list[str] = []
    while head_words and re.fullmatch(r"[0-9][0-9.]*", head_words[-1]):
        edition.insert(0, head_words.pop())
    if head_words and edition:
        head = f"{' '.join(head_words)} [{' '.join(edition)}]"

    return f"{head} - {tail}"


def display_title(post: dict, query: str = "") -> str:
    title = retitle(post["title"], query)
    upper = title.upper()
    tags: list[str] = []

    fmt = (post.get("format") or "").upper()
    if fmt in ("M4B", "M4A", "MP3", "FLAC") and fmt not in upper:
        tags.append(fmt)

    bitrate = post.get("bitrate") or ""
    match = re.search(r"(\d{2,3})", bitrate)
    if match and "KBPS" not in upper:
        tags.append(f"{match.group(1)}kbps")

    if tags:
        title = f"{title} [{' '.join(tags)}]"
    return title


def escape(value: str) -> str:
    return sax.escape(str(value), {'"': "&quot;"})


def render_item(post: dict, info: dict, query: str = "") -> str:
    title = display_title(post, query)
    magnet = build_magnet(info, title)
    size = post["size"] or 0
    pub_date = format_datetime(post["posted"])

    return (
        "<item>\n"
        f"  <title>{escape(title)}</title>\n"
        f'  <guid isPermaLink="false">abb-{info["hash"]}</guid>\n'
        f"  <link>{escape(magnet)}</link>\n"
        f"  <comments>{escape(post['url'])}</comments>\n"
        f"  <pubDate>{pub_date}</pubDate>\n"
        f"  <size>{size}</size>\n"
        f'  <enclosure url="{escape(magnet)}" length="{size}" type="application/x-bittorrent"/>\n'
        f"  <category>{CATEGORY}</category>\n"
        f'  <torznab:attr name="category" value="{CATEGORY}"/>\n'
        f'  <torznab:attr name="size" value="{size}"/>\n'
        f'  <torznab:attr name="seeders" value="{ASSUMED_SEEDERS}"/>\n'
        f'  <torznab:attr name="peers" value="{ASSUMED_SEEDERS}"/>\n'
        f'  <torznab:attr name="infohash" value="{info["hash"]}"/>\n'
        f'  <torznab:attr name="magneturl" value="{escape(magnet)}"/>\n'
        "</item>"
    )


def rss_document(query: str, items: list[str]) -> str:
    now = formatdate(timeval=None, localtime=False, usegmt=True)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" '
        'xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:torznab="http://torznab.com/schemas/2015/feed">\n'
        "<channel>\n"
        "  <title>AudioBookBay</title>\n"
        "  <description>AudioBookBay audiobooks via abb-torznab</description>\n"
        f"  <link>{escape(BASE)}/</link>\n"
        "  <language>en-us</language>\n"
        f"  <lastBuildDate>{now}</lastBuildDate>\n"
        f"  <category>{CATEGORY}</category>\n"
        f'  <atom:link href="{escape(BASE)}/api" rel="self" type="application/rss+xml"/>\n'
        + ("\n".join(items) + "\n" if items else "")
        + "</channel>\n"
        "</rss>\n"
    )


def caps_document() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<caps>\n"
        '  <server version="1.0" title="abb-torznab"/>\n'
        '  <limits max="100" default="50"/>\n'
        "  <searching>\n"
        '    <search available="yes" supportedParams="q"/>\n'
        '    <audiobook available="yes" supportedParams="q"/>\n'
        '    <book-search available="yes" supportedParams="q,author,title"/>\n'
        "  </searching>\n"
        "  <categories>\n"
        '    <category id="3000" name="Audio">\n'
        f'      <subcat id="{CATEGORY}" name="Audio/Audiobook"/>\n'
        "    </category>\n"
        "  </categories>\n"
        "</caps>\n"
    )


def torznab(params: dict[str, list[str]]) -> str:
    mode = (params.get("t") or ["search"])[0].lower()

    if mode == "caps":
        return caps_document()

    if mode not in ("search", "audiobook", "book", "book-search"):
        return rss_document("", [])

    query = (params.get("q") or [""])[0].strip()
    if not query:
        title = (params.get("title") or [""])[0].strip()
        author = (params.get("author") or [""])[0].strip()
        query = " ".join(part for part in (title, author) if part).strip()

    try:
        if query:
            posts = find_results(query)
        else:
            # Prowlarr validates a new indexer with a query-less search, so
            # serve the front page as a recent-releases feed.
            posts = latest_page()[:8]
    except Exception:  # noqa: BLE001 - never fail the indexer hard
        log("search failed:\n" + traceback.format_exc())
        return rss_document(query, [])

    if not posts:
        return rss_document(query, [])

    try:
        with ThreadPoolExecutor(max_workers=MAX_DETAIL_WORKERS) as pool:
            infos = list(pool.map(lambda post: detail_info(post["url"]), posts))
    except Exception:  # noqa: BLE001
        log("detail lookup failed:\n" + traceback.format_exc())
        return rss_document(query, [])

    items = [
        render_item(post, info, query)
        for post, info in zip(posts, infos)
        if info and info.get("hash")
    ]
    log(f'"{query}" -> {len(items)} magnet result(s)')
    return rss_document(query, items)


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #

class Handler(BaseHTTPRequestHandler):
    server_version = "abb-torznab/1.0"

    def _send(self, status: int, body: str, content_type: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

        if parsed.path == "/healthz":
            self._send(200, "ok\n", "text/plain; charset=utf-8")
            return

        if parsed.path not in ("/api", "/api/"):
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return

        if API_KEY and (params.get("apikey") or [""])[0] != API_KEY:
            self._send(401, "invalid api key\n", "text/plain; charset=utf-8")
            return

        try:
            xml = torznab(params)
        except Exception:  # noqa: BLE001
            log("unhandled error:\n" + traceback.format_exc())
            self._send(500, "internal error\n", "text/plain; charset=utf-8")
            return

        self._send(200, xml, "application/xml; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        log(f"{self.client_address[0]} {fmt % args}")


def main() -> None:
    log(
        f"starting on :{PORT} base={BASE} fallbacks={FALLBACKS} "
        f"auth={'on' if API_KEY else 'off'} assumed_seeders={ASSUMED_SEEDERS}"
    )
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
