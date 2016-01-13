# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

from django import forms
from django.forms import ValidationError


from django import forms

IMAGE_SIZE_CHOICES = (('small', 'Small'), ('large', 'Large'))


class NewImageDataForm(forms.Form):
    image = forms.FileField(required=False)
    imageUrl = forms.URLField(required=False)
    mission = forms.CharField(required=False)
    roll = forms.CharField(required=False)
    frame = forms.CharField(required=False)
    imageSize = forms.ChoiceField(widget=forms.RadioSelect, choices=IMAGE_SIZE_CHOICES)
    autoregister = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = super(NewImageDataForm, self).clean()
        image_file = cleaned_data.get("image")
        image_url = cleaned_data.get("imageUrl")
        mission = cleaned_data.get("mission")

        if not ((bool(image_file) ^ bool(image_url)) ^ bool(mission)):
            raise ValidationError("Requires only one of URL or uploaded image or mission id")
 
        return cleaned_data