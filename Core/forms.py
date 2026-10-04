from django import forms  
from .models import Feedback, Track

class FeedbackForm(forms.ModelForm):


    class Meta:

        model = Feedback
        fields = ['name','email','description']


class TrackForm(forms.ModelForm):

    class Meta:
        model = Track
        fields = [
            'title',
            'artist',
            'featured_artist',
            'genres',
            'release_date',
            'cover',
            'audio_file',
            'description',
            'has_lyrics',
            'lyrics',
        ]
