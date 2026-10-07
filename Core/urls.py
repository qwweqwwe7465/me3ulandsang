from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from .views import (
    about_view,
    like_album_view,
    album_view,
    like_artist_view,
    artist_view,
    extract_metadata_view,
    index_view,
    like_playlist_view,
    like_track_view,
    playlist_view,
    search_view,
    single_track_view,
    test_view,
    track_add_view,
)



urlpatterns = [
        path('',index_view,name='index_view'),
        path('search',search_view,name='search_view'),
        path('about',about_view,name='about_view'),
        path('track/<int:tid>',single_track_view,name='single_track_view'),
        path('track/<int:tid>/like',like_track_view,name='like_track_view'),
        path('test',test_view,name='test'),
        path('trackadd',track_add_view,name='track_add_view'),
        path('album/<int:aid>',album_view,name='album_view'),
        path('album/<int:aid>/like', like_album_view, name='like_album_view'),
        path('playlist/<int:pid>',playlist_view,name='playlist_view'),
        path('extract-metadata/', extract_metadata_view, name='extract_metadata'),
        path('artist/<int:aid>',artist_view,name='artist_view'),
        path('artist/<int:aid>/like', like_artist_view, name='like_artist_view'),
        path('playlist/<int:pid>/like', like_playlist_view, name='like_playlist_view'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


