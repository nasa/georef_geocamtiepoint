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

#!/usr/bin/env python

import logging
import os

import pyproj
import numpy as np
from osgeo import gdal

import rpcModel
import gdalUtil


def dosys(cmd):
    logging.info('running: %s', cmd)
    ret = os.system(cmd)
    if ret != 0:
        logging.warn('command exited with non-zero return value %s', ret)
    return ret


def testFit(imgPath):
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')

    handle = gdal.Open(imgPath, gdal.GA_ReadOnly)
    img = gdalUtil.GdalImage(handle)
    imageWidth, imageHeight = img.getShape()
    lonLatAlt = img.getCenterLonLatAlt()
    clon, clat, _ = lonLatAlt[:, 0]

    T = img.mapPixelsFromLonLatAlts  # forward function (lon lat alt -> pixel xy) In the function, it takes in array of lon lat alts, and returns array of pixel coords.
                                     # I want to use mine instead.
    T_rpc = rpcModel.fitRpcToModel(T,
                                   imageWidth, imageHeight,
                                   clon, clat)
    print T_rpc.getVrtMetadata()

    if 0:
        # debug
        u1 = np.vstack([[clon-1, clat, 0],
                        [clon, clat, 0],
                        [clon+1, clat, 0]]).T
        print
        print u1
        print T_rpc.forward(u1)

        u2 = np.vstack([[clon, clat-1, 0],
                        [clon, clat, 0],
                        [clon, clat+1, 0]]).T
        print
        print u2
        print T_rpc.forward(u2)

    return T_rpc


def testRpcModel():
    imgPath = 'testrpc/conus.tif'
    resultPath = 'testrpc/out.tif'
    tilesPath = 'testrpc/tiles'
    vwTilesPath = 'testrpc/vwTiles'

    T_rpc = testFit(imgPath)
    srs = gdalUtil.EPSG_4326
    # srs = gdalUtil.GOOGLE_MAPS_SRS
    gdalUtil.reprojectWithRpcMetadata(imgPath, T_rpc.getVrtMetadata(),
                                      srs, resultPath)
    dosys('rm -rf %s' % tilesPath)
    logging.info('fetch mostly-working version of gdal2tiles.py from here: http://www.klokan.cz/projects/gdal2tiles/gdal2tiles.py')
    dosys('./gdal2tiles.py -forcekml %s %s'
          % (resultPath, tilesPath))
    logging.info('')
    logging.info('*** view testrpc/tiles/openlayers.html ***')
    logging.info('*** view testrpc/tiles/doc.kml ***')

    logging.info('')
    logging.info('NOTE: now trying an alternate way to make tiles that only works if you have NASA Vision Workbench installed -- this approach seems to make better KML output')
    dosys('rm -rf %s' % vwTilesPath)
    dosys('image2qtree testrpc/out.tif -o %s' % vwTilesPath)
    logging.info('*** view testrpc/vwTiles/vwTiles.kml ***')


def main():
    testRpcModel()


if __name__ == '__main__':
    main()
