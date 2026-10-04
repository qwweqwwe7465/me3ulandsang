from django.conf.locale import de
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# Create your models here.

class Genre(models.Model):
    name=models.CharField(max_length=225)  
    def __str__(self):
        return self.name

        
    def top_track(self):
        return self.rel_track.order_by('-likes').first()

class Artist(models.Model):
    name = models.CharField(max_length=100)
    description= models.TextField(blank=1)
    genres = models.ManyToManyField(Genre,related_name='rel_artist')
    def __str__(self):
        return self.name
    photo = models.ImageField(default='default-artist.png')


class Track(models.Model):
    title = models.CharField(max_length=50)
    featured_artist=models.ManyToManyField(Artist,related_name='featured_tracks',blank=1)
    artist = models.ForeignKey(on_delete=models.CASCADE,to=Artist,related_name='tracks',null=1,blank=1)
    #album
    views = models.IntegerField(default=0)
    has_lyrics= models.BooleanField()
    lyrics = models.TextField(blank=True)
    genres = models.ManyToManyField(Genre,related_name='rel_track')
    likes = models.IntegerField(default=0)
    cover = models.ImageField(default='default-cover.png',upload_to='covers/')
    description = models.TextField(blank=1)
    release_date = models.DateTimeField(null=1,blank=1,default=timezone.now)
    date_added = models.DateTimeField(auto_now_add=True)
    audio_file = models.FileField(upload_to='tracks/',null=1,blank=1)
    def __str__(self):
        return self.title    
    def clean_artists(self):
        featured = self.featured_artist.all()
        if not featured:
            return str(self.artist)
        names = ", ".join(str(a) for a in featured)
        return f"{self.artist} (Ft {names})"
    

class Album(models.Model):
    name=models.CharField(max_length=100)
    description=models.TextField(blank=1)
    release_date = models.DateTimeField(null=1,blank=1,default=timezone.now)
    date_added = models.DateTimeField(auto_now_add=True)
    likes = models.IntegerField(default=0)
    views = models.IntegerField(default=0)
    genres = models.ManyToManyField(Genre,related_name='rel_album')
    tracks = models.ManyToManyField(Track, through="Album_track_relation")
    def __str__(self):
        return self.name


class Album_track_relation(models.Model):
    track = models.ForeignKey(Track, on_delete=models.CASCADE,related_name='albumr')
    album = models.ForeignKey(Album, on_delete=models.CASCADE,related_name='albumr')
    order = models.IntegerField()
    def __str__(self):
        return f"{self.album} - {self.order}: {self.track}"
    


class Playlist(models.Model):
    name = models.CharField(max_length=50)
    description=models.TextField(blank=1)
    date_added = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    likes = models.IntegerField(default=0)
    views = models.IntegerField(default=0)    
    genres = models.ManyToManyField(Genre,related_name='rel_Playlist')
    tracks = models.ManyToManyField(Track, through="Playlist_track_relation")
    def __str__(self):
        return self.name
    def select_cover(self, i=1):
        # Query the relation directly or through tracks
        relation = self.trackr.filter(order=i).select_related('track').first()
        if relation and relation.track and relation.track.cover:
            return relation.track.cover.url
        return None
class Playlist_track_relation(models.Model):
    track = models.ForeignKey(Track, on_delete=models.CASCADE,related_name='playlistr')
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE,related_name='trackr')
    order = models.IntegerField()
    def __str__(self):
        return f"{self.playlist} - {self.order}: {self.track}"






class Feedback(models.Model):
    name= models.CharField(max_length=100,blank=1)
    description=models.TextField()
    email= models.EmailField(max_length=254,blank=1)
    def __str__(self):
            return self.name
    
