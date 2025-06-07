from django import forms

class YouTubeForm(forms.Form):
    url = forms.URLField(label="YouTube Video URL", required=True)
