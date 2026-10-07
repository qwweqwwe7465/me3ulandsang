"""Seed a handful of test tracks by posting to the real add-track view."""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "me3ulandsang.setting.dev")

import django

django.setup()

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3

from Core.models import Album, Artist, Genre, Track

LIBRARY = r"A:\Liberary"

# (filename, genre)
SELECTION = [
    ("01 Muse - Time Is Running Out.mp3", "Alternative Rock"),
    ("03 Type O Negative - Love You to Death.mp3", "Gothic Metal"),
    ("1 1 - Deftones - My Own Summer (Shove It) (320).mp3", "Alternative Metal"),
    ("06 Dream Theater - Never Enough.mp3", "Progressive Metal"),
    ("07 TOOL - Parabola.mp3", "Progressive Metal"),
    ("07 Ending Credits.mp3", "Progressive Metal"),
    ("02 Azadi.mp3", "Hip-Hop"),
    ("1 1 - Bernth - Waterworks (320).mp3", "Instrumental Rock"),
]

JUNK = ("[musicmim.com]", "[ www.Just-Music.ir ]")


def clean(value):
    value = value.strip()
    for junk in JUNK:
        value = value.replace(junk, "")
    return value.strip(" -")


def index_library():
    found = {}
    for dirpath, _dirnames, filenames in os.walk(LIBRARY):
        for name in filenames:
            found.setdefault(name, os.path.join(dirpath, name))
    return found


def read_tags(path):
    audio = EasyID3(path)
    tags = {key: audio.get(key, [""])[0].strip() for key in ("title", "artist", "album", "date", "tracknumber")}

    raw = ID3(path)
    lyrics = ""
    for frame in raw.getall("USLT"):
        lyrics = str(frame.text)
        break

    cover = None
    covers = raw.getall("APIC")
    if covers:
        picture = covers[0]
        extension = (picture.mime or "image/jpeg").split("/")[-1]
        cover = (picture.data, picture.mime or "image/jpeg", "cover." + extension)

    return tags, lyrics, cover


def main():
    library = index_library()
    missing = [name for name, _genre in SELECTION if name not in library]
    if missing:
        print("missing from library:")
        for name in missing:
            print("  ", name)
        return 1

    user = User.objects.filter(is_superuser=True).first()
    if user is None:
        print("no superuser to log in as")
        return 1

    client = Client()
    client.force_login(user)
    add_url = reverse("track_add_view")

    for filename, genre_name in SELECTION:
        path = library[filename]
        tags, lyrics, cover = read_tags(path)

        title = clean(tags["title"]) or os.path.splitext(filename)[0]
        artist_name = clean(tags["artist"]) or "Unknown Artist"
        album_name = clean(tags["album"])
        year = tags["date"][:4]
        order = tags["tracknumber"].split("/")[0].strip()

        if cover is None:
            print(f"skip (no embedded cover): {filename}")
            continue

        genre, _ = Genre.objects.get_or_create(name=genre_name)

        artist, created_artist = Artist.objects.get_or_create(name=artist_name)
        if created_artist:
            artist.description = f"{artist_name} — seeded for testing."
            artist.save()
        artist.genres.add(genre)

        album = None
        if album_name:
            album, created_album = Album.objects.get_or_create(name=album_name)
            if created_album:
                album.description = f"{album_name} — seeded for testing."
                if year.isdigit():
                    album.release_date = timezone.make_aware(datetime.fromisoformat(f"{year}-01-01"))
                album.save()
                album.genres.add(genre)

        with open(path, "rb") as handle:
            audio_bytes = handle.read()

        data = {
            "action": "save",
            "title": title[:50],
            "artist": str(artist.id),
            "genres": [str(genre.id)],
            "description": f"From the album {album_name}." if album_name else "",
            "lyrics": lyrics,
        }
        if year:
            data["release_date"] = f"{year}-01-01"
        if lyrics.strip():
            data["has_lyrics"] = "on"
        if album is not None:
            data["album"] = str(album.id)
            if order.isdigit():
                data["album_order"] = order

        files = {
            "audio_file": SimpleUploadedFile(filename, audio_bytes, content_type="audio/mpeg"),
            "cover": SimpleUploadedFile(cover[2], cover[0], content_type=cover[1]),
        }
        data.update(files)

        response = client.post(add_url, data, SERVER_NAME="localhost")

        track = Track.objects.filter(title=title[:50]).first()
        status = "OK" if response.status_code == 302 and track else f"FAILED ({response.status_code})"
        print(f"{status:12} {title} :: {artist_name} :: {genre_name} :: lyrics={'yes' if lyrics.strip() else 'no'} :: album={album_name or '-'}")

    print()
    print("tracks", Track.objects.count(), "artists", Artist.objects.count(), "genres", Genre.objects.count(), "albums", Album.objects.count())
    return 0


if __name__ == "__main__":
    sys.exit(main())
