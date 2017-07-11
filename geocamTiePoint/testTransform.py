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

from geocamTiePoint import transform

POINTS = [
        [
            -13877359.198523184,
            6164031.440801282,
            45.4999999999999,
            15.50000000000681
        ],
        [
            -7684125.418745065,
            6007488.406873245,
            647.5000000000002,
            31.49999999999952
        ],
        [
            -9024525.146753915,
            2886411.667932928,
            579.4999999999998,
            418.4999999999996
        ],
        [
            -10589955.486034326,
            6379278.112452344,
            366.5000000000003,
            41.500000000005336
        ],
        [
            -11372670.65567453,
            4852983.53165394,
            281.49999999999955,
            196.49999999999196
        ],
        [
            -13045724.330780469,
            3825669.8715011734,
            68.50000000000003,
            289.4999999999986
        ],
        [
            -10824770.036926387,
            2994035.003758455,
            335.50000000000034,
            424.50000000000097
        ]
    ]

TO_PTS, FROM_PTS = transform.splitPoints(POINTS)
N = len(POINTS)


def testTransformClass(cls):
    tform = cls.fit(TO_PTS, FROM_PTS)
    toPtsApprox = transform.forwardPts(tform, FROM_PTS)
    print "INPUT (to_Pts):"
    print TO_PTS
    print "TFROMED (to_pts):"
    print toPtsApprox
    #print toPtsApprox
    print ('%s: %e'
           % (cls.__name__,
              numpy.linalg.norm(toPtsApprox - TO_PTS) / N))

def testTransformClass2(cls):
    tform = cls.fit(TO_PTS, FROM_PTS, "ISS039-E-12345")
    toPtsApprox = transform.forwardPts(tform, FROM_PTS)
    print "INPUT (to_Pts):"
    print TO_PTS
    print "TFROMED (to_pts):"
    print toPtsApprox
    #print toPtsApprox
    print ('%s: %e'
           % (cls.__name__,
              numpy.linalg.norm(toPtsApprox - TO_PTS) / N))

testTransformClass2(transform.CameraModelTransform)
testTransformClass(transform.TranslateTransform)
testTransformClass(transform.RotateScaleTranslateTransform)
testTransformClass(transform.AffineTransform)
testTransformClass(transform.ProjectiveTransform)
testTransformClass(transform.QuadraticTransform)
testTransformClass(transform.QuadraticTransform2)

print transform.getTransform(TO_PTS, FROM_PTS)
