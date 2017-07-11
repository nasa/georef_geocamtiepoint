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
import logging

import numpy as np
import numpy.linalg
from osgeo import gdal, osr
import pyproj

def dosys(cmd):
    logging.info('running: %s', cmd)
    ret = os.system(cmd)
    if ret != 0:
        logging.warn('command exited with non-zero return value %s', ret)
    return ret


def getGeoTransform(gdalImageHandle):
    # return gdalImageHandle.GetGeoTransform()
    (x0, dx, rotX, y0, rotY, dy) = gdalImageHandle.GetGeoTransform()
    assert rotX == 0
    assert rotY == 0
    return np.array([[dx, 0, x0],
                     [0, dy, y0]])


def applyGeoTransformAug(geoTransform, mapPixelsAug):
    return np.dot(geoTransform, mapPixelsAug)


def applyGeoTransform(geoTransform, mapPixels):
    n = mapPixels.shape[1]
    mapPixelsAug = np.vstack([mapPixels, np.ones(n)])
    return applyGeoTransformAug(geoTransform, mapPixelsAug)


def invertGeoTransform(M):
    MAug = np.vstack([M, np.array([0, 0, 1])])
    inverseAug = numpy.linalg.inv(MAug)
    inverse = inverseAug[:2, :]
    return inverse


def getMapProj(gdalImageHandle):
    srsWkt = gdalImageHandle.GetProjection()
    srs = osr.SpatialReference()
    srs.ImportFromWkt(srsWkt)
    srsProj4 = srs.ExportToProj4()
    return pyproj.Proj(srsProj4)


class GdalImage(object):
    def __init__(self, gdalImageHandle):
        self.gdalImageHandle = gdalImageHandle
        self.geoTransform = getGeoTransform(gdalImageHandle)
        self.inv = invertGeoTransform(self.geoTransform)
        self.mapProj = getMapProj(gdalImageHandle)

    def mapProjectedCoordsFromMapPixels(self, mapPixel):
        return applyGeoTransform(self.geoTransform, mapPixel)

    def mapPixelsFromMapProjectedCoords(self, projectedCoords):
        return applyGeoTransform(self.inv, projectedCoords)

    def lonLatAltsFromMapProjectedCoords(self, projectedCoords):
        pcx, pcy = projectedCoords
        lon, lat = self.mapProj(pcx, pcy, inverse=True)
        n = projectedCoords.shape[1]
        alt = np.zeros(n)
        return np.vstack([lon, lat, alt])

    def mapProjectedCoordsFromLonLatAlts(self, lonLatAlt):
        lon, lat, _ = lonLatAlt
        x, y = self.mapProj(lon, lat)
        return np.vstack([x, y])

    def lonLatAltsFromMapPixels(self, mapPixel):
        return (self.lonLatAltsFromMapProjectedCoords
                (self.mapProjectedCoordsFromMapPixels(mapPixel)))

    def mapPixelsFromLonLatAlts(self, lonLatAlt):
        return (self.mapPixelsFromMapProjectedCoords
                (self.mapProjectedCoordsFromLonLatAlts(lonLatAlt)))

    def getShape(self):
        return (self.gdalImageHandle.RasterXSize,
                self.gdalImageHandle.RasterYSize)

    def getCenterLonLatAlt(self):
        w, h = self.getShape()
        cx = float(w) / 2
        cy = float(h) / 2
        pix = np.array([[cx], [cy]])
        return self.lonLatAltsFromMapPixels(pix)


def buildVrtWithRpcMetadata(imgPath, rpcMetadata):
    noSuffix = os.path.splitext(imgPath)[0]
    geotiffName = noSuffix + '_rpc.tif'
    vrt0Name = noSuffix + '_rpc0.vrt'
    # make a bogus geotiff with same image contents so gdalbuildvrt will build a vrt for us
    dosys('gdal_translate -a_srs "+proj=latlong" -a_ullr -30 30 30 -30 %s %s'
          % (imgPath, geotiffName))
    # create raw vrt
    dosys('gdalbuildvrt %s %s' % (vrt0Name, geotiffName)) 
    # edit vrt -- delete srs and geoTransform sections, add RPC metadata
    vrtName = noSuffix + '_rpc.vrt'
    vrt0 = open(vrt0Name, 'r').read().splitlines()
    startTag = vrt0[0]
    rest = vrt0[1:]
    dosys('rm -f %s' % vrtName)
    with open(vrtName, 'w') as vrtOut:
        vrtOut.write(startTag + '\n')
        vrtOut.write(rpcMetadata)
        vrtOut.write('\n'.join(rest) + '\n')
    logging.info('Inserted RPC metadata into VRT file %s' % vrtName)

    return vrtName


GOOGLE_MAPS_SRS = '+proj=merc +datum=WGS84'
EPSG_4326 = '+proj=longlat +datum=WGS84'

def reprojectWithRpcMetadata(inputPath, inputRpcMetadata, outputSrs, outputPath):
    # TODO: need to explicitly specify bounding box for output using gdalwarp's option -te
    #   Without that, the command below may fail when trying to calculate bounds for
    #   wide-angle photos that include space as well as ground in the image frame.
    vrtPath = buildVrtWithRpcMetadata(inputPath, inputRpcMetadata)
    dosys('rm -f %s' % outputPath)
    dosys('gdalwarp -r lanczos -rpc -t_srs "%s" -of GTiff -co COMPRESS=LZW -co TILED=YES %s %s' % (outputSrs, vrtPath, outputPath))
