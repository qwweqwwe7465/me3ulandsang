"""Deployment checks for the Core app.

These catch the two production misconfigurations that this project has actually
hit: an S3 backend without a bucket, and visitor statistics whose migration was
never applied.
"""

from django.conf import settings
from django.core.checks import Error, Warning, register
from django.core.checks import Tags
from django.db import connections

# Check ids are surfaced as e.g. "Core.E001" in `manage.py check`.
S3_BACKEND_MARKER = "storages.backends.s3"


@register()
def storage_settings_check(app_configs, **kwargs):
    """Warn when object storage is in use but not fully configured."""
    problems = []
    storages = getattr(settings, "STORAGES", {})
    default_backend = (storages.get("default") or {}).get("BACKEND", "")

    if S3_BACKEND_MARKER in default_backend:
        if not getattr(settings, "AWS_STORAGE_BUCKET_NAME", None):
            problems.append(
                Error(
                    "The default storage backend is S3 but AWS_STORAGE_BUCKET_NAME is not set.",
                    hint=(
                        "Every file upload and every image URL will fail with "
                        "'Required parameter name not set' until the bucket is configured. "
                        "Set AWS_STORAGE_BUCKET_NAME (and the access keys) in the environment "
                        "that the web process actually runs in."
                    ),
                    id="Core.E001",
                )
            )
        elif not getattr(settings, "AWS_ACCESS_KEY_ID", None) and not getattr(
            settings, "AWS_SESSION_TOKEN", None
        ):
            problems.append(
                Warning(
                    "The default storage backend is S3 without AWS_ACCESS_KEY_ID.",
                    hint=(
                        "Uploads will only work if the instance provides credentials some "
                        "other way (an IAM role or ~/.aws/credentials)."
                    ),
                    id="Core.W001",
                )
            )

    return problems


@register()
def visitor_tracking_check(app_configs, **kwargs):
    """Remind the operator to keep a sensible retention window."""
    problems = []
    retention = getattr(settings, "VISITOR_RETENTION_DAYS", None)
    if getattr(settings, "VISITOR_TRACKING_ENABLED", False) and retention is not None:
        if retention < 7:
            problems.append(
                Warning(
                    f"VISITOR_RETENTION_DAYS is {retention}; page views will be pruned almost immediately.",
                    hint="Use at least 7 days, or 180 for a typical retention window.",
                    id="Core.W002",
                )
            )
    return problems


@register(Tags.database)
def visitor_tables_check(app_configs, databases=None, **kwargs):
    """Error when the visitor tracking tables are missing.

    This is the failure that broke production: the code shipped ahead of
    ``migrate``, so every page that reads the statistics raised
    ``OperationalError: no such table: Core_visit``.
    """
    if not getattr(settings, "VISITOR_TRACKING_ENABLED", False):
        return []

    problems = []
    for alias in databases or ["default"]:
        connection = connections[alias]
        try:
            existing = set(connection.introspection.table_names())
        except Exception as error:  # noqa: BLE001 - report, never crash the check
            problems.append(
                Warning(
                    f"Could not inspect database '{alias}': {error}",
                    id="Core.W003",
                )
            )
            continue
        for table in ("Core_visit", "Core_dailyvisitor"):
            if table not in existing:
                problems.append(
                    Error(
                        f"Table '{table}' does not exist in database '{alias}'.",
                        hint=(
                            "Run `python manage.py migrate` in the environment that serves the "
                            "site, then restart the application."
                        ),
                        id="Core.E002",
                    )
                )
    return problems
