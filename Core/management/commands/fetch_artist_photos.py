"""Fetch artist profile pictures from keyless public sources and square-crop them.

Tier 1  Wikipedia (English, then Persian for non-Latin names) lead image, served
        from Wikimedia Commons. Real photos of the artist.
Tier 2  iTunes Search album artwork. Square by definition, and available for
        artists Wikipedia has no photo of - but it is cover art, not a face.
Tier 3  The existing default-artist.png placeholder.

Every image is centre-cropped to a square and stored under media/artists/.

Both public APIs throttle. So: modest concurrency, a rate limiter on the iTunes
search endpoint, and every call reports "found", "none" or "error" - a network
failure is never silently recorded as "no image exists". If Wikipedia starts
erroring repeatedly it is switched off for the remainder of the run, and artists
that failed keep their placeholder, so simply re-running retries exactly them.
Database writes stay on the main thread, so SQLite is never written concurrently.

    python manage.py fetch_artist_photos --limit 10      # trial
    python manage.py fetch_artist_photos                 # everyone missing one
"""

from __future__ import annotations

import io
import json
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from Core.models import Artist
from PIL import Image

USER_AGENT = "me3ulandsang-artist-photos/1.0 (personal local Django project)"
TIMEOUT = 10
ITUNES_MIN_INTERVAL = 3.5  # the search API allows roughly 20 calls per minute
WIKIPEDIA_ERROR_BUDGET = 12  # consecutive network errors before we give up on it

# A Wikipedia description must contain one of these before we trust the match.
MUSIC_WORDS = (
    "band", "musician", "singer", "rapper", "composer", "guitarist", "drummer",
    "vocalist", "songwriter", "multi-instrumentalist", "bassist", "pianist",
    "violinist", "cellist", "disc jockey", "dj", "record producer", "orchestra",
    "ensemble", "musical group", "musical duo", "recording artist", "musical artist",
    "hip hop", "heavy metal", "rock band", "metal band", "conductors",
)

# ...and must not look like one of these.
REJECT_WORDS = (
    "album", "song by", "film", "village", "municipality", "genus", "species",
    "footballer", "actor", "politician", "company", "newspaper", "river",
    "disambiguation", "list of", "discography", "genetic", "protein",
)

_itunes_lock = threading.Lock()
_itunes_last = [0.0]


def fetch(url: str, *, as_json: bool = True, timeout: int = TIMEOUT):
    """GET a URL. 4xx replies are deterministic, so they are never retried."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
            return json.loads(payload) if as_json else payload
        except urllib.error.HTTPError:
            raise
        except Exception:
            if attempt:
                raise
            time.sleep(0.5)


def itunes_fetch(url: str):
    """Serialised, rate-limited access to the iTunes search endpoint."""
    with _itunes_lock:
        wait = ITUNES_MIN_INTERVAL - (time.time() - _itunes_last[0])
        if wait > 0:
            time.sleep(wait)
        _itunes_last[0] = time.time()
    return fetch(url)


def norm(value: str) -> str:
    """Fold a name for comparison: NFC, no parentheticals, alphanumerics only."""
    text = unicodedata.normalize("NFC", value or "")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.casefold()
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", text)


def is_non_latin(value: str) -> bool:
    """True when the name uses a non-Latin script, so fa.wikipedia is worth trying."""
    return bool(re.search(r"[\u0600-\u06ff\u0400-\u04ff\u3040-\u30ff\u4e00-\u9fff]", value or ""))


def square_jpeg(data: bytes, size: int) -> bytes:
    """Centre-crop to a square and re-encode as JPEG."""
    image = Image.open(io.BytesIO(data))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((size, size), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def commons_name(url: str) -> str:
    """Pull the Commons file name out of a Wikipedia thumbnail/original URL."""
    match = re.search(r"/commons/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/]+)", url or "")
    return urllib.parse.unquote(match.group(1)) if match else ""


# File names scraped from music sites often carry junk after the artist name,
# e.g. "Majid Kharatha @RozMusic.com", "Ahmagh Man Oghdeyim ~ UpMusic",
# "Siyavash Ghomeyshi [BibakMusic.com]". Searching the raw tag never matches.
_SITE_SUFFIX = re.compile(r"\s*[@~|]\s*[^\s]+.*$")
_BRACKETED = re.compile(r"[\(\[]([^)\]]*)[)\]]")


def search_name(name: str) -> str:
    """The artist name with download-site decoration stripped off."""
    cleaned = _BRACKETED.sub(" ", name or "")
    cleaned = _SITE_SUFFIX.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_.,/")
    return cleaned or (name or "")


def wikipedia_image(name: str) -> dict:
    """Resolve a validated Wikipedia image. Returns status found/none/error."""
    name = search_name(name)
    languages = ["en"] + (["fa"] if is_non_latin(name) else [])
    wanted = norm(name)
    searches_ok = 0

    for lang in languages:
        base = f"https://{lang}.wikipedia.org"
        try:
            search = fetch(
                f"{base}/w/api.php?action=query&list=search&srnamespace=0&format=json"
                f"&srlimit=5&srsearch={urllib.parse.quote(name)}"
            )
            searches_ok += 1
        except Exception as error:
            continue

        titles = [hit["title"] for hit in search.get("query", {}).get("search", [])]
        exact = [title for title in titles if norm(title) == wanted]
        if exact:
            candidates = exact[:2]
        else:
            # "Bach" lives at "Johann Sebastian Bach", so also accept a page
            # whose title contains the name as a whole word.
            word = re.compile(rf"(?<![a-z0-9]){re.escape(name.strip())}(?![a-z0-9])", re.IGNORECASE)
            candidates = [title for title in titles if word.search(title)][:2]

        for title in candidates:
            try:
                summary = fetch(f"{base}/api/rest_v1/page/summary/{urllib.parse.quote(title)}")
            except Exception:
                continue

            description = (summary.get("description") or "").lower()
            if not any(word in description for word in MUSIC_WORDS):
                continue
            if any(word in description for word in REJECT_WORDS):
                continue

            original = (summary.get("originalimage") or {}).get("source") or ""
            thumbnail = (summary.get("thumbnail") or {}).get("source") or ""
            filename = commons_name(original) or commons_name(thumbnail)
            page = (summary.get("content_urls", {}).get("desktop", {}) or {}).get("page", "")

            urls = []
            if filename:
                urls.append(
                    "https://commons.wikimedia.org/wiki/Special:FilePath/"
                    + urllib.parse.quote(filename)
                    + "?width=1000"
                )
            if thumbnail:
                urls.append(thumbnail)
            if original:
                urls.append(original)

            for url in urls:
                try:
                    data = fetch(url, as_json=False)
                except Exception:
                    continue
                if data and len(data) > 2000:
                    return {
                        "status": "found",
                        "data": data,
                        "source": page or url,
                        "description": description,
                    }

    if not searches_ok:
        return {"status": "error"}
    return {"status": "none"}


def itunes_artwork(name: str) -> dict:
    """Resolve the artist's album art. Returns status found/none/error."""
    name = search_name(name)
    try:
        payload = itunes_fetch(
            "https://itunes.apple.com/search?entity=album&limit=10&term=" + urllib.parse.quote(name)
        )
    except Exception as error:
        return {"status": "error", "error": str(error)}

    wanted = norm(name)
    for result in payload.get("results", []):
        if norm(result.get("artistName", "")) != wanted:
            continue
        artwork = result.get("artworkUrl100") or ""
        if not artwork:
            continue
        for url in (artwork.replace("/100x100bb.jpg", "/600x600bb.jpg"), artwork):
            try:
                data = fetch(url, as_json=False)
            except Exception:
                continue
            if data and len(data) > 2000:
                return {"status": "found", "data": data, "source": result.get("collectionViewUrl") or url}
    return {"status": "none"}


def resolve(name: str, use_wikipedia: bool, use_itunes: bool) -> dict:
    """Network-only worker: decide which image this artist should get."""
    wiki_status = "skipped"
    if use_wikipedia:
        result = wikipedia_image(name)
        wiki_status = result["status"]
        if wiki_status == "found":
            return {"tier": "wikipedia", "wiki_status": wiki_status, "itunes_status": "skipped", **result}

    itunes_status = "skipped"
    if use_itunes:
        result = itunes_artwork(name)
        itunes_status = result["status"]
        if itunes_status == "found":
            return {"tier": "itunes", "wiki_status": wiki_status, "itunes_status": itunes_status, **result}

    return {"tier": None, "wiki_status": wiki_status, "itunes_status": itunes_status}


def safe_resolve(name: str, use_wikipedia: bool, use_itunes: bool) -> dict:
    """Wrap resolve() so one bad artist cannot abort a whole chunk."""
    try:
        return resolve(name, use_wikipedia, use_itunes)
    except Exception as error:  # noqa: BLE001 - report per artist and continue
        return {"tier": None, "wiki_status": "error", "itunes_status": "error", "error": str(error)}


class Command(BaseCommand):
    help = "Fetch and square-crop artist profile pictures from Wikipedia, then iTunes."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Only process N artists.")
        parser.add_argument("--size", type=int, default=600, help="Square size in pixels (default: %(default)s).")
        parser.add_argument("--workers", type=int, default=4, help="Concurrent fetches (default: %(default)s).")
        parser.add_argument("--refresh", action="store_true", help="Re-fetch artists that already have a photo.")
        parser.add_argument("--skip-wikipedia", action="store_true", help="Do not use Wikipedia/Commons.")
        parser.add_argument("--skip-itunes", action="store_true", help="Do not use iTunes artwork.")
        parser.add_argument(
            "--report",
            default=str(Path(settings.BASE_DIR) / "tmp" / "artist_photos_report.json"),
            help="Where to write the per-artist result log (default: %(default)s).",
        )

    def say(self, message: str):
        self.stdout.write(message)
        try:
            self.stdout._out.flush()
        except Exception:
            pass

    def handle(self, *args, **options):
        for stream in (self.stdout, self.stderr):
            try:
                stream._out.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        size = options["size"]
        limit = options["limit"]
        workers = max(1, options["workers"])
        use_wikipedia = not options["skip_wikipedia"]
        use_itunes = not options["skip_itunes"]

        queryset = Artist.objects.all()
        if not options["refresh"]:
            queryset = queryset.filter(photo__in=["", "default-artist.png"])
        artists = list(queryset.order_by("name"))
        if limit:
            artists = artists[:limit]

        self.say(f"artists to process : {len(artists)}")
        self.say(f"workers            : {workers}")
        self.say(f"square size        : {size}px")
        self.say(f"sources            : wikipedia={'on' if use_wikipedia else 'off'} itunes={'on' if use_itunes else 'off'}")
        self.say("")

        results = []
        tiers = {"wikipedia": 0, "itunes": 0, "none": 0}
        failures = []
        done = 0
        wiki_errors = 0

        chunk_size = workers * 4
        for start in range(0, len(artists), chunk_size):
            chunk = artists[start : start + chunk_size]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                resolved = list(
                    pool.map(lambda a: (a, safe_resolve(a.name, use_wikipedia, use_itunes)), chunk)
                )

            for artist, outcome in resolved:
                done += 1
                label = f"[{done}/{len(artists)}] {artist.name}"

                if outcome.get("wiki_status") == "error":
                    wiki_errors += 1
                    if use_wikipedia and wiki_errors >= WIKIPEDIA_ERROR_BUDGET:
                        use_wikipedia = False
                        self.say(f"  !!  wikipedia erroring ({wiki_errors}); "
                                 f"disabling it for the rest of this run")
                elif outcome.get("wiki_status") == "found":
                    wiki_errors = 0

                if outcome["tier"] is None:
                    tiers["none"] += 1
                    note = ""
                    if outcome.get("wiki_status") == "error" or outcome.get("itunes_status") == "error":
                        note = " [network error]"
                        failures.append((artist.name, f"wiki={outcome.get('wiki_status')} itunes={outcome.get('itunes_status')}"))
                    self.say(f"  --  {label}{note}")
                    results.append(
                        {
                            "artist": artist.name,
                            "tier": None,
                            "wiki_status": outcome.get("wiki_status"),
                            "itunes_status": outcome.get("itunes_status"),
                        }
                    )
                    continue

                try:
                    image = square_jpeg(outcome["data"], size)
                except Exception as error:
                    tiers["none"] += 1
                    failures.append((artist.name, f"decode: {error}"))
                    self.say(f"  !!  {label} (undecodable)")
                    results.append({"artist": artist.name, "tier": None, "source": outcome.get("source")})
                    continue

                slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", norm(artist.name))).strip("-")
                filename = f"artists/{slug or uuid4().hex[:8]}-{uuid4().hex[:6]}.jpg"
                artist.photo.save(filename, ContentFile(image), save=True)

                tiers[outcome["tier"]] += 1
                self.say(f"  ok  {label}  <- {outcome['tier']} ({len(image) // 1024}KB)")
                results.append(
                    {
                        "artist": artist.name,
                        "tier": outcome["tier"],
                        "source": outcome.get("source", ""),
                        "description": outcome.get("description", ""),
                        "saved": filename,
                    }
                )

        report_path = Path(options["report"])
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Merge with earlier runs so the report stays a complete record even
        # though finished artists are skipped by a re-run.
        merged: dict = {}
        if report_path.exists():
            try:
                with open(report_path, encoding="utf-8") as handle:
                    for entry in json.load(handle).get("results", []):
                        merged[entry["artist"]] = entry
            except Exception:
                pass
        for entry in results:
            previous = merged.get(entry["artist"], {})
            if entry["tier"] is None and previous.get("tier"):
                continue  # keep the earlier success
            merged[entry["artist"]] = entry

        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "processed_this_run": len(artists),
                    "tiers_this_run": tiers,
                    "failures_this_run": failures,
                    "results": sorted(merged.values(), key=lambda e: e["artist"].casefold()),
                },
                handle,
                ensure_ascii=False,
                indent=1,
            )

        remaining = Artist.objects.filter(photo__in=["", "default-artist.png"]).count()
        self.say("")
        self.say(f"wikipedia photos : {tiers['wikipedia']}")
        self.say(f"itunes artwork   : {tiers['itunes']}")
        self.say(f"no image found   : {tiers['none']}")
        if failures:
            self.say(f"errors           : {len(failures)}")
            for name, reason in failures[:10]:
                self.say(f"  {name} — {reason}")
        self.say(f"artists still on default-artist.png: {remaining}")
        self.say(f"report           {report_path}")
