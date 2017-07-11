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

"""
This is a place to put any prep code you need to run before your app
is ready.

For example, you might need to render some icons.  The convention for
that is to put the source data in your app's media_src directory and
render the icons into your app's build/media directory (outside version
control).

How this script gets run: when the site admin runs "./manage.py prep",
one of the steps is "prepapps", which calls
management/appCommands/prep.py command for each app (if it exists).
"""

from django.core.management.base import NoArgsCommand


class Command(NoArgsCommand):
    help = 'Prep geocamTiePoint'

    def handle_noargs(self, **options):
        # put your code here
        pass
