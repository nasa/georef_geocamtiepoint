#!/usr/bin/env python

import logging

import pyproj
import numpy as np
from osgeo import gdal

import rpcModel
import gdalUtil


def testFit(imgPath):
    logging.basicConfig(level=logging.DEBUG)

    handle = gdal.Open(imgPath, gdal.GA_ReadOnly)
    img = gdalUtil.GdalImage(handle)
    imageWidth, imageHeight = img.getShape()
    lonLatAlt = img.getCenterLonLatAlt()
    clon, clat, _ = lonLatAlt[:, 0]

    T = img.mapPixelsFromLonLatAlts

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
    T_rpc = testFit(imgPath)
    gdalUtil.reprojectWithRpcMetadata(imgPath, T_rpc.getVrtMetadata(),
                                      gdalUtil.GOOGLE_MAPS_SRS, 'testrpc/out.tif')


def main():
    testRpcModel()


if __name__ == '__main__':
    main()
