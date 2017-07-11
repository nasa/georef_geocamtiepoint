#__BEGIN_LICENSE__
# Copyright (c) 2017, United States Government, as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All rights reserved.
#
# The GeoRef platform is licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
#__END_LICENSE__

from django import forms
from django.forms import ValidationError

IMAGE_SIZE_CHOICES = (('small', 'Small'), ('large', 'Large'))


class NewImageDataForm(forms.Form):
    image = forms.FileField(required=False)
    imageUrl = forms.URLField(required=False)
    mission = forms.CharField(required=False)
    roll = forms.CharField(required=False)
    frame = forms.CharField(required=False)
    endFrame = forms.CharField(required=False)
    imageSize = forms.ChoiceField(widget=forms.RadioSelect, choices=IMAGE_SIZE_CHOICES)
    autoregister = forms.BooleanField(required=False)
    sequence = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = super(NewImageDataForm, self).clean()
        image_file = cleaned_data.get("image")
        image_url = cleaned_data.get("imageUrl")
        mission = cleaned_data.get("mission")

        if not ((bool(image_file) ^ bool(image_url)) ^ bool(mission)):
            raise ValidationError("Requires only one of URL or uploaded image or mission id")
 
        return cleaned_data