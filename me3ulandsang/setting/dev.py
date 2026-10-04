"""Development settings. Never use these on a public deployment."""

import os

from me3ulandsang.settings import *  # noqa: F403


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-development-only-key")
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INTERNAL_IPS = ["127.0.0.1", "::1"]

# django-debug-toolbar is optional, so a fresh install can still run normally.
if os.environ.get("DJANGO_DEBUG_TOOLBAR") == "1":
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa: F405
    
MEDIA_ROOT = BASE_DIR / "me3ulandsang" / "media"
STATIC_ROOT = BASE_DIR / "staticfiles"