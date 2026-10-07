import os

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3


def scan(root):
    files = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(".mp3"):
                files.append(os.path.join(dirpath, fn))

    print("total mp3 files:", len(files))

    tagged = []
    untagged = 0
    for path in files:
        try:
            audio = EasyID3(path)
        except Exception:
            untagged += 1
            continue

        title = audio.get("title", [""])[0].strip()
        artist = audio.get("artist", [""])[0].strip()
        album = audio.get("album", [""])[0].strip()
        genre = audio.get("genre", [""])[0].strip()
        date = audio.get("date", [""])[0].strip()
        number = audio.get("tracknumber", [""])[0].strip()

        art = False
        lyrics = False
        try:
            raw = ID3(path)
            art = bool(raw.getall("APIC"))
            lyrics = any(key.startswith("USLT") for key in raw.keys())
        except Exception:
            pass

        if title and artist:
            tagged.append(
                (os.path.getsize(path), title, artist, album, genre, date, number, art, lyrics, os.path.basename(path))
            )
        else:
            untagged += 1

    print("readable but missing title/artist:", untagged)
    print("titled candidates:", len(tagged))
    print()

    with_art = [row for row in tagged if row[7]]
    print("candidates that also carry embedded cover art:", len(with_art))
    print()

    for row in sorted(with_art, key=lambda r: r[9])[:40]:
        size, title, artist, album, genre, date, number, art, lyrics, name = row
        print(f"{title} :: {artist} :: album={album or '-'} :: genre={genre or '-'} :: date={date or '-'} :: cover=yes :: lyrics={'yes' if lyrics else 'no'} :: {size // 1024}KB :: {name}")


if __name__ == "__main__":
    scan(r"A:\Liberary")
