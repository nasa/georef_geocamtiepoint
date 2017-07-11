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
from geocamUtil import imageInfo
from geocamUtil.registration import imageCoordToEcef, rotMatrixOfCameraInEcef, rotMatrixFromEcefToCamera, eulFromRot, rotFromEul
from geocamUtil.geomath import transformEcefToLonLatAlt, transformLonLatAltToEcef, EARTH_RADIUS_METERS
import math
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

def getInitialData():
    if 0: 
        imageMetaData = imageInfo.getIssImageInfo("ISS039", "E", "12345")
        lat = imageMetaData['latitude']
        lon = imageMetaData['longitude']
        alt = imageMetaData['altitude']
        Fx = imageMetaData['focalLength'][0]
        Fy = imageMetaData['focalLength'][1]
        width = imageMetaData['width']
        height = imageMetaData['height']
        return [lat, lon, alt, Fx, Fy, width, height]
    if 0:
        # basically camera is directly above the north pole
        imageMetaData = imageInfo.getIssImageInfo("ISS039", "E", "12345")
        Fx = imageMetaData['focalLength'][0]
        Fy = imageMetaData['focalLength'][1]
        lat = 90
        lon = 0
        alt = EARTH_RADIUS_METERS + 300000
        width = 900
        height = 400
        return [lat, lon, alt, Fx, Fy, width, height]
    if 0:
        # basically camera is directly above the north pole
        imageMetaData = imageInfo.getIssImageInfo("ISS039", "E", "12345")
        Fx = imageMetaData['focalLength'][0]
        Fy = imageMetaData['focalLength'][1]
        lat = 0
        lon = 90
        alt = EARTH_RADIUS_METERS + 300000
        width = 900
        height = 400
        return [lat, lon, alt, Fx, Fy, width, height]
    if 1:
        # camera is at the equator
        # basically camera is directly above the north pole
        imageMetaData = imageInfo.getIssImageInfo("ISS039", "E", "12345")
        Fx = imageMetaData['focalLength'][0]
        Fy = imageMetaData['focalLength'][1]
        print Fx
        print Fy
        lat = 0
        lon = 0
        alt = EARTH_RADIUS_METERS + 300000
        width = 900
        height = 400
        return [lat, lon, alt, Fx, Fy, width, height]


def forward(pt):
    """
    Takes in a point in pixel coordinate and returns point in gmap units (meters)
    """
    lat, lon, alt, Fx, Fy, width, height = getInitialData()
    camLonLatAlt = (lon,lat,alt)
    rotMatrix = rotMatrixOfCameraInEcef(lon, transformLonLatAltToEcef(camLonLatAlt)) 
    print "rotMatrix"
    print rotMatrix
    roll, pitch, yaw = eulFromRot(rotMatrix)
    print 'roll pitch yaw'
    print (roll * (180/numpy.pi), pitch * (180/numpy.pi), yaw * (180/numpy.pi))
    rotMatrix = rotFromEul(roll, pitch, yaw)
    print "rot matrix back"
    print rotMatrix
    
    opticalCenter = (int(width / 2.0), int(height / 2.0))
    focalLength = (Fx, Fy)
    
    # convert image pixel coordinates to ecef
    ecef = imageCoordToEcef(camLonLatAlt, pt, opticalCenter, focalLength, rotMatrix) 
    return ecef
    # convert ecef to lon lat
#     lonLatAlt = transformEcefToLonLatAlt(ecef)
#     toPt = [lonLatAlt[0], lonLatAlt[1]]  # needs to be this order (lon, lat)
#     xy_meters = transform.lonLatToMeters(toPt) 
#     return xy_meters
#     return toPt


def reverse(pt):
    """
    Takes a point in gmap meters and converts it to image coordinates
    """
    lat, lon, alt, Fx, Fy, width, height = getInitialData()
    camLonLatAlt = (lon,lat,alt)
    rotMatrix = rotMatrixOfCameraInEcef(lon, transformLonLatAltToEcef(camLonLatAlt)) 
    roll, pitch, yaw = eulFromRot(rotMatrix)
#     #convert point to lat lon, and then to ecef
#     ptlon, ptlat = transform.metersToLatLon([pt[0], pt[1]])
#     ptalt = 0
#     # convert lon lat alt to ecef
#     px, py, pz = transformLonLatAltToEcef([ptlon, ptlat, ptalt])
    
#     print ("0,0 lat lon to meters")
#     print transform.lonLatToMeters([0,0])
#     print (px, py, pz)
    
    px, py, pz = (pt[0],pt[1], pt[2])  
    pt = numpy.array([[px, py, pz, 1]]).transpose()
    cameraMatrix = numpy.matrix([[Fx, 0, width / 2.0],  # matrix of intrinsic camera parameters
                                [0, Fy, height / 2.0],
                                [0, 0, 1]],
                               dtype='float64')  
    x,y,z = transformLonLatAltToEcef((lon,lat,alt))  # camera pose in ecef
    # euler to matrix
    rotation = rotFromEul(roll, pitch, yaw)
    rotation = numpy.transpose(rotation)  # can I do this?
#         rotation = rotMatrixFromEcefToCamera(lon, [x,y,z])  # world to camera
    cameraPoseColVector = numpy.array([[x, y, z]]).transpose()
    translation = -1* rotation * cameraPoseColVector
    # append the translation matrix (3x1) to rotation matrix (3x3) -> becomes 3x4
    rotTransMat = numpy.c_[rotation, translation]
    ptInImage = cameraMatrix * rotTransMat * pt
    u = ptInImage.item(0) / ptInImage.item(2)
    v = ptInImage.item(1) / ptInImage.item(2)
    ptInImage =  [u, v]
    return ptInImage


def testTransformClass():
    lat, lon, alt, Fx, Fy, width, height = getInitialData()
    camLonLatAlt = (lon, lat, alt)
    rotMatrix = rotMatrixOfCameraInEcef(lon, transformLonLatAltToEcef(camLonLatAlt))    
    print "rotation Matrix is"
    print rotMatrix
     
    print "euler angle is"
    r,p,y = eulFromRot(rotMatrix)
    print [r,p,y]
     
    print "back to rotation Matrix"
    print rotFromEul(r,p,y)
    
    """
    Forward
    """
#     pt = [width / 2.0, height / 2.0]  # if image coord is at center of image
#     fwdRetval = forward(pt)
#     print "ecef should be at 0, 0, some radius"
#     print fwdRetval
#      
#     print "back to image coordinates"
#     print reverse(fwdRetval)
#      
#     print"back to ecef"
#     print forward(reverse(fwdRetval))
#     
    """
    Reverse
    """
#     # input 0,0,x for ecef and make sure I get center of the image
#     reverseRetval = reverse([EARTH_RADIUS_METERS * math.cos(15/180 * math.pi),EARTH_RADIUS_METERS * math.sin(15/180 * math.pi) , 0])
#     reverseRetval = reverse([0, EARTH_RADIUS_METERS / 2.0, 0])
#     print "imagePt should be center of image with size %s, %s" % (width, height) 
#     print reverseRetval

    
    
testTransformClass()
