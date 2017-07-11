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

import numpy
import PIL
from django.core.cache import cache

from quadTree import SimpleQuadTreeGenerator

fakeFile = '/home/vagrant/geocamspace/geoRef/data/test_large.jpg'
im = PIL.Image.open(fakeFile)
dummyQuadTreeId = 1
simple = SimpleQuadTreeGenerator(dummyQuadTreeId,im)
data = simple.getTileData(3,0,0)
print data
try: 
    cache.set("testKey", data)
except: 
    print "cacheing failed"