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

import os

MAX_IMPORT_FILE_SIZE = 4000000  # bytes 

# This feature is rigged to be disabled due to the planned removal of the Appengine PDF service
PDF_IMPORT_ENABLED = True
PDF_MIME_TYPES = ('application/pdf',
                  'application/acrobat',
                  'application/nappdf',
                  'application/x-pdf',
                  'application/vnd.pdf',
                  'text/pdf',
                  'text/x-pdf',
                  )

# default initial viewport for alignment interface. if we can detect the
# user's position we'll use that instead. these bounds cover the
# continental US.
GEOCAM_TIE_POINT_DEFAULT_MAP_VIEWPORT = {
    "west": -130,
    "south": 22,
    "east": -59,
    "north": 52,
}


# set to 'INFO' or 'DEBUG' to get more debug information from L-M optimizer
GEOCAM_TIE_POINT_OPTIMIZE_LOG_LEVEL = 'WARNING'

GEOCAM_TIE_POINT_TEMPLATE_DEBUG = True  # If this is true, handlebars templates will not be cached.
GEOCAM_TIE_POINT_HANDLEBARS_DIR = [os.path.join('geocamTiePoint', 'templates', 'handlebars')]

# once the map zoom level exceeds the resolution of the original overlay
# image, zooming further doesn't provide more information. use this
# setting to specify how many additional levels of zoom we should
# provide past that point. this setting used to affect tile generation
# but now it only affects the client-side js map controls on the
# unaligned image.
GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION = 2

# amount of time to retain records in the database and blob store
# after they are marked as unused.
GEOCAM_TIE_POINT_RETAIN_SECONDS = 3600

GEOCAM_TIE_POINT_LICENSE_CHOICES = (
    ('http://creativecommons.org/publicdomain/mark/1.0/',
     'Public Domain'),

    ('http://creativecommons.org/licenses/by/3.0',
     'Creative Commons CC-BY'),

    ('http://creativecommons.org/licenses/by-nd/3.0',
     'Creative Commons CC-BY-ND'),

    ('http://creativecommons.org/licenses/by-nc-sa/3.0',
     'Creative Commons CC-BY-NC-SA'),

    ('http://creativecommons.org/licenses/by-sa/3.0',
     'Creative Commons CC-BY-SA'),

    ('http://creativecommons.org/licenses/by-nc/3.0',
     'Creative Commons CC-BY-NC'),

    ('http://creativecommons.org/licenses/by-nc-nd/3.0',
     'Creative Commons CC-BY-NC-ND'),

    )

# controls the default setting of the isPublic field on overlays.
# aligned tiles from public overlays can be viewed by any non-logged-in
# user, even though the app is in private beta.
GEOCAM_TIE_POINT_PUBLIC_BY_DEFAULT = True
