# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import numpy

from geocamTiePoint import transform
from geocamUtil import imageInfo
from geocamUtil.registration import imageCoordToEcef, rotMatrixFromEcefToCamera
from geocamUtil.geomath import transformEcefToLonLatAlt, transformLonLatAltToEcef, EARTH_RADIUS_METERS

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
#     imageMetaData = imageInfo.getIssImageInfo("ISS039", "E", "12345")
#     lat = imageMetaData['latitude']
#     lon = imageMetaData['longitude']
#     alt = imageMetaData['altitude']
#     Fx = imageMetaData['focalLength'][0]
#     Fy = imageMetaData['focalLength'][1]
#     width = imageMetaData['width']
#     height = imageMetaData['height']
#     return [lat, lon, alt, Fx, Fy, width, height]
    if 0:
        # basically camera is directly above the north pole
        imageMetaData = imageInfo.getIssImageInfo("ISS039", "E", "12345")
        Fx = imageMetaData['focalLength'][0]
        Fy = imageMetaData['focalLength'][1]
        lat = 90
        lon = 0
        alt = 500
        width = 900
        height = 400
        return [lat, lon, alt, Fx, Fy, width, height]
    if 1:
        # camera is at the equator
        # basically camera is directly above the north pole
        imageMetaData = imageInfo.getIssImageInfo("ISS039", "E", "12345")
        Fx = imageMetaData['focalLength'][0]
        Fy = imageMetaData['focalLength'][1]
        lat = 0
        lon = 90
        alt = 500
        width = 900
        height = 400
        return [lat, lon, alt, Fx, Fy, width, height]


def forward(pt):
    """
    Takes in a point in pixel coordinate and returns point in gmap units (meters)
    """
    lat, lon, alt, Fx, Fy, width, height = getInitialData()
    lonLatAlt = (lon, lat, alt)  # camera position in lon,lat,alt
    opticalCenter = (int(width / 2.0), int(height / 2.0))
    focalLength = (Fx, Fy)
    
    # convert image pixel coordinates to ecef
    ecef = imageCoordToEcef(lonLatAlt, pt, opticalCenter, focalLength)
    return ecef
    # convert ecef to lon lat
#     lonLatAlt = transformEcefToLonLatAlt(ecef)
#     toPt = [lonLatAlt[0], lonLatAlt[1]]  # needs to be this order (lon, lat)
#     xy_meters = transform.lonLatToMeters(toPt) 
#     return xy_meters
#     return toPt


def reverse(pt):
    """
    Takes a 2D point in gmap meters and converts it to image coordinates
    """
    lat, lon, alt, Fx, Fy, width, height = getInitialData()
                                                          
    #convert point to lat lon, and then to ecef
    ptlon, ptlat = pt #transform.metersToLatLon([pt[0], pt[1]])
    ptalt = 0
    # convert lon lat alt to ecef
    pt = transformLonLatAltToEcef([ptlon, ptlat, ptalt])
     
    cameraMatrix = numpy.array([[Fx, 0, width / 2.0],  # matrix of intrinsic camera parameters
                                [0, Fy, height / 2.0],
                                [0, 0, 1]],
                               dtype='float64')  
    
    cameraPoseEcef = transformLonLatAltToEcef((lon,lat,alt))
    rotation = rotMatrixFromEcefToCamera(lon, cameraPoseEcef)  # world to camera
    translation = -1* rotation * numpy.array([[cameraPoseEcef[0]], 
                                           [cameraPoseEcef[1]], 
                                           [cameraPoseEcef[2]]])   
    ptInImage = cameraMatrix * rotation * translation * pt
    ptInImage =  [ptInImage[0] / ptInImage[2], ptInImage[1] / ptInImage[2]]
    return ptInImage


def testTransformClass():
    lat, lon, alt, Fx, Fy, width, height = getInitialData()
    
    """
    Forward
    """
    pt = [width / 2.0, height / 2.0]  # if image coord is at center of image
    fwdRetval = forward(pt)
    print "ecef should be at 0, some radius, 0"
    print fwdRetval
#     meters = forward(pt)
#     print "gmap meters coords should be at -13877359.198523184, 6164031.440801282"
#     print meters
    
    """
    Reverse
    """
    # input 0,0,x for ecef and make sure I get center of the image
    reverseRetval = reverse([0,0])
    print "imagePt should be center of image with size %s, %s" % (width, height) 
    print reverseRetval
    
testTransformClass()
