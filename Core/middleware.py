"""First-party visitor tracking.

Records one Visit row per page view plus a per-day DailyVisitor row so the admin
can report unique and returning visitors without scanning the raw table.

Design notes:

* No client IP address is ever stored. ``visitor_hash`` is a salted digest, and
  the salt comes from SECRET_KEY, so a stolen database cannot be turned back
  into addresses.
* Tracking is completely silent. A failure to record a visit must never affect
  the page a visitor asked for.
* Only page views count. Static files, media, admin pages, export/prefetch
  requests and crawlers are skipped.
"""

import hashlib
import logging
import re

from django.conf import settings
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

# Requests per visitor per day are capped so a crawler or an open tab cannot
# flood the table.
MAX_VISITS_PER_VISITOR_PER_DAY = 500

# Paths that are assets or admin plumbing rather than content.
SKIP_PATH = re.compile(
    r"^/(static|media|admin|jsi18n|favicon\.ico|robots\.txt|sitemap\.xml)",
    re.IGNORECASE,
)
SKIP_EXTENSION = re.compile(
    r"\.(css|js|mjs|map|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|eot|mp3|m4a|ogg|wav|zip|txt|xml|json)$",
    re.IGNORECASE,
)
BOT_MARKERS = (
    "bot", "crawler", "spider", "slurp", "curl", "wget", "python-requests",
    "httpx", "headless", "monitor", "uptime", "facebookexternalhit", "preview",
)

# Only plain page loads are counted. POSTs (likes, feedback, the track form)
# and the fetch/prefetch traffic around them are not page views.
ALLOWED_METHODS = {"GET"}

TABLET_MARKERS = ("ipad", "tablet", "kindle", "playbook", "silk")
MOBILE_MARKERS = ("mobile", "android", "iphone", "ipod", "windows phone", "blackberry")


def client_ip(request):
    """Best effort client address, honouring the reverse proxy header when enabled."""
    if getattr(settings, "VISITOR_TRACKING_TRUST_PROXY", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or ""


def visitor_hash(ip_address, user_agent):
    """Salted, non-reversible identifier for a visitor."""
    salt = settings.SECRET_KEY or ""
    digest = hashlib.sha256(f"{salt}|{ip_address}|{user_agent}".encode("utf-8", "replace"))
    return digest.hexdigest()


def classify_device(user_agent):
    agent = (user_agent or "").lower()
    if any(marker in agent for marker in TABLET_MARKERS):
        return "tablet"
    if any(marker in agent for marker in MOBILE_MARKERS):
        return "mobile"
    return "desktop"


def looks_like_bot(user_agent):
    agent = (user_agent or "").lower()
    if not agent.strip():
        return True
    return any(marker in agent for marker in BOT_MARKERS)


def should_track(request, response):
    if not getattr(settings, "VISITOR_TRACKING_ENABLED", False):
        return False
    if request.method not in ALLOWED_METHODS:
        return False
    if response is None or response.status_code != 200:
        return False
    if getattr(response, "streaming", False):
        return False
    path = request.path or "/"
    if SKIP_PATH.match(path) or SKIP_EXTENSION.search(path):
        return False
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return False
    if request.headers.get("purpose") == "prefetch":
        return False
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        return False
    return True


class VisitorTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self.record(request, response)
        except Exception:  # pragma: no cover - tracking must never break a page
            logger.exception("Visitor tracking failed for %s", getattr(request, "path", "?"))
        return response

    def record(self, request, response):
        if not should_track(request, response):
            return

        from .models import DailyVisitor, Visit

        user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
        address = client_ip(request)
        digest = visitor_hash(address, user_agent)
        today = timezone.localdate()

        daily, created = DailyVisitor.objects.get_or_create(
            date=today, visitor_hash=digest, defaults={"views": 1}
        )
        # Cap each visitor's counted hits per day so an open tab cannot flood the table.
        if not created:
            DailyVisitor.objects.filter(pk=daily.pk, views__lt=MAX_VISITS_PER_VISITOR_PER_DAY).update(
                views=F("views") + 1
            )

        user = getattr(request, "user", None)
        session = getattr(request, "session", None)
        session_key = ""
        if session is not None:
            # The response has already been rendered, so saving the session now
            # also guarantees SessionMiddleware can still persist it afterwards.
            session.setdefault("_visitor_tracked", True)
            session_key = session.session_key or ""

        Visit.objects.create(
            path=(request.path or "/")[:500],
            referrer=(request.META.get("HTTP_REFERER", "") or "")[:500],
            session_key=session_key[:40],
            visitor_hash=digest,
            user=user if (user is not None and user.is_authenticated and not user.is_staff) else None,
            user_agent=user_agent,
            device=classify_device(user_agent),
            is_bot=looks_like_bot(user_agent),
        )
