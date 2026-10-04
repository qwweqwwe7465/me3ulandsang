from django.contrib import admin
from django.contrib.auth.models import User
from .models import *




# class PostAdmin(admin.ModelAdmin):
#     date_hierarchy='created_date'
#     list_display= ('title','counted_views','published_date','status',)
#     list_filter=('status',)
#     ordering=['created_date']
#     search_fields=['content','title']
# admin.site.register(Post,PostAdmin)
# admin.site.register(Contact)
# admin.site.register(Category)

class Trackadmin(admin.ModelAdmin):
    readonly_fields = ("date_added",)
    list_display = ('title','views','likes','artist','has_lyrics',"date_added")


admin.site.register(Genre)
admin.site.register(Artist)

admin.site.register(Album_track_relation)
admin.site.register(Playlist_track_relation)

class AlbumTrackRelationInline(admin.TabularInline):
    model = Album_track_relation
    extra = 1
    
class PlaylistTrackRelationInline(admin.TabularInline):
    model = Playlist_track_relation
    extra = 1

@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    inlines = [AlbumTrackRelationInline]

@admin.register(Playlist)
class AlbumAdmin(admin.ModelAdmin):
    inlines = [PlaylistTrackRelationInline]

@admin.register(Track)
class Trackadmin(admin.ModelAdmin):
    inlines = [AlbumTrackRelationInline]



@admin.register(Feedback)
class Feedbackadmin(admin.ModelAdmin):
    list_display=['description']