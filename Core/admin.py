"""Admin configuration for the Core music catalogue.

Every changelist is built to answer the questions you actually have while
running the site: what does it look like, how is it performing, and what still
needs attention (missing artwork, missing audio, missing lyrics).
"""

import logging

from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.db.models import Count
from django.urls import reverse
from django.utils.functional import SimpleLazyObject
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import (
    Album,
    Album_track_relation,
    Artist,
    Feedback,
    Genre,
    Playlist,
    Playlist_track_relation,
    Track,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Site branding
# --------------------------------------------------------------------------- #

admin.site.site_header = "Me3ulandsang administration"
admin.site.site_title = "Me3ulandsang admin"
admin.site.index_title = "Catalogue overview"

THUMB_SIZE = 50

# Previews are rendered as <img> tags whose source comes from storage. When a
# record points at a file that is not actually in storage (common while moving
# between local media and the production bucket) the image reports the failure,
# and Core/static/Core/css/admin_previews.css turns it into a dashed placeholder
# instead of a broken-image icon. An empty field renders the same placeholder.
EMPTY_THUMB = (
    '<span style="display:inline-block;width:{size}px;height:{size}px;'
    "border:1px dashed #ccc;border-radius:4px;line-height:{size}px;"
    'text-align:center;color:#999;font-size:11px;">&ndash;</span>'
)


# --------------------------------------------------------------------------- #
# Shared display helpers
# --------------------------------------------------------------------------- #

def thumbnail(image, size=THUMB_SIZE, missing_label="image not found in storage"):
    """Inline preview for an ImageField, safe to use in list and detail pages."""
    if not image:
        return format_html(EMPTY_THUMB, size=size)
    try:
        url = image.url
    except ValueError:
        return format_html(EMPTY_THUMB, size=size)
    return format_html(
        '<img class="core-thumb" src="{}" alt="" title="{}" width="{}" height="{}"'
        ' onerror="this.dataset.missing=1">',
        url,
        missing_label,
        size,
        size,
    )


def audio_player(audio, width=320):
    """Small HTML5 player, so an uploaded track can be checked without downloading it."""
    if not audio:
        return mark_safe('<span style="color:#ba2121;">No audio file uploaded</span>')
    try:
        url = audio.url
    except ValueError:
        return mark_safe('<span style="color:#ba2121;">No audio file uploaded</span>')
    return format_html(
        '<audio controls preload="none" style="max-width:{}px;height:32px;" src="{}">'
        '<a href="{}">{}</a></audio>',
        width,
        url,
        url,
        audio.name,
    )


def related_change_link(obj, label=None):
    """Link to another object's admin change page."""
    if obj is None:
        return mark_safe("&ndash;")
    url = reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])
    return format_html('<a href="{}">{}</a>', url, label or str(obj))


def object_links(manager):
    """Comma separated links to every object in a related manager."""
    return format_html_join(
        ", ",
        '<a href="{}">{}</a>',
        (
            (reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk]), str(obj))
            for obj in manager.all()
        ),
    ) or mark_safe("&ndash;")


def track_cell(track, size=32):
    """Cover thumbnail plus title, used by the through-model inlines."""
    if track is None:
        return mark_safe("&ndash;")
    return format_html(
        '{} <span class="mini quiet">{}</span>',
        thumbnail(getattr(track, "cover", None), size),
        str(track),
    )


class TrackPreviewMixin:
    """Adds a read-only cover preview column to the album/playlist track inlines."""

    class PreviewForm(forms.ModelForm):
        # Declaring the field on the form is what lets it render read-only
        # without being posted back on save.
        track_preview = forms.CharField(required=False, label="Preview", disabled=True)

        class Meta:
            fields = "__all__"

    form = PreviewForm

    @admin.display(description="Preview")
    def track_preview(self, obj):
        return track_cell(obj.track if obj and obj.track_id else None)


class PreviewMediaMixin:
    """Loads the stylesheet that renders the preview images."""

    class Media:
        css = {"all": ("Core/css/admin_previews.css",)}


# --------------------------------------------------------------------------- #
# Genre
# --------------------------------------------------------------------------- #

@admin.register(Genre)
class GenreAdmin(PreviewMediaMixin, admin.ModelAdmin):
    list_display = ("name", "track_count", "album_count", "artist_count", "top_track_link")
    search_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _tracks=Count("rel_track", distinct=True),
                _albums=Count("rel_album", distinct=True),
                _artists=Count("rel_artist", distinct=True),
            )
            .prefetch_related("rel_track")
        )

    @admin.display(description="Tracks", ordering="_tracks")
    def track_count(self, obj):
        return obj._tracks

    @admin.display(description="Albums", ordering="_albums")
    def album_count(self, obj):
        return obj._albums

    @admin.display(description="Artists", ordering="_artists")
    def artist_count(self, obj):
        return obj._artists

    @admin.display(description="Most liked track")
    def top_track_link(self, obj):
        # obj.top_track() would issue one query per row, so the tracks are
        # prefetched and the winner picked in Python instead.
        tracks = list(obj.rel_track.all())
        if not tracks:
            return mark_safe("&ndash;")
        track = max(tracks, key=lambda candidate: candidate.likes)
        return format_html(
            "{} <span class='mini quiet'>({} likes)</span>",
            related_change_link(track),
            track.likes,
        )


# --------------------------------------------------------------------------- #
# Artist
# --------------------------------------------------------------------------- #

@admin.register(Artist)
class ArtistAdmin(PreviewMediaMixin, admin.ModelAdmin):
    list_display = (
        "photo_preview",
        "name",
        "genres_list",
        "track_count",
        "album_count",
        "views",
        "likes",
        "engagement",
        "is_active",
    )
    list_display_links = ("name",)
    list_filter = ("genres",)
    search_fields = ("name", "genres__name")
    ordering = ("name",)
    readonly_fields = ("photo_preview", "engagement", "track_count", "album_count")
    list_per_page = 30
    save_on_top = True
    fieldsets = (
        (None, {"fields": ("name", "photo", "photo_preview", "genres")}),
        ("Biography", {"fields": ("description",)}),
        (
            "Statistics",
            {
                "fields": ("views", "likes", "engagement", "track_count", "album_count"),
                "description": "Counters are maintained by the public site; edit them only to correct data.",
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("genres")
            .annotate(
                _tracks=Count("tracks", distinct=True),
                # Albums an artist appears on, via the tracks they performed on.
                _albums=Count("tracks__albumr__album", distinct=True),
            )
        )

    @admin.display(description="Photo")
    def photo_preview(self, obj):
        return thumbnail(obj.photo)

    @admin.display(description="Genres")
    def genres_list(self, obj):
        return object_links(obj.genres)

    @admin.display(description="Tracks", ordering="_tracks")
    def track_count(self, obj):
        return obj._tracks

    @admin.display(description="Albums", ordering="_albums")
    def album_count(self, obj):
        return obj._albums

    @admin.display(description="Views / likes")
    def engagement(self, obj):
        if not obj.views:
            return "&ndash;"
        return format_html(
            "{} / {} <span class='mini quiet'>({}% like rate)</span>",
            obj.views,
            obj.likes,
            round(obj.likes * 100 / obj.views, 1),
        )

    @admin.display(boolean=True, description="Has tracks")
    def is_active(self, obj):
        # Uses the queryset annotation, so the changelist does not run one
        # existence query per artist row.
        return bool(obj._tracks)


# --------------------------------------------------------------------------- #
# Through-model inlines (album / playlist track lists)
# --------------------------------------------------------------------------- #

class AlbumTrackRelationInline(TrackPreviewMixin, admin.TabularInline):
    model = Album_track_relation
    fk_name = "album"
    extra = 1
    autocomplete_fields = ("track",)
    fields = ("order", "track", "track_preview")
    ordering = ("order",)
    verbose_name = "track in this album"
    verbose_name_plural = "Track list (order controls playback sequence)"

    def get_queryset(self, request):
        # The preview column reads each row's track, so fetch them together.
        return super().get_queryset(request).select_related("track")


class PlaylistTrackRelationInline(TrackPreviewMixin, admin.TabularInline):
    model = Playlist_track_relation
    fk_name = "playlist"
    extra = 1
    autocomplete_fields = ("track",)
    fields = ("order", "track", "track_preview")
    ordering = ("order",)
    verbose_name = "track in this playlist"
    verbose_name_plural = "Track list (order controls playback sequence)"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("track")


class TrackAlbumRelationInline(admin.TabularInline):
    """Show which albums a track appears on, straight from the track page."""

    model = Album_track_relation
    fk_name = "track"
    extra = 0
    autocomplete_fields = ("album",)
    fields = ("album", "order")


class TrackPlaylistRelationInline(admin.TabularInline):
    model = Playlist_track_relation
    fk_name = "track"
    extra = 0
    autocomplete_fields = ("playlist",)
    fields = ("playlist", "order")


# --------------------------------------------------------------------------- #
# Album
# --------------------------------------------------------------------------- #

@admin.register(Album)
class AlbumAdmin(PreviewMediaMixin, admin.ModelAdmin):
    list_display = (
        "cover_preview",
        "name",
        "artist_names",
        "release_date",
        "track_count",
        "genres_list",
        "views",
        "likes",
        "date_added",
    )
    list_display_links = ("name",)
    list_filter = ("genres", "release_date")
    search_fields = ("name", "description", "tracks__title", "tracks__artist__name")
    date_hierarchy = "release_date"
    ordering = ("-release_date",)
    readonly_fields = ("cover_preview", "track_count", "date_added")
    inlines = [AlbumTrackRelationInline]
    list_per_page = 30
    save_on_top = True
    fieldsets = (
        (None, {"fields": ("name", "cover_preview", "genres", "release_date")}),
        ("Description", {"fields": ("description",)}),
        (
            "Statistics",
            {
                "fields": ("views", "likes", "track_count", "date_added"),
                "description": "The cover preview uses the artwork of the first track in the album.",
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("genres", "tracks__artist")
            .annotate(_tracks=Count("tracks", distinct=True))
        )

    @admin.display(description="Cover")
    def cover_preview(self, obj):
        first_track = next(iter(obj.tracks.all()), None)
        return thumbnail(first_track.cover) if first_track else mark_safe(EMPTY_THUMB)

    @admin.display(description="Artists")
    def artist_names(self, obj):
        names = sorted({str(track.artist) for track in obj.tracks.all() if track.artist_id})
        return ", ".join(names) or mark_safe("&ndash;")

    @admin.display(description="Tracks", ordering="_tracks")
    def track_count(self, obj):
        return obj._tracks

    @admin.display(description="Genres")
    def genres_list(self, obj):
        return object_links(obj.genres)


# --------------------------------------------------------------------------- #
# Playlist
# --------------------------------------------------------------------------- #

@admin.register(Playlist)
class PlaylistAdmin(PreviewMediaMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "cover_preview",
        "track_count",
        "audio_coverage",
        "genres_list",
        "views",
        "likes",
        "date_updated",
    )
    list_display_links = ("name",)
    list_filter = ("genres", "date_updated")
    search_fields = ("name", "description", "tracks__title", "tracks__artist__name")
    date_hierarchy = "date_added"
    ordering = ("-date_updated",)
    readonly_fields = ("cover_preview", "track_count", "date_added", "date_updated")
    inlines = [PlaylistTrackRelationInline]
    list_per_page = 30
    save_on_top = True
    fieldsets = (
        (None, {"fields": ("name", "cover_preview", "genres")}),
        ("Description", {"fields": ("description",)}),
        (
            "Statistics",
            {"fields": ("views", "likes", "track_count", "date_added", "date_updated")},
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("genres", "tracks", "trackr")
            .annotate(_tracks=Count("tracks", distinct=True))
        )

    @admin.display(description="Cover")
    def cover_preview(self, obj):
        # Position 1 is the cover the public playlist page uses.
        relation = next((rel for rel in obj.trackr.all() if rel.order == 1), None)
        if relation and relation.track_id:
            return thumbnail(relation.track.cover)
        first_track = next(iter(obj.tracks.all()), None)
        return thumbnail(first_track.cover) if first_track else mark_safe(EMPTY_THUMB)

    @admin.display(description="Tracks", ordering="_tracks")
    def track_count(self, obj):
        return obj._tracks

    @admin.display(description="Audio uploaded")
    def audio_coverage(self, obj):
        tracks = list(obj.tracks.all())
        if not tracks:
            return mark_safe("&ndash;")
        with_audio = sum(1 for track in tracks if track.audio_file)
        return format_html("{} / {}", with_audio, len(tracks))

    @admin.display(description="Genres")
    def genres_list(self, obj):
        return object_links(obj.genres)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Keep the playback order gap-free after tracks are added or removed.
        relations = list(form.instance.trackr.order_by("order", "pk"))
        for index, relation in enumerate(relations, start=1):
            if relation.order != index:
                relation.order = index
                relation.save(update_fields=["order"])


# --------------------------------------------------------------------------- #
# Track
# --------------------------------------------------------------------------- #

class HasAudioFilter(admin.SimpleListFilter):
    title = "audio file"
    parameter_name = "has_audio"

    def lookups(self, request, model_admin):
        return (("yes", "Uploaded"), ("no", "Missing"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(audio_file="")
        if self.value() == "no":
            return queryset.filter(audio_file="")
        return queryset


@admin.action(description="Flag selected tracks as having lyrics")
def mark_lyrics_available(modeladmin, request, queryset):
    updated = queryset.update(has_lyrics=True)
    modeladmin.message_user(request, f"{updated} track(s) flagged as having lyrics.")


@admin.action(description="Flag selected tracks as having no lyrics")
def mark_lyrics_missing(modeladmin, request, queryset):
    updated = queryset.update(has_lyrics=False)
    modeladmin.message_user(request, f"{updated} track(s) flagged as having no lyrics.")


@admin.register(Track)
class TrackAdmin(PreviewMediaMixin, admin.ModelAdmin):
    list_display = (
        "cover_preview",
        "title",
        "artist_link",
        "featured_list",
        "genre_list",
        "has_lyrics",
        "has_audio",
        "views",
        "likes",
        "release_date",
        "date_added",
    )
    list_display_links = ("title",)
    list_filter = ("has_lyrics", HasAudioFilter, "genres", "artist", "release_date")
    search_fields = ("title", "artist__name", "featured_artist__name", "lyrics", "description")
    date_hierarchy = "date_added"
    ordering = ("-date_added",)
    list_select_related = ("artist",)
    autocomplete_fields = ("artist", "featured_artist")
    filter_horizontal = ("genres",)
    readonly_fields = (
        "cover_preview",
        "audio_preview",
        "performing_artists",
        "views",
        "likes",
        "date_added",
    )
    inlines = [TrackAlbumRelationInline, TrackPlaylistRelationInline]
    actions = [mark_lyrics_available, mark_lyrics_missing]
    list_per_page = 30
    save_on_top = True
    fieldsets = (
        (
            None,
            {
                "fields": ("title", "artist", "featured_artist", "performing_artists", "genres"),
                "description": "Artist fields use search boxes - type a few letters instead of scrolling a list.",
            },
        ),
        ("Artwork & audio", {"fields": ("cover", "cover_preview", "audio_file", "audio_preview")}),
        ("Lyrics", {"fields": ("has_lyrics", "lyrics"), "classes": ("collapse",)}),
        ("Release details", {"fields": ("description", "release_date")}),
        ("Statistics", {"fields": ("views", "likes", "date_added"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("artist")
            .prefetch_related("genres", "featured_artist")
        )

    @admin.display(description="Cover")
    def cover_preview(self, obj):
        return thumbnail(obj.cover)

    @admin.display(description="Audio preview")
    def audio_preview(self, obj):
        return audio_player(obj.audio_file)

    @admin.display(description="Artist", ordering="artist__name")
    def artist_link(self, obj):
        return related_change_link(obj.artist) if obj.artist_id else mark_safe("&ndash;")

    @admin.display(description="Featured")
    def featured_list(self, obj):
        return object_links(obj.featured_artist)

    @admin.display(description="Genres")
    def genre_list(self, obj):
        return object_links(obj.genres)

    @admin.display(description="Performing artists")
    def performing_artists(self, obj):
        if obj.pk is None:
            return "Save the track first to see the combined credit."
        return obj.clean_artists()

    @admin.display(boolean=True, description="Audio")
    def has_audio(self, obj):
        return bool(obj.audio_file)


# --------------------------------------------------------------------------- #
# Feedback
# --------------------------------------------------------------------------- #

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "short_description", "reply_link")
    list_display_links = ("name",)
    search_fields = ("name", "email", "description")
    ordering = ("name",)
    readonly_fields = ("reply_link",)
    list_per_page = 30
    fieldsets = (
        (None, {"fields": ("name", "email", "reply_link")}),
        ("Message", {"fields": ("description",)}),
    )

    @admin.display(description="Message")
    def short_description(self, obj):
        text = (obj.description or "").strip().replace("\n", " ")
        return (text[:70] + "...") if len(text) > 70 else text

    @admin.display(description="Reply")
    def reply_link(self, obj):
        if not obj.email:
            return mark_safe("&ndash;")
        return format_html(
            '<a href="mailto:{}?subject={}">Reply by email</a>', obj.email, "Re: your message"
        )


# --------------------------------------------------------------------------- #
# Relation models stay registered so they remain searchable, even though the
# inlines above are the normal way to edit them.
# --------------------------------------------------------------------------- #

@admin.register(Album_track_relation)
class AlbumTrackRelationAdmin(admin.ModelAdmin):
    list_display = ("album", "order", "track")
    list_filter = ("album",)
    search_fields = ("album__name", "track__title")
    autocomplete_fields = ("album", "track")
    ordering = ("album", "order")


@admin.register(Playlist_track_relation)
class PlaylistTrackRelationAdmin(admin.ModelAdmin):
    list_display = ("playlist", "order", "track")
    list_filter = ("playlist",)
    search_fields = ("playlist__name", "track__title")
    autocomplete_fields = ("playlist", "track")
    ordering = ("playlist", "order")


# --------------------------------------------------------------------------- #
# Dashboard data for the admin index page (templates/admin/index.html)
# --------------------------------------------------------------------------- #

def _changelist_url(model):
    return reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")


def _dashboard_context():
    cards = [
        {"label": "Tracks", "value": Track.objects.count(), "url": _changelist_url(Track)},
        {"label": "Artists", "value": Artist.objects.count(), "url": _changelist_url(Artist)},
        {"label": "Albums", "value": Album.objects.count(), "url": _changelist_url(Album)},
        {"label": "Playlists", "value": Playlist.objects.count(), "url": _changelist_url(Playlist)},
        {"label": "Genres", "value": Genre.objects.count(), "url": _changelist_url(Genre)},
        {"label": "Feedback", "value": Feedback.objects.count(), "url": _changelist_url(Feedback)},
        {"label": "Users", "value": User.objects.count(), "url": _changelist_url(User)},
        {"label": "Groups", "value": Group.objects.count(), "url": _changelist_url(Group)},
    ]

    recent = []
    for model, kind in ((Track, "Track"), (Album, "Album"), (Playlist, "Playlist")):
        for obj in model.objects.order_by("-date_added")[:3]:
            recent.append(
                {
                    "kind": kind,
                    "name": str(obj),
                    "url": reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_change", args=[obj.pk]),
                    "date": obj.date_added,
                }
            )
    recent.sort(key=lambda item: item["date"], reverse=True)

    checks = [
        {
            "label": "Tracks with no cover (still using the default artwork)",
            "count": Track.objects.filter(cover="default-cover.png").count(),
            "url": _changelist_url(Track),
        },
        {
            "label": "Tracks with no audio file uploaded",
            "count": Track.objects.filter(audio_file="").count(),
            "url": f"{_changelist_url(Track)}?has_audio=no",
        },
        {
            "label": "Tracks flagged as having lyrics but with empty lyrics",
            "count": Track.objects.filter(has_lyrics=True, lyrics="").count(),
            "url": f"{_changelist_url(Track)}?has_lyrics__exact=1",
        },
        {
            "label": "Tracks with no lyrics",
            "count": Track.objects.filter(has_lyrics=False).count(),
            "url": f"{_changelist_url(Track)}?has_lyrics__exact=0",
        },
        {
            "label": "Tracks with no artist set",
            "count": Track.objects.filter(artist__isnull=True).count(),
            "url": f"{_changelist_url(Track)}?artist__isnull=True",
        },
        {
            "label": "Tracks not part of any album or playlist",
            "count": Track.objects.filter(albumr__isnull=True, playlistr__isnull=True).count(),
            "url": _changelist_url(Track),
        },
        {
            "label": "Artists with no photo (still using the default image)",
            "count": Artist.objects.filter(photo="default-artist.png").count(),
            "url": _changelist_url(Artist),
        },
        {
            "label": "Albums with no tracks",
            "count": Album.objects.filter(albumr__isnull=True).count(),
            "url": _changelist_url(Album),
        },
        {
            "label": "Playlists with no tracks",
            "count": Playlist.objects.filter(trackr__isnull=True).count(),
            "url": _changelist_url(Playlist),
        },
    ]

    top_tracks = [
        {
            "name": track.title,
            "url": reverse("admin:Core_track_change", args=[track.pk]),
            "views": track.views,
            "likes": track.likes,
        }
        for track in Track.objects.order_by("-views")[:5]
    ]
    top_artists = [
        {
            "name": artist.name,
            "url": reverse("admin:Core_artist_change", args=[artist.pk]),
            "views": artist.views,
            "likes": artist.likes,
        }
        for artist in Artist.objects.order_by("-views")[:5]
    ]

    return {
        "cards": cards,
        "recent": recent[:8],
        "checks": checks,
        "top_tracks": top_tracks,
        "top_artists": top_artists,
    }


def _install_dashboard_context():
    """Attach the dashboard to the site the project URLconf actually serves.

    ``me3ulandsang/urls.py`` wires up ``admin.site``, so instead of replacing the
    default site (which would leave the old one handling /admin/) the dashboard
    hook is wrapped onto that same site. The statistics are wrapped in a lazy
    object so the queries only run on pages that actually read ``dashboard``
    (the index) and never while opening a change form.
    """
    site = admin.site
    if getattr(site, "_dashboard_installed", False):
        return site

    original_each_context = site.each_context

    def each_context(request):
        context = original_each_context(request)
        context["dashboard"] = SimpleLazyObject(_safe_dashboard_context)
        return context

    site.each_context = each_context
    site._dashboard_installed = True
    return site


def _safe_dashboard_context():
    """Dashboard statistics, or None if anything goes wrong.

    A broken statistic must never stop the operator from reaching the catalogue.
    """
    try:
        return _dashboard_context()
    except Exception:  # pragma: no cover - defensive: the admin must keep working
        logger.exception("Could not build the admin dashboard")
        return None


_install_dashboard_context()
