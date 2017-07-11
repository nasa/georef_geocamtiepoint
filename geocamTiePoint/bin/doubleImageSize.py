#!/usr/bin/env python
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

from geocamTiePoint.models import Overlay


def doubleImageSize(overlayId):
    ov = Overlay.objects.get(key=overlayId)
    meta = ov.getJsonDict()
    for pt in meta['points']:
        pt[2] = pt[2] * 2
        pt[3] = pt[3] * 2
    ov.setJsonDict(meta)
    ov.save()


def main():
    import optparse
    parser = optparse.OptionParser('usage: doubleImageSize.py <overlayId>')
    _opts, args = parser.parse_args()
    if len(args) != 1:
        parser.error('expected exactly 1 arg')
    doubleImageSize(args[0])


if __name__ == '__main__':
    main()
