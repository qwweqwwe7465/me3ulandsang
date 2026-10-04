from django.shortcuts import render ,get_object_or_404, redirect
from .models import Track , Artist , Genre, Album, Album_track_relation , Playlist , Genre
from .forms import FeedbackForm, TrackForm
from django.db.models import Count, Sum, Q
from django.http import JsonResponse , HttpResponse
import tempfile
import os
import re
import base64
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3
from django.contrib.auth.decorators import login_required

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


@login_required
def track_add_view(request):
    
    if request.method == 'POST':
        form = TrackForm(request.POST, request.FILES)
        if form.is_valid():
            track = form.save()

            album_id = request.POST.get('album')
            album_order = request.POST.get('album_order')
            if album_id:
                Album_track_relation.objects.create(
                    album_id=album_id,
                    track=track,
                    order=album_order or 0,
                )

            return redirect('single_track_view', tid=track.id)
    else:
        form = TrackForm()

    if request.method == 'POST':
        initial_artist_id = request.POST.get('artist', '')
        initial_album_id = request.POST.get('album', '')
        initial_album_order = request.POST.get('album_order', '')
        initial_featured_ids = ",".join(request.POST.getlist('featured_artist'))
        selected_genre_ids = {int(g) for g in request.POST.getlist('genres') if g.isdigit()}
    else:
        initial_artist_id = ''
        initial_album_id = ''
        initial_album_order = ''
        initial_featured_ids = ''
        selected_genre_ids = set()

    context = {
        'form': form,
        'initial_artist_id': initial_artist_id,
        'initial_album_id': initial_album_id,
        'initial_album_order': initial_album_order,
        'initial_featured_ids': initial_featured_ids,
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
    
    relations=album.albumr.select_related("track").order_by("order")
    context = {'album': album,'relations':relations}
    return render(request,'album.html',context)

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
    tracks = Track.objects.filter(Q(artist=artist) | Q(featured_artist=artist)).distinct()
    top_tracks = tracks.order_by('-likes')[:5]
    albums = Album.objects.filter(albumr__track__in=tracks).distinct().order_by('-release_date')
    total_views = tracks.aggregate(total=Sum('views'))['total'] or 0
    context = {
        'artist': artist,
        'top_tracks': top_tracks,
        'albums': albums,
        'track_count': tracks.count(),
        'album_count': albums.count(),
        'total_views': total_views,
    }
    return render(request,'artist.html',context)
