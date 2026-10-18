from django.shortcuts import render ,get_object_or_404, redirect
from .models import Track , Artist , Genre, Album, Album_track_relation , Playlist , Genre
from .forms import FeedbackForm, TrackForm
from django.db.models import Count, Max, Sum, Q
from django.http import JsonResponse , HttpResponse
import logging
import json
import tempfile
import os
import re
import time
import base64
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .artist_photos import attach_photo, has_real_photo

logger = logging.getLogger(__name__)

# Total time the upload page may spend fetching photos for newly created
# artists, so a slow network cannot stall the save. Each artist may use up to
# 12s of it (6s per source), and later artists share whatever is left.
PHOTO_FETCH_BUDGET = 16

def index_view(request):
    tracks = Track.objects.all()
    toptracks = tracks.order_by('-likes')[:10]
    agotracks = Track.objects.all().order_by('-date_added')[:10]
    artists = Artist.objects.all()
    genres = Genre.objects.annotate(track_count=Count('rel_track')).order_by('-track_count', 'name')
    playlists=Playlist.objects.order_by('likes')[:4]
    playlist_count=Playlist.objects.all().count()
    lyrcount=tracks.filter(has_lyrics=True).count
    context={'tracks':tracks,'toptracks':toptracks,'artist':artists,'genres':genres,'agotracks':agotracks,'playlists':playlists,'playlist_count':playlist_count,'lyrcount':lyrcount}
    return render (request,'index.html',context)

def search_view(request):
    
    query = request.GET.get('s', '').strip()
    current_type = request.GET.get('type', 'all')
    genre_query= request.GET.get('genre', '').strip()
    genres=Genre.objects.all()
    if query:
        tracks = Track.objects.filter(
            Q(title__icontains=query) |
            Q(artist__name__icontains=query) |
            Q(featured_artist__name__icontains=query)
        ).distinct()
        artists = Artist.objects.filter(name__icontains=query)
        albums = Album.objects.filter(name__icontains=query)
        playlists = Playlist.objects.filter(name__icontains=query)
    else:
        tracks = Track.objects.all()
        artists = Artist.objects.all()
        albums = Album.objects.all()
        playlists = Playlist.objects.all()

    tracks = tracks.select_related('artist').prefetch_related('featured_artist')
    albums = albums.prefetch_related('tracks')
    playlists = playlists.prefetch_related('tracks')
    artists = artists.annotate(
        track_count=Count('tracks', distinct=True) + Count('featured_tracks', distinct=True)
    )

    if genre_query :
        tracks=tracks.filter(genres__name=genre_query)
        artists=artists.filter(genres__name=genre_query)
        albums=albums.filter(genres__name=genre_query)
        playlists=playlists.filter(genres__name=genre_query)

    tracks = tracks.distinct()
    artists = artists.distinct()
    albums = albums.distinct()
    playlists = playlists.distinct()

    if current_type == 'tracks':
        result_count = tracks.count()
    elif current_type == 'albums':
        result_count = albums.count()
    elif current_type == 'playlists':
        result_count = playlists.count()
    elif current_type == 'artists':
        result_count = artists.count()
    else:
        result_count = tracks.count() + albums.count() + playlists.count() + artists.count()

    top_artists = Artist.objects.annotate(
        track_count=Count('tracks', distinct=True)
    ).order_by('-track_count')[:5]
    top_songs = Track.objects.select_related('artist').order_by('-views')[:5]

    context = {
        'genres': genres,
        'tracks': tracks,
        'artists': artists,
        'albums': albums,
        'req_text': query,
        'current_type': current_type,
        'result_count': result_count,
        'top_artists': top_artists,
        'top_songs': top_songs,
        'playlists':playlists,
    }
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            form.save()
        
    return render(request, 'search.html', context)

def single_track_view(request,tid):
    track = get_object_or_404(
        Track.objects.select_related('artist').prefetch_related('featured_artist'),
        id=tid,
    )

    viewed_tracks = request.session.get('viewed_tracks', [])
    if tid not in viewed_tracks:
        track.views += 1
        track.save(update_fields=['views'])
        viewed_tracks.append(tid)
        request.session['viewed_tracks'] = viewed_tracks

    liked_tracks = request.session.get('liked_tracks', [])
    is_liked = tid in liked_tracks

    album_relation = Album_track_relation.objects.select_related('album').filter(track=track).first()
    album = album_relation.album if album_relation else None
    album_tracks = []
    if album:
        album_tracks = (
            Album_track_relation.objects
            .select_related('track', 'track__artist')
            .filter(album=album)
            .order_by('order')
        )

    context = {
        'track': track,
        'album': album,
        'album_relation': album_relation,
        'album_tracks': album_tracks,
        'is_liked': is_liked,
    }
    return render(request,'single_track.html',context)

def like_track_view(request, tid):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    track = get_object_or_404(Track, id=tid)

    liked_tracks = request.session.get('liked_tracks', [])
    if tid in liked_tracks:
        liked_tracks.remove(tid)
        track.likes = max(track.likes - 1, 0)
        liked = False
    else:
        liked_tracks.append(tid)
        track.likes += 1
        liked = True
    track.save(update_fields=['likes'])
    request.session['liked_tracks'] = liked_tracks

    return JsonResponse({'liked': liked, 'likes': track.likes})

def about_view(request):
    submitted = False
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            form.save()
            submitted = True
            form = FeedbackForm()
    else:
        form = FeedbackForm()

    context = {
        'form': form,
        'submitted': submitted,
        'songs_count': Track.objects.count(),
        'playlists_count': Playlist.objects.count(),
        'lyrics_count': Track.objects.filter(has_lyrics=True).count(),
        'genres_count': Genre.objects.count(),
    }
    return render(request, 'about.html', context)

def test_view(request):
    album = Album.objects.get(id=1)
    relations=album.albumr.select_related("track").order_by("order")
    context = {'relations': relations}
    return render(request, 'test.html', context)


def _resolve_artist(post):
    """Return (artist, created) for the typed name, or (None, False).

    The combo box posts the id of an existing artist in ``artist``. When the
    user typed a name that does not exist, it posts the text in ``artist_name``
    instead, and the artist is created here so the form validates normally.
    """
    artist_id = (post.get('artist') or '').strip()
    if artist_id.isdigit():
        artist = Artist.objects.filter(pk=artist_id).first()
        if artist is not None:
            return artist, False

    name = (post.get('artist_name') or '').strip()
    if not name:
        return None, False

    artist = Artist.objects.filter(name__iexact=name).first()
    if artist is not None:
        return artist, False

    return Artist.objects.create(name=name), True


def _resolve_featured_artists(post, exclude_id=None):
    """Create any featured artist names that do not exist yet.

    The featured combo posts existing ids in ``featured_artist`` and typed-but-
    missing names in ``featured_artist_name``. Returns the full id list plus the
    artists that were newly created, so their photos can be fetched.
    """
    ids = [value for value in post.getlist('featured_artist') if str(value).isdigit()]
    new_artists = []
    seen_names = set()

    for raw_name in post.getlist('featured_artist_name'):
        name = (raw_name or '').strip()
        if not name or name.casefold() in seen_names:
            continue
        seen_names.add(name.casefold())

        artist = Artist.objects.filter(name__iexact=name).first()
        if artist is None:
            artist = Artist.objects.create(name=name)
            new_artists.append(artist)
        if str(artist.pk) in ids:
            continue
        if exclude_id is not None and artist.pk == exclude_id:
            continue
        ids.append(str(artist.pk))

    return ids, new_artists


def _resolve_album(post, track):
    """Return the album to attach ``track`` to, creating it if the name is new."""
    album_id = (post.get('album') or '').strip()
    if album_id.isdigit():
        album = Album.objects.filter(pk=album_id).first()
        if album is not None:
            return album, False

    name = (post.get('album_name') or '').strip()
    if not name:
        return None, False

    album = Album.objects.filter(name__iexact=name).first()
    created = False
    if album is None:
        album = Album.objects.create(
            name=name,
            release_date=track.release_date or timezone.now(),
        )
        created = True
        # A brand new album inherits the track's genres so it is browsable
        # straight away.
        album.genres.set(track.genres.all())
    return album, created


@login_required
def track_add_view(request):
    new_artists = []

    if request.method == 'POST':
        # Copy because QueryDict is immutable and the artists have to be resolved
        # into ids before the form validates.
        post = request.POST.copy()
        artist, artist_created = _resolve_artist(post)
        if artist is not None:
            post['artist'] = str(artist.pk)
            if artist_created:
                new_artists.append(artist)

        featured_ids, featured_created = _resolve_featured_artists(
            post, exclude_id=artist.pk if artist is not None else None
        )
        if featured_ids:
            post.setlist('featured_artist', featured_ids)
        new_artists.extend(featured_created)

        form = TrackForm(post, request.FILES)
        if form.is_valid():
            track = form.save()

            # Give a face to every artist on this track who has none yet. That
            # includes existing artists whose earlier fetch failed: otherwise a
            # re-upload would never retry them. A failed lookup keeps the default
            # image and the upload carries on, and the batch shares a time budget
            # so saving never hangs.
            candidates = [*new_artists]
            if track.artist_id:
                candidates.append(track.artist)
            candidates.extend(track.featured_artist.all())

            to_fetch = []
            seen_pks = set()
            for candidate in candidates:
                if candidate is None or candidate.pk in seen_pks:
                    continue
                seen_pks.add(candidate.pk)
                if not has_real_photo(candidate):
                    to_fetch.append(candidate)

            if to_fetch:
                logger.info("Fetching photos for %s", ", ".join(a.name for a in to_fetch))
                deadline = time.monotonic() + PHOTO_FETCH_BUDGET
                for candidate in to_fetch[:6]:
                    remaining = deadline - time.monotonic()
                    if remaining < 1:
                        logger.info("Photo budget exhausted; %s keeps the default image", candidate.name)
                        break
                    try:
                        attach_photo(candidate, timeout=min(12, remaining))
                    except Exception:  # noqa: BLE001 - never lose the upload over a photo
                        logger.exception("Could not fetch a photo for %s", candidate.name)

            album, album_created = _resolve_album(post, track)
            if album is not None:
                raw_order = (post.get('album_order') or '').strip()
                if raw_order.isdigit() and int(raw_order) > 0:
                    order = int(raw_order)
                else:
                    # Append to the end of the tracklist when no position is given.
                    highest = (
                        Album_track_relation.objects.filter(album=album)
                        .aggregate(highest=Max('order'))['highest']
                        or 0
                    )
                    order = highest + 1

                relation, relation_created = Album_track_relation.objects.get_or_create(
                    album=album, track=track, defaults={'order': order}
                )
                if not relation_created and relation.order != order:
                    relation.order = order
                    relation.save(update_fields=['order'])

            return redirect('single_track_view', tid=track.id)
    else:
        form = TrackForm()

    if request.method == 'POST':
        initial_artist_id = request.POST.get('artist', '')
        initial_artist_name = request.POST.get('artist_name', '')
        initial_album_id = request.POST.get('album', '')
        initial_album_name = request.POST.get('album_name', '')
        initial_album_order = request.POST.get('album_order', '')
        initial_featured_ids = ",".join(request.POST.getlist('featured_artist'))
        initial_featured_names = json.dumps(
            [name for name in request.POST.getlist('featured_artist_name') if name.strip()]
        )
        selected_genre_ids = {int(g) for g in request.POST.getlist('genres') if g.isdigit()}
    else:
        initial_artist_id = ''
        initial_artist_name = ''
        initial_album_id = ''
        initial_album_name = ''
        initial_album_order = ''
        initial_featured_ids = ''
        initial_featured_names = '[]'
        selected_genre_ids = set()

    context = {
        'form': form,
        'initial_artist_id': initial_artist_id,
        'initial_artist_name': initial_artist_name,
        'initial_album_id': initial_album_id,
        'initial_album_name': initial_album_name,
        'initial_album_order': initial_album_order,
        'initial_featured_ids': initial_featured_ids,
        'initial_featured_names': initial_featured_names,
        'selected_genre_ids': selected_genre_ids,
        'artist_list': list(Artist.objects.order_by('name').values('id', 'name')),
        'album_list': list(Album.objects.order_by('name').values('id', 'name')),
        'genres': Genre.objects.order_by('name'),
    }
    return render(request, 'trackadd.html', context)




def extract_metadata_view(request):
    if request.method == 'POST' and request.FILES.get('audio_file'):
        audio_file = request.FILES['audio_file']

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
            for chunk in audio_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            audio = EasyID3(tmp_path)
            release_date = ''
            raw_date = audio.get('date')
            if raw_date:
                year_match = re.search(r'\d{4}', str(raw_date[0]))
                if year_match:
                    release_date = f'{year_match.group(0)}-01-01'

            track_number = ''
            raw_track = audio.get('tracknumber')
            if raw_track:
                track_number = str(raw_track[0]).split('/')[0].strip()

            data = {
                'title': audio.get('title', [''])[0],
                'artist': audio.get('artist', [''])[0],
                'album': audio.get('album', [''])[0],
                'release_date': release_date,
                'track_number': track_number,
            }

            # lyrics live in a separate raw ID3 frame, not in EasyID3
            id3 = ID3(tmp_path)
            lyrics_text = ''
            for key in id3.keys():
                if key.startswith('USLT'):
                    lyrics_text = id3[key].text
                    break

            data['lyrics'] = lyrics_text
            data['has_lyrics'] = bool(lyrics_text.strip())

            # embedded cover art lives in APIC frames
            data['cover'] = ''
            apic_frames = id3.getall('APIC')
            if apic_frames:
                picture = apic_frames[0]
                encoded = base64.b64encode(picture.data).decode('ascii')
                extension = picture.mime.split('/')[-1] or 'jpg'
                data['cover'] = f'data:{picture.mime};base64,{encoded}'
                data['cover_filename'] = f'cover.{extension}'

        except Exception as e:
            print("Extraction error:", e)
            data = {'error': str(e)}
        finally:
            os.remove(tmp_path)

        return JsonResponse(data)

    return JsonResponse({'error': 'No file provided'}, status=400)





def album_view(request,aid):
    album = get_object_or_404(Album, id=aid)

    viewed_albums = request.session.get('viewed_albums', [])
    if aid not in viewed_albums:
        album.views += 1
        album.save(update_fields=['views'])
        viewed_albums.append(aid)
        request.session['viewed_albums'] = viewed_albums

    liked_albums = request.session.get('liked_albums', [])
    is_liked = aid in liked_albums

    relations=album.albumr.select_related("track").order_by("order")
    context = {'album': album,'relations':relations,'is_liked':is_liked}
    return render(request,'album.html',context)

def like_album_view(request, aid):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    album = get_object_or_404(Album, id=aid)

    liked_albums = request.session.get('liked_albums', [])
    if aid in liked_albums:
        liked_albums.remove(aid)
        album.likes = max(album.likes - 1, 0)
        liked = False
    else:
        liked_albums.append(aid)
        album.likes += 1
        liked = True
    album.save(update_fields=['likes'])
    request.session['liked_albums'] = liked_albums

    return JsonResponse({'liked': liked, 'likes': album.likes})

def playlist_view(request,pid):

    pid = int(pid)
    playlist = get_object_or_404(Playlist, id=pid)

    viewed_playlists = request.session.get('viewed_playlists', [])
    if pid not in viewed_playlists:
        playlist.views += 1
        playlist.save(update_fields=['views'])
        viewed_playlists.append(pid)
        request.session['viewed_playlists'] = viewed_playlists
    liked_playlists = request.session.get('liked_playlists', [])
    is_liked = pid in liked_playlists


    relations=playlist.trackr.select_related("track").order_by("order")
    context = {'playlist': playlist,'relations':relations,'is_liked':is_liked}
    return render(request,'playlist.html', context)

def like_playlist_view(request, pid):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    playlist = get_object_or_404(Playlist, id=pid)

    liked_playlists = request.session.get('liked_playlists', [])
    if pid in liked_playlists:
        liked_playlists.remove(pid)
        playlist.likes = max(playlist.likes - 1, 0)
        liked = False
    else:
        liked_playlists.append(pid)
        playlist.likes += 1
        liked = True
    playlist.save(update_fields=['likes'])
    request.session['liked_playlists'] = liked_playlists

    return JsonResponse({'liked': liked, 'likes': playlist.likes})

def artist_view(request,aid):
    artist = get_object_or_404(Artist, id=aid)

    viewed_artists = request.session.get('viewed_artists', [])
    if aid not in viewed_artists:
        artist.views += 1
        artist.save(update_fields=['views'])
        viewed_artists.append(aid)
        request.session['viewed_artists'] = viewed_artists

    liked_artists = request.session.get('liked_artists', [])
    is_liked = aid in liked_artists

    tracks = Track.objects.filter(Q(artist=artist) | Q(featured_artist=artist)).distinct()
    top_tracks = tracks.order_by('-likes')[:5]
    albums = Album.objects.filter(albumr__track__in=tracks).distinct().order_by('-release_date')
    context = {
        'artist': artist,
        'top_tracks': top_tracks,
        'albums': albums,
        'track_count': tracks.count(),
        'album_count': albums.count(),
        'is_liked': is_liked,
    }
    return render(request,'artist.html',context)

def like_artist_view(request, aid):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    artist = get_object_or_404(Artist, id=aid)

    liked_artists = request.session.get('liked_artists', [])
    if aid in liked_artists:
        liked_artists.remove(aid)
        artist.likes = max(artist.likes - 1, 0)
        liked = False
    else:
        liked_artists.append(aid)
        artist.likes += 1
        liked = True
    artist.save(update_fields=['likes'])
    request.session['liked_artists'] = liked_artists

    return JsonResponse({'liked': liked, 'likes': artist.likes})
