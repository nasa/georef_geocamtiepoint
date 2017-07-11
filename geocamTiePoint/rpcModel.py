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

import math
import logging

import scipy
import numpy as np
import numpy.linalg
from scipy.optimize import brentq as findRoot

def spaceSeparated(x):
    return ' '.join(['%s' % xi for xi in x])


class RpcTransform(object):
    """
    Implement GeoTIFF RPC model as described in http://geotiff.maptools.org/rpc_prop.html
    """
    def __init__(self,
                 sampOff, lineOff,
                 lonOff, latOff, heightOff,
                 sampScale, lineScale,
                 lonScale, latScale, heightScale,
                 sampNumCoeff, sampDenCoeff,
                 lineNumCoeff, lineDenCoeff):
        """
        Construct an RpcTransform.

        The 'off' and 'scale' parameters can be chosen freely; we
        recommend values below that should be good for numerical
        stability.

        The 'coeff' parameters will be tuned through model fitting.

        If the image size in pixels is (w x h), set:
          sampOff = w/2
          lineOff = h/2
          sampScale = w/2
          lineScale = h/2
        If the image footprint bounding box is (lonMin, lonMax, latMin, latMax), set:
          lonOff = (lonMin + lonMax)/2
          latOff = (latMin + latMax)/2
          heightOff = 0
          lonScale = (lonMax - lonMin)/2
          latScale = (latMax - latMin)/2
          heightScale = 1000
        """
        self.sampOff = sampOff
        self.lineOff = lineOff
        self.lonOff = lonOff
        self.latOff = latOff
        self.heightOff = heightOff

        self.sampScale = sampScale
        self.lineScale = lineScale
        self.latScale = latScale
        self.lonScale = lonScale
        self.heightScale = heightScale

        self.sampNumCoeff = sampNumCoeff
        self.sampDenCoeff = sampDenCoeff
        self.lineNumCoeff = lineNumCoeff
        self.lineDenCoeff = lineDenCoeff

    def getPolyMatrix(self, u):
        """
        Returns the matrix used for RPC polynomial evaluation.

        @u is a 3 x n matrix representing n 3D points in WGS84 (lon, lat, alt) format.
        """
        lon = u[0, :]
        lat = u[1, :]
        height = u[2, :]

        P = (lat - self.latOff) / self.latScale
        L = (lon - self.lonOff) / self.lonScale
        H = (height - self.heightOff) / self.heightScale

        n = u.shape[1]
        M = np.zeros((n, 20))

        M[:, 0] = np.ones(n)
        M[:, 1] = L
        M[:, 2] = P
        M[:, 3] = H
        M[:, 4] = L * P
        M[:, 5] = L * H
        M[:, 6] = P * H
        M[:, 7] = L ** 2
        M[:, 8] = P ** 2
        M[:, 9] = H ** 2
        M[:, 10] = P * L * H
        M[:, 11] = L ** 3
        M[:, 12] = L * P ** 2
        M[:, 13] = L * H ** 2
        M[:, 14] = L ** 2 * P
        M[:, 15] = P ** 3
        M[:, 16] = P * H ** 2
        M[:, 17] = L ** 2 * H
        M[:, 18] = P ** 2 * H
        M[:, 19] = H ** 3

        return M

    def forward(self, u):
        """
        Calculate v = T(u), where T is the RPC transform.

        @u is a 3 x n matrix representing n 3D points in WGS84 (lon, lat, alt) format.
        @v is a 2 x n matrix representing n 2D points in image pixel (px, py) format.
        """
        self.M = self.getPolyMatrix(u)

        c = np.dot(self.M, self.sampNumCoeff) / np.dot(self.M, self.sampDenCoeff)
        r = np.dot(self.M, self.lineNumCoeff) / np.dot(self.M, self.lineDenCoeff)

        x = self.sampOff + c * self.sampScale
        y = self.lineOff + r * self.lineScale
        v = np.vstack([x, y])
        return v

    @classmethod
    def getInitParams(cls, v, u, fixed):
        """
        Return initial parameters for least-squares fitting.

        @u is a 3 x n matrix representing n 3D points in WGS84 (lon, lat, alt) format.
        @v is a 2 x n matrix representing n 2D points in image pixel (px, py) format.

        @fixed is a dictionary specifying the fixed parameters that
          don't get optimized (offsets and scales).
        """
        return np.zeros(78)

    @classmethod
    def fromParams(cls, params, fixed):
        """
        Construct an RpcTransform instance based on the specified @params and @fixed.

        @params is the 78-parameter vector that is optimized during
          least-squares fit.

        @fixed is a dictionary specifying the fixed parameters that
          don't get optimized (offsets and scales).
        """
        names = [
            'sampOff', 'lineOff',
            'lonOff', 'latOff', 'heightOff',
            'sampScale', 'lineScale',
            'lonScale', 'latScale', 'heightScale',
        ]
        args = dict([(name, fixed[name])
                     for name in names])

        args['sampNumCoeff'] = np.array(params[0:20])
        args['lineNumCoeff'] = np.array(params[20:40])
        args['sampDenCoeff'] = np.concatenate([[1], params[40:59]])
        args['lineDenCoeff'] = np.concatenate([[1], params[59:78]])

        return cls(**args)

    @classmethod
    def getErrorFunc(cls, v, u, fixed):
        """
        Return the error function to be minimized by the least-squares
        fit.
        """
        def errorFunc(params):
            T = cls.fromParams(params, fixed)
            err = v - T.forward(u)
            return err.ravel()
        return errorFunc

    @classmethod
    def fit(cls, v, u, fixed):
        """
        Return a transform optimized by least-squares fitting.

        @u is a 3 x n matrix representing n 3D points in WGS84 (lon, lat, alt) format.
        @v is a 2 x n matrix representing n 2D points in image pixel (px, py) format.

        @fixed is a dictionary specifying the fixed parameters that
          don't get optimized (offsets and scales).
        """
        params0 = cls.getInitParams(v, u, fixed)
        errorFunc = cls.getErrorFunc(v, u, fixed)
        params, _cov = scipy.optimize.leastsq(errorFunc, params0)
        return params

    def getVrtMetadata(self):
        ctx = {
            'HEIGHT_OFF': self.heightOff,
            'HEIGHT_SCALE': self.heightScale,
            'LAT_OFF': self.latOff,
            'LAT_SCALE': self.latScale,
            'LINE_DEN_COEFF': spaceSeparated(self.lineDenCoeff),
            'LINE_NUM_COEFF': spaceSeparated(self.lineNumCoeff),
            'LINE_OFF': self.lineOff,
            'LINE_SCALE': self.lineScale,
            'LONG_OFF': self.lonOff,
            'LONG_SCALE': self.lonScale,
            'SAMP_DEN_COEFF': spaceSeparated(self.sampDenCoeff),
            'SAMP_NUM_COEFF': spaceSeparated(self.sampNumCoeff),
            'SAMP_OFF': self.sampOff,
            'SAMP_SCALE': self.sampScale,
        }
        fields = '\n'.join(['    <MDI key="%s">%s</MDI>' % (key, val)
                              for key, val in sorted(ctx.items())])
        tmpl = ("""
  <Metadata domain="RPC">
%s
  </Metadata>
"""[1:])
        return tmpl % fields


def pixInImage(v, imageWidth, imageHeight):
    x = v[0, :]
    y = v[1, :]
    return np.min([x, imageWidth - x,
                   y, imageHeight - y],
                  axis=0)


def findRootOrDefault(f, a, b, dflt):
    """
    Find the point in the interval [a, b] where f(x) drops below
    zero or, if both endpoints are greater than zero, return
    the default.
    """
    if f(a) > 0 and f(b) > 0:
        return dflt
    else:
        try: 
            root = findRoot(f, a, b)
        except ValueError: 
            print "root cannot be found"
            print "a and b are %.2f %.2f" % (a,b)
            print "f(a) is %.2f" % (f(a))
            print "f(b) is %.2f" % (f(b))
        return root


def getApproxImageFootprintBoundingBox(T,
                                       imageWidth, imageHeight,
                                       clon, clat,
                                       maxDistanceDegrees,
                                       margin=0.5):
    """
    Return an approximate geographic bounding box for the image footprint.

    See fitRpcToModel() for arg types.
    """
    def lonInFootprint(lon):
        u = np.array([[lon], [clat], [0.0]])
        return pixInImage(T(u), imageWidth, imageHeight)[0]

    def latInFootprint(lat):
        u = np.array([[clon], [lat], [0.0]])
        return pixInImage(T(u), imageWidth, imageHeight)[0]

    lonMin = findRootOrDefault(lonInFootprint, clon - maxDistanceDegrees, clon,
                               dflt=clon - maxDistanceDegrees)
    lonMax = findRootOrDefault(lonInFootprint, clon, clon + maxDistanceDegrees,
                               dflt=clon + maxDistanceDegrees)
    latMin = findRootOrDefault(latInFootprint, clat - maxDistanceDegrees, clat,
                               dflt=clat - maxDistanceDegrees)
    latMax = findRootOrDefault(latInFootprint, clat, clat + maxDistanceDegrees,
                               dflt=clat + maxDistanceDegrees)

    lonMin = clon + (lonMin - clon) * (1 + margin)
    lonMax = clon + (lonMax - clon) * (1 + margin)
    latMin = clat + (latMin - clat) * (1 + margin)
    latMax = clat + (latMax - clat) * (1 + margin)

    return [lonMin, latMin, lonMax, latMax]


def getSubRandomSamples(bbox, numSamples, isValidFunc):
    """
    @bbox is [xmin, ymin, xmax, ymax]

    Returns a 3 x n matrix u of numSamples 3D points u = (x, y, 0), where
      xmin < x < xmax, ymin < y < ymax, and isValidFunc(u) == True

    The points are distributed through the bbox as a "subrandom
    sequence". Subrandom points are like random points, but tend to be
    more evenly
    distributed. https://en.wikipedia.org/wiki/Low-discrepancy_sequence#Additive_recurrence
    """
    xmin, ymin, xmax, ymax = bbox
    xscale = xmax - xmin
    yscale = ymax - ymin

    # fairly arbitrary constants. shouldn't be too close to small
    # whole number ratios.
    dx = (math.sqrt(5) - 1) / 2.0
    dy = math.sqrt(2) - 1

    result = []
    while len(result) < numSamples:
        i = len(result)
        x0 = (dx * i) % 1
        y0 = (dy * i) % 1
        x = xmin + x0 * xscale
        y = ymin + y0 * yscale
        u = np.array([[x], [y], [0]])
        if isValidFunc(u):
            result.append(u)

    return np.hstack(result)


def fitRpcToModel(T,
                  imageWidth, imageHeight,
                  clon, clat,
                  maxDistanceDegrees=10):
    """
    @T is a transform function (projection model) such that v = T(u) where 
            @v is a 3 x n matrix of n 3D points in WGS84 (lon, lat, alt)
            @u is a 2 x n matrix of n 2D points in image (px, py)
    @imageWidth and @imageHeight are the size of the image in pixels
    @clon, @clat should be the "geographic center point" i.e. the approximate (lon, lat)
      of the image center point.
    @maxDistanceDegrees is used to limit the area over which we do the RPC
      fit to a bounding box around (clon, clat) with maxDistanceDegrees.
    """
    bbox = getApproxImageFootprintBoundingBox(T,
                                              imageWidth, imageHeight,
                                              clon, clat,
                                              maxDistanceDegrees)

    [lonMin, latMin, lonMax, latMax] = bbox
    logging.info('bbox: %s', bbox)

    def geoInImageFootprint(u):
        return pixInImage(T(u), imageWidth, imageHeight)

    u = getSubRandomSamples(bbox, numSamples=500, isValidFunc=geoInImageFootprint)
    v = T(u)

    # set up fixed params
    fixed = {
        'sampOff': imageWidth / 2,
        'lineOff': imageHeight / 2,
        'sampScale': imageWidth / 2,
        'lineScale': imageHeight / 2,
        'lonOff': clon,
        'latOff': clat,
        'heightOff': 0,
        'lonScale': (lonMax - lonMin) / 2,
        'latScale': (latMax - latMin) / 2,
        'heightScale': 1000,
    }
    params = RpcTransform.fit(v, u, fixed)
    T_rpc = RpcTransform.fromParams(params, fixed)
    if 1:    
        vp = T_rpc.forward(u)
        n = u.shape[1]
        rms = math.sqrt(numpy.linalg.norm(vp - v) / n)
        logging.debug('rms: %s pixels', rms)

    return T_rpc
