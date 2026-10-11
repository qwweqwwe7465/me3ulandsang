"""Scan a local music library into a reviewable manifest.

Phase 1 of the library import. Reads ID3 tags, embedded artwork presence and
lyrics length for every audio file under --library, then writes one JSON
manifest. This command never touches the database, so it is safe to run against
the real library as often as you like.

    python manage.py library_import --scan

Phase 2 (genre classification) fills in the manifest's "genres" fields.
Phase 3 (`--apply`) creates the Genre/Artist/Album/Track rows.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone as django_timezone

from Core.models import Album, Album_track_relation, Artist, Genre, Track
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

AUDIO_EXTENSIONS = {".mp3"}

# The approved closed genre pool. `--apply` refuses any genre outside this list,
# so a typo in the classification map cannot silently create a 24th genre.
APPROVED_GENRES = [
    "Alternative",
    "Black metal",
    "Blues",
    "Death metal",
    "Doom metal",
    "Electronic",
    "Electronic metal",
    "Folk",
    "Gothic metal",
    "Heavy metal",
    "Hip hop",
    "Indie rock",
    "Industrial metal",
    "Neoclassical",
    "Nu metal",
    "Pop",
    "Power metal",
    "Progressive metal",
    "Punk",
    "Rock",
    "Soundtrack",
    "Theatrical",
    "Thrash",
]

# Existing rows renamed in place on first `--apply`, so the 21 live tracks keep
# their genre relations instead of being orphaned.
GENRE_RENAMES = {
    "progressive": "Progressive metal",
    "electrical metal": "Electronic metal",
}

# Download-site junk that ends up inside tags and file names.
JUNK_MARKERS = (
    "[musicmim.com]",
    "[ www.Just-Music.ir ]",
    "www.Just-Music.ir",
    "Just-Music.ir",
    "musicmim.com",
)

# Tags we care about, in the order we try to read them.
TEXT_TAGS = (
    ("title", "TIT2"),
    ("artist", "TPE1"),
    ("albumartist", "TPE2"),
    ("album", "TALB"),
    ("date", "TDRC"),
    ("tracknumber", "TRCK"),
    ("discnumber", "TPOS"),
    ("genre", "TCON"),
)

# "12 - Title - Artist (320).mp3" — by far the dominant style here.
DASH_PATTERN = re.compile(
    r"^(?P<number>\d+)?\s*[-_.]?\s*(?P<left>.+?)\s+[-–]\s+(?P<right>.+?)"
    r"(?:\s*\(\d+\))?\s*$"
)

# "Title   Artist" — a second style, separated by two or more spaces.
SPACE_PATTERN = re.compile(r"^(?P<left>.+?)\s{2,}(?P<right>.+?)(?:\s*\(\d+\))?\s*$")

NUMERIC_ONLY = re.compile(r"^[\d\s._\-]+$")


def clean(value: str) -> str:
    """Strip download-site junk and stray whitespace out of a tag.

    Unicode is folded to NFC first: the library contains "Måneskin" spelt with
    both a precomposed and a combining ring, which would otherwise become two
    separate artist pages.
    """
    text = unicodedata.normalize("NFC", value or "")
    for junk in JUNK_MARKERS:
        text = text.replace(junk, "")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_·.")


def guess_from_filename(stem: str) -> dict:
    """Best-effort title/artist recovery for files whose tags are missing.

    Handles the naming styles actually present in this library:
        "12 - Title - Artist (320)"  -> track 12, title, artist
        "Artist - Title"             -> artist, title
        "Title   Artist"             -> title, artist (two or more spaces)
    Anything ambiguous is left blank rather than guessed wrong.
    """
    text = re.sub(r"\(\d+\)\s*$", "", stem).strip()

    match = DASH_PATTERN.match(text)
    if match:
        number = (match.group("number") or "").strip()
        left = clean(match.group("left"))
        right = clean(match.group("right"))
        if left and right and not NUMERIC_ONLY.match(right):
            guess = {"title": right, "artist": left, "from_filename": True}
            if number:
                guess["tracknumber"] = number
            return guess

    match = SPACE_PATTERN.match(text)
    if match:
        left = clean(match.group("left"))
        right = clean(match.group("right"))
        # A numeric left side is a track number, not a title, so there is
        # nothing usable to recover.
        if left and right and not NUMERIC_ONLY.match(left):
            return {"title": left, "artist": right, "from_filename": True}

    return {}


def read_tags(path: str) -> dict:
    """Read text tags via EasyID3, falling back to raw ID3 frames."""
    tags: dict[str, str] = {}
    genre_values: list[str] = []

    try:
        audio = EasyID3(path)
        for field, _frame in TEXT_TAGS:
            values = audio.get(field) or []
            values = [clean(str(v)) for v in values if str(v).strip()]
            if values:
                tags[field] = values[0]
                if field == "genre":
                    genre_values = values
    except Exception:
        pass

    missing = [field for field, _frame in TEXT_TAGS if not tags.get(field)]
    if missing:
        try:
            raw = ID3(path)
            for field, frame_id in TEXT_TAGS:
                if tags.get(field):
                    continue
                frame = raw.get(frame_id)
                if frame is None:
                    continue
                values = frame.text if isinstance(frame.text, list) else [frame.text]
                values = [clean(str(v)) for v in values if str(v).strip()]
                if values:
                    tags[field] = values[0]
                    if field == "genre" and not genre_values:
                        genre_values = values
        except Exception:
            pass

    tags["genre_all"] = genre_values
    return tags


def read_media_facts(path: str) -> dict:
    """Lyrics length, embedded artwork presence and audio properties."""
    facts = {"has_cover": False, "cover_mime": "", "cover_bytes": 0, "lyrics_chars": 0}
    try:
        duration = MP3(path).info
        facts["duration"] = round(float(duration.length), 1)
        facts["bitrate"] = int(duration.bitrate or 0)
    except Exception:
        facts["duration"] = None
        facts["bitrate"] = 0

    try:
        raw = ID3(path)
        covers = raw.getall("APIC")
        if covers:
            picture = covers[0]
            facts["has_cover"] = True
            facts["cover_mime"] = picture.mime or "image/jpeg"
            facts["cover_bytes"] = len(picture.data or b"")
        for key in raw.keys():
            if key.startswith("USLT"):
                facts["lyrics_chars"] = len(str(raw[key].text or "").strip())
                break
    except Exception:
        pass

    return facts


def read_artwork(path: str):
    """Return (bytes, mime, extension) for the first embedded APIC frame."""
    try:
        raw = ID3(path)
        covers = raw.getall("APIC")
        if covers:
            picture = covers[0]
            mime = picture.mime or "image/jpeg"
            extension = mime.split("/")[-1].lower()
            extension = {"jpeg": "jpg"}.get(extension, extension) or "jpg"
            return picture.data, mime, extension
    except Exception:
        pass
    return None, "", ""


def read_lyrics(path: str) -> str:
    """Return the USLT (unsynchronised lyrics) text, if any."""
    try:
        raw = ID3(path)
        for key in raw.keys():
            if key.startswith("USLT"):
                return str(raw[key].text or "").strip()
    except Exception:
        pass
    return ""


class Command(BaseCommand):
    help = "Scan a music library into a JSON manifest (read-only, no database writes)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scan",
            action="store_true",
            help="Walk --library and write the manifest.",
        )
        parser.add_argument(
            "--worksheet",
            action="store_true",
            help="Write a per-artist genre worksheet from an existing manifest.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Import the manifest in phases: genres, artists, albums, then tracks.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually write to the database and copy files. Without this, --apply is a dry run.",
        )
        parser.add_argument(
            "--no-audio",
            dest="with_audio",
            action="store_false",
            help="Import metadata and artwork only; leave audio_file empty.",
        )
        parser.add_argument(
            "--manifest",
            default=str(Path(settings.BASE_DIR) / "tmp" / "library_manifest.json"),
            help="Manifest to import (default: %(default)s).",
        )
        parser.add_argument(
            "--map",
            default=str(Path(settings.BASE_DIR) / "tmp" / "genre_map.json"),
            help="Genre classification map (default: %(default)s).",
        )
        parser.add_argument(
            "--library",
            default=r"A:\Liberary",
            help="Folder to scan recursively (default: %(default)s).",
        )
        parser.add_argument(
            "--out",
            default=str(Path(settings.BASE_DIR) / "tmp" / "library_manifest.json"),
            help="Manifest path (default: %(default)s).",
        )
        parser.add_argument("--limit", type=int, default=0, help="Stop after N files (for a quick test).")

    def write_worksheet(self, manifest_path: Path):
        """One line per artist, with the hints needed to assign a genre.

        Genre is mostly an artist-level fact, so classifying 273 artists is both
        more consistent and far less work than classifying 743 tracks.
        """
        if not manifest_path.exists():
            raise CommandError(f"Manifest not found: {manifest_path}. Run --scan first.")

        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)

        by_artist: dict[str, dict] = {}
        for track in manifest["tracks"]:
            entry = by_artist.setdefault(track["artist"], {"tracks": [], "albums": set(), "tags": Counter()})
            entry["tracks"].append(track)
            if track["album"]:
                entry["albums"].add(track["album"])
            for tag in track["genre_tag"]:
                entry["tags"][clean(tag)] += 1

        out_path = manifest_path.parent / "genre_worksheet.txt"
        lines = [
            "APPROVED GENRE POOL (assign only from these):",
            ", ".join(APPROVED_GENRES),
            "",
            f"{len(by_artist)} artists covering {len(manifest['tracks'])} tracks",
            "FORMAT: <tracks> :: <artist> :: albums :: library genre tags",
            "",
        ]
        for artist, entry in sorted(by_artist.items(), key=lambda kv: (-len(kv[1]["tracks"]), kv[0].casefold())):
            albums = "; ".join(sorted(entry["albums"])[:4]) or "-"
            tags = "; ".join(tag for tag, _ in entry["tags"].most_common(4)) or "-"
            lines.append(f"{len(entry['tracks']):3} :: {artist} :: {albums} :: {tags}")

        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

        self.stdout.write(f"worksheet {out_path}")
        self.stdout.write(f"artists   {len(by_artist)}")

    def _merge_genre(self, old_name: str, new_name: str) -> int:
        """Rename a genre in place, or merge it into an existing row.

        Relations are moved onto the surviving row before the old row is
        dropped, so tracks already using the old name keep their genres.
        """
        old_rows = list(Genre.objects.filter(name=old_name))
        changed = 0
        for row in old_rows:
            survivor = Genre.objects.filter(name__iexact=new_name).exclude(pk=row.pk).first()
            if survivor is None:
                row.name = new_name
                row.save(update_fields=["name"])
                changed += 1
                continue
            for track in row.rel_track.all():
                track.genres.add(survivor)
            for artist in row.rel_artist.all():
                artist.genres.add(survivor)
            for album in row.rel_album.all():
                album.genres.add(survivor)
            for playlist in row.rel_Playlist.all():
                playlist.genres.add(survivor)
            row.delete()
            changed += 1
        return changed

    def apply_import(self, options):
        """Import the manifest in dependency order.

        Genres, then artists, then albums, then tracks. Artists and albums have
        to exist before any track references them: Track.artist is a foreign
        key, Album_track_relation needs both rows, and the add-track page's
        artist and album pickers only offer what is already in the database.
        """
        commit = options["commit"]
        with_audio = options["with_audio"]
        limit = options["limit"]

        manifest_path = Path(options["manifest"])
        map_path = Path(options["map"])
        if not manifest_path.exists():
            raise CommandError(f"Manifest not found: {manifest_path}. Run --scan first.")
        if not map_path.exists():
            raise CommandError(f"Genre map not found: {map_path}.")

        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        with open(map_path, encoding="utf-8") as handle:
            genre_map = json.load(handle)

        library = Path(manifest["library"])
        pool = set(APPROVED_GENRES)
        aliases = genre_map.get("aliases", {})
        splits = genre_map.get("splits", {})
        artist_genres = genre_map["genres"]
        overrides = genre_map.get("track_genres", {})

        stray = sorted({
            name
            for names in list(artist_genres.values()) + list(overrides.values())
            for name in names
            if name not in pool
        })
        if stray:
            raise CommandError(f"Genre map uses names outside the approved pool: {', '.join(stray)}")

        def resolve_artist(raw):
            if raw in splits:
                primary, featured = splits[raw]
                return primary, list(featured)
            return aliases.get(raw, raw), []

        def resolve_genres(raw_artist, filename):
            if filename in overrides:
                return list(overrides[filename])
            primary, _featured = resolve_artist(raw_artist)
            return list(artist_genres.get(primary) or artist_genres.get(raw_artist) or [])

        records = manifest["tracks"]
        if limit:
            records = records[:limit]

        self.stdout.write(f"mode      {'COMMIT' if commit else 'DRY RUN (pass --commit to write)'}")
        self.stdout.write(f"manifest  {manifest_path}")
        self.stdout.write(f"tracks    {len(records)}")
        self.stdout.write(f"audio     {'copied into media/tracks/' if with_audio else 'skipped (--no-audio)'}")

        # ---- what every artist needs to exist, and with which genres -----
        wanted: dict[str, set] = {}
        for record in records:
            primary, featured = resolve_artist(record["artist"])
            wanted.setdefault(primary, set()).update(resolve_genres(record["artist"], record["file"]))
            for name in featured:
                wanted.setdefault(name, set())

        # ---- phase 1: genres --------------------------------------------
        self.stdout.write("")
        self.stdout.write("phase 1  genres")
        renamed = created_genres = 0
        if commit:
            for old, new in GENRE_RENAMES.items():
                renamed += self._merge_genre(old, new)
            for name in APPROVED_GENRES:
                if not Genre.objects.filter(name__iexact=name).exists():
                    Genre.objects.create(name=name)
                    created_genres += 1
        self.stdout.write(f"  renamed {renamed}, created {created_genres}, pool {len(APPROVED_GENRES)}")

        genre_cache: dict = {}
        if commit:
            for genre in Genre.objects.all():
                genre_cache.setdefault(genre.name.casefold(), genre)

        def genre_for(name):
            key = name.casefold()
            if key in genre_cache:
                return genre_cache[key]
            if not commit:
                return None
            obj = Genre.objects.create(name=name)
            genre_cache[key] = obj
            return obj

        # ---- phase 2: artists (before any track references them) --------
        self.stdout.write("")
        self.stdout.write("phase 2  artists")
        artist_cache: dict = {}
        if commit:
            for obj in Artist.objects.all():
                artist_cache.setdefault(unicodedata.normalize("NFC", obj.name).casefold(), obj)

        artists_created = 0
        for name in sorted(wanted, key=str.casefold):
            key = unicodedata.normalize("NFC", name).casefold()
            if key in artist_cache:
                continue
            if not commit:
                artist_cache[key] = None
                artists_created += 1
                continue
            obj = Artist.objects.create(name=name)
            artist_cache[key] = obj
            artists_created += 1

        if commit:
            for name, names in wanted.items():
                obj = artist_cache.get(unicodedata.normalize("NFC", name).casefold())
                if obj is None:
                    continue
                for genre_name in names:
                    genre = genre_for(genre_name)
                    if genre:
                        obj.genres.add(genre)
        self.stdout.write(f"  created {artists_created}, total {len(wanted)}")

        # ---- phase 3: albums (before any relation references them) ------
        self.stdout.write("")
        self.stdout.write("phase 3  albums")
        album_cache: dict = {}
        if commit:
            for obj in Album.objects.all():
                album_cache.setdefault(unicodedata.normalize("NFC", obj.name).casefold(), obj)

        albums_created = 0
        for record in records:
            album_name = (record.get("album") or "").strip()
            if not album_name:
                continue
            key = unicodedata.normalize("NFC", album_name).casefold()
            if key in album_cache:
                continue
            if not commit:
                album_cache[key] = None
                albums_created += 1
                continue
            obj = Album.objects.create(name=album_name)
            year = (record.get("date") or "")[:4]
            if year.isdigit():
                obj.release_date = django_timezone.make_aware(datetime(int(year), 1, 1))
                obj.save(update_fields=["release_date"])
            album_cache[key] = obj
            albums_created += 1
        self.stdout.write(f"  created {albums_created}")

        # ---- phase 4: tracks --------------------------------------------
        self.stdout.write("")
        self.stdout.write("phase 4  tracks")
        created = already = failed = 0
        covers = with_lyrics = with_audio_count = album_links = 0
        failures: list[tuple[str, str]] = []

        for record in records:
            title = (record["title"] or "").strip()[:50]
            primary, featured = resolve_artist(record["artist"])
            names = resolve_genres(record["artist"], record["file"])

            try:
                if not title:
                    raise ValueError("empty title")
                if not names:
                    raise ValueError("no genre assigned")

                # Idempotent: re-running never duplicates an existing track.
                if Track.objects.filter(title=title, artist__name__iexact=primary).exists():
                    already += 1
                    continue

                if not commit:
                    created += 1
                    continue

                artist_obj = artist_cache.get(unicodedata.normalize("NFC", primary).casefold())
                if artist_obj is None:
                    raise ValueError(f"artist row missing for {primary!r}")

                source = library / record["file"]
                cover_bytes, _cover_mime, cover_ext = read_artwork(str(source))
                lyrics = read_lyrics(str(source))

                with transaction.atomic():
                    track = Track(
                        title=title,
                        artist=artist_obj,
                        has_lyrics=bool(lyrics),
                        lyrics=lyrics,
                        description="",
                    )
                    year = (record.get("date") or "")[:4]
                    if year.isdigit():
                        track.release_date = django_timezone.make_aware(datetime(int(year), 1, 1))

                    if cover_bytes:
                        track.cover.save(f"cover_{uuid4().hex[:7]}.{cover_ext}", ContentFile(cover_bytes), save=False)
                        covers += 1

                    if with_audio and source.exists():
                        with open(source, "rb") as stream:
                            track.audio_file.save(source.name, File(stream), save=False)
                        with_audio_count += 1

                    track.save()

                    for genre_name in names:
                        genre = genre_for(genre_name)
                        if genre:
                            track.genres.add(genre)

                    for featured_name in featured:
                        obj = artist_cache.get(unicodedata.normalize("NFC", featured_name).casefold())
                        if obj:
                            track.featured_artist.add(obj)

                    album_name = (record.get("album") or "").strip()
                    if album_name:
                        album_obj = album_cache.get(unicodedata.normalize("NFC", album_name).casefold())
                        if album_obj is not None:
                            order = (record.get("tracknumber") or "").split("/")[0].strip()
                            Album_track_relation.objects.get_or_create(
                                album=album_obj,
                                track=track,
                                defaults={"order": int(order) if order.isdigit() else 0},
                            )
                            for genre_name in names:
                                genre = genre_for(genre_name)
                                if genre:
                                    album_obj.genres.add(genre)
                            album_links += 1

                if lyrics:
                    with_lyrics += 1
                created += 1
                if created % 100 == 0:
                    self.stdout.write(f"  ... {created} created")

            except Exception as error:
                failed += 1
                failures.append((record["file"], str(error)))

        self.stdout.write("")
        self.stdout.write(f"created        {created}")
        self.stdout.write(f"already there  {already}")
        self.stdout.write(f"failed         {failed}")
        self.stdout.write(f"covers saved   {covers}")
        self.stdout.write(f"audio copied   {with_audio_count}")
        self.stdout.write(f"with lyrics    {with_lyrics}")
        self.stdout.write(f"album links    {album_links}")
        if failures:
            self.stdout.write("")
            self.stdout.write("failures:")
            for path, reason in failures[:20]:
                self.stdout.write(f"  {path} — {reason}")
            if len(failures) > 20:
                self.stdout.write(f"  ... and {len(failures) - 20} more")

        if not commit:
            self.stdout.write("")
            self.stdout.write("dry run — nothing was written. Re-run with --commit to import.")

    def handle(self, *args, **options):
        # The Windows console defaults to cp1252, which cannot encode the
        # non-Latin titles present in this library.
        for stream in (self.stdout, self.stderr):
            try:
                stream._out.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        if options["worksheet"]:
            self.write_worksheet(Path(options["out"]))
            return

        if options["apply"]:
            self.apply_import(options)
            return

        if not options["scan"]:
            raise CommandError("Nothing to do. Pass --scan, --worksheet or --apply.")

        library = Path(options["library"])
        if not library.is_dir():
            raise CommandError(f"Library folder not found: {library}")

        limit = options["limit"]

        tracks: list[dict] = []
        skipped: list[dict] = []
        junk_files: list[str] = []
        seen: dict[tuple[str, str], str] = {}
        duplicates: list[dict] = []
        total_bytes = 0

        for dirpath, dirnames, filenames in os.walk(library):
            dirnames.sort()
            for name in sorted(filenames):
                extension = Path(name).suffix.lower()
                if extension not in AUDIO_EXTENSIONS:
                    junk_files.append(str(Path(dirpath, name).relative_to(library)))
                    continue
                if limit and len(tracks) + len(skipped) >= limit:
                    break

                full = str(Path(dirpath, name))
                relative = str(Path(dirpath, name).relative_to(library))
                size = os.path.getsize(full)
                total_bytes += size

                try:
                    tags = read_tags(full)
                except Exception as error:  # pragma: no cover - defensive
                    skipped.append({"file": relative, "reason": f"unreadable tags: {error}"})
                    continue

                record: dict = {
                    "file": relative,
                    "size": size,
                    "title": tags.get("title", ""),
                    "artist": tags.get("artist", ""),
                    "albumartist": tags.get("albumartist", ""),
                    "album": tags.get("album", ""),
                    "date": tags.get("date", ""),
                    "tracknumber": tags.get("tracknumber", ""),
                    "discnumber": tags.get("discnumber", ""),
                    "genre_tag": tags.get("genre_all", []),
                    "title_source": "tag" if tags.get("title") else "",
                    "artist_source": "tag" if tags.get("artist") else "",
                }

                if not record["title"] or not record["artist"]:
                    guess = guess_from_filename(Path(name).stem)
                    if not record["title"] and guess.get("title"):
                        record["title"] = guess["title"]
                        record["title_source"] = "filename"
                    if not record["artist"] and guess.get("artist"):
                        record["artist"] = guess["artist"]
                        record["artist_source"] = "filename"
                    if not record["tracknumber"] and guess.get("tracknumber"):
                        record["tracknumber"] = guess["tracknumber"]

                record.update(read_media_facts(full))

                problems = []
                if not record["title"]:
                    problems.append("no title tag")
                if not record["artist"]:
                    problems.append("no artist tag")
                if not record["has_cover"]:
                    problems.append("no embedded cover")

                if problems:
                    record["reason"] = "; ".join(problems)
                    skipped.append(record)
                    continue

                key = (record["artist"].casefold(), record["title"].casefold())
                if key in seen:
                    duplicates.append(
                        {"file": relative, "duplicate_of": seen[key], "artist": record["artist"], "title": record["title"]}
                    )
                else:
                    seen[key] = relative

                tracks.append(record)

        tracks.sort(key=lambda r: (r["artist"].casefold(), r["album"].casefold(), r["tracknumber"].zfill(3)))

        manifest = {
            "library": str(library),
            "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "genres_on_site": sorted(Genre.objects.values_list("name", flat=True)),
            "counts": {
                "importable": len(tracks),
                "skipped": len(skipped),
                "non_audio": len(junk_files),
                "duplicate_candidates": len(duplicates),
                "library_bytes": total_bytes,
            },
            "tracks": tracks,
            "skipped": skipped,
            "duplicate_candidates": duplicates,
            "non_audio_files": junk_files,
        }

        out_path = Path(options["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=1)

        self.stdout.write("")
        self.stdout.write(f"library        {library}")
        self.stdout.write(f"importable     {len(tracks)}")
        self.stdout.write(f"skipped        {len(skipped)}")
        self.stdout.write(f"non-audio      {len(junk_files)}")
        self.stdout.write(f"dup candidates {len(duplicates)}")
        self.stdout.write(f"total size     {total_bytes / 1024 / 1024 / 1024:.2f} GB")
        self.stdout.write(f"manifest       {out_path}")

        reasons = Counter(item.get("reason", "?") for item in skipped)
        if reasons:
            self.stdout.write("")
            self.stdout.write("skip reasons:")
            for reason, count in reasons.most_common():
                self.stdout.write(f"  {count:4}  {reason}")

        tag_counter = Counter(tag for record in tracks for tag in record["genre_tag"])
        if tag_counter:
            self.stdout.write("")
            self.stdout.write(f"genre tags found in the library ({len(tag_counter)} distinct):")
            for tag, count in tag_counter.most_common(40):
                self.stdout.write(f"  {count:4}  {tag}")

        artists = Counter(record["artist"] for record in tracks)
        self.stdout.write("")
        self.stdout.write(f"distinct artists: {len(artists)}")
        self.stdout.write(f"distinct albums:  {len({r['album'] for r in tracks if r['album']})}")
