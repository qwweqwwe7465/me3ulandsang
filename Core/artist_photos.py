"""Fetch and attach an artist photo on demand.

The heavy lifting (Wikipedia, then iTunes, square-cropping) already lives in
Core/management/commands/fetch_artist_photos.py. This module exposes one
function for the upload flow to call so a newly created artist gets a picture
without a second manual step.

The fetch is bounded: if the network is slow or down, the artist is still
created with the default image and the upload continues.
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from uuid import uuid4

from django.core.files.base import ContentFile

from Core.management.commands.fetch_artist_photos import norm, safe_resolve, square_jpeg

logger = logging.getLogger(__name__)

DEFAULT_SIZE = 600
# Total time one artist's photo may take, across both sources.
DEFAULT_TIMEOUT = 12
# Time the upload page allows per source. Wikipedia and iTunes get their own
# slice, so a slow Wikipedia reply cannot consume iTunes' chance.
TIER_TIMEOUT = 6


def has_real_photo(artist):
    """True when the artist already has something better than the placeholder."""
    photo = getattr(artist, "photo", None)
    if not photo or not photo.name:
        return False
    return "default-artist" not in photo.name


def _resolve_within(name, use_wikipedia, use_itunes, timeout):
    """Run the (blocking) resolver with a deadline; None when it is too slow."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(safe_resolve, name, use_wikipedia, use_itunes)
        return future.result(timeout=timeout)
    except FutureTimeout:
        logger.warning("Photo lookup for %r timed out after %.1fs", name, timeout)
        return None
    except Exception:  # noqa: BLE001 - a lookup must never break the upload
        logger.exception("Photo lookup failed for %r", name)
        return None
    finally:
        pool.shutdown(wait=False)


def attach_photo(artist, size=DEFAULT_SIZE, timeout=DEFAULT_TIMEOUT):
    """Look up and save a photo for ``artist``.

    Returns the source that supplied it ("wikipedia", "itunes") or None. Never
    raises: a failure here must not lose the track the user just uploaded.
    """
    if artist is None or artist.pk is None:
        return None
    if has_real_photo(artist):
        return None

    deadline = time.monotonic() + timeout
    outcome = None

    # Wikipedia first: it gives real photos.
    remaining = deadline - time.monotonic()
    if remaining > 1:
        outcome = _resolve_within(artist.name, True, False, min(TIER_TIMEOUT, remaining))

    # Then iTunes, with its own slice of time. That way a slow or blocked
    # Wikipedia call cannot silently cost the artist its fallback artwork.
    if not (outcome and outcome.get("data")):
        remaining = deadline - time.monotonic()
        if remaining > 1:
            if outcome and outcome.get("wiki_status") == "error":
                logger.info("Wikipedia errored for %r; trying iTunes", artist.name)
            outcome = _resolve_within(artist.name, False, True, min(TIER_TIMEOUT, remaining))

    if not outcome or not outcome.get("data"):
        logger.info(
            "No photo found for %r (wikipedia=%s, itunes=%s)",
            artist.name,
            (outcome or {}).get("wiki_status"),
            (outcome or {}).get("itunes_status"),
        )
        return None

    try:
        image = square_jpeg(outcome["data"], size)
    except Exception:  # noqa: BLE001 - undecodable image
        logger.warning("Could not decode the photo fetched for %r", artist.name)
        return None

    slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", norm(artist.name))).strip("-")
    filename = f"artists/{slug or 'artist'}-{uuid4().hex[:6]}.jpg"
    try:
        artist.photo.save(filename, ContentFile(image), save=True)
    except Exception:  # noqa: BLE001 - storage problem must not break the upload
        logger.exception("Could not save the photo for %r", artist.name)
        return None

    logger.info("Attached %s photo for %r", outcome.get("tier"), artist.name)
    return outcome.get("tier")
