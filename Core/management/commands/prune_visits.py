"""Delete raw page-view rows older than the retention window.

DailyVisitor keeps the headline numbers, so discarding old raw rows only costs
you the per-page detail for those days.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from Core.models import Visit


class Command(BaseCommand):
    help = "Delete page views older than VISITOR_RETENTION_DAYS (default 180)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override the retention window in days.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting it.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = getattr(settings, "VISITOR_RETENTION_DAYS", 180)
        cutoff = timezone.now() - timedelta(days=days)
        queryset = Visit.objects.filter(created_at__lt=cutoff)
        total = queryset.count()

        if options["dry_run"]:
            self.stdout.write(f"{total} page view(s) older than {cutoff:%Y-%m-%d} would be deleted.")
            return

        deleted, _ = queryset.delete()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {deleted} page view(s) older than {cutoff:%Y-%m-%d}.")
        )
