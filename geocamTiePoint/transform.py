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

# warnings about undefined variables within closures
# pylint: disable=E1120

# warnings about not calling parent class constructor
# pylint: disable=W0231

# warnings about not defining abstract methods from parent
# pylint: disable=W0223

import math
import numpy
from geocamTiePoint.optimize import optimize
from geocamUtil.registration import imageCoordToEcef, rotMatrixOfCameraInEcef, rotMatrixFromEcefToCamera, eulFromRot, rotFromEul
from geocamUtil.geomath import transformEcefToLonLatAlt, transformLonLatAltToEcef

# TODO: Clean up these constants!
# ORIGN_SHIFT = meters per 180 degrees!
ORIGIN_SHIFT = 2 * math.pi * (6378137 / 2.)
METERS_PER_DEGREE_LON = ORIGIN_SHIFT / 180
DEGREES_LON_PER_METER = 180 / ORIGIN_SHIFT
TILE_SIZE = 256.
INITIAL_RESOLUTION = 2 * math.pi * 6378137 / TILE_SIZE


def lonLatToMeters(lonLat):
    '''Lonlat coordinate to projected coordinate in meters'''
    lon, lat = lonLat
    mx = lon * METERS_PER_DEGREE_LON
    my = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180) # Lat correction
    my = my * METERS_PER_DEGREE_LON
    return mx, my


def metersToLatLon(mercatorPt):
    '''Projected coordinate in meters to lonlat coordinate'''
    x, y = mercatorPt
    lon = x * DEGREES_LON_PER_METER
    lat = y * DEGREES_LON_PER_METER
    lat = ((math.atan(math.exp((lat * (math.pi / 180)))) * 360) / math.pi) - 90 # Lat correction
    return lon, lat


def resolution(zoom):
    return INITIAL_RESOLUTION / (2 ** zoom)


def pixelsToMeters(x, y, zoom):
    '''Pixel coordinate to projected coordinate in meters'''
    res = resolution(zoom)
    mx =  (x * res) - ORIGIN_SHIFT
    my = -(y * res) + ORIGIN_SHIFT
    return [mx, my]


def metersToPixels(x, y, zoom):
    '''Projected coordinate in meters to pixel coordinate'''
    res = resolution(zoom)
    px = ( x + ORIGIN_SHIFT) / res
    py = (-y + ORIGIN_SHIFT) / res
    return [px, py]


def getProjectiveInverse(matrix):
    '''Compute the inverse of a projective transform matrix,
       returning the new projective transform matrix.
    http://www.cis.rit.edu/class/simg782/lectures/lecture_02/lec782_05_02.pdf (p. 33)'''
    c0 = matrix[0, 0]
    c1 = matrix[0, 1]
    c2 = matrix[0, 2]
    c3 = matrix[1, 0]
    c4 = matrix[1, 1]
    c5 = matrix[1, 2]
    c6 = matrix[2, 0]
    c7 = matrix[2, 1]
    result = numpy.array([[c4 - c5 * c7,
                           c2 * c7 - c1,
                           c1 * c5 - c2 * c4],
                          [c5 * c6 - c3,
                           c0 - c2 * c6,
                           c3 * c2 - c0 * c5],
                          [c3 * c7 - c4 * c6,
                           c1 * c6 - c0 * c7,
                           c0 * c4 - c1 * c3]])
    # normalize just for the hell of it
    result /= result[2, 2]
    return result


def closest(tgt, vals):
    '''Return the element in vals which is closest to tgt'''
    return min(vals, key=lambda v: abs(tgt - v))


def solveQuad(a, p):
    """
    Solve p = x + a x^2 for x. Over the region of interest there should
    generally be two real roots with one much closer to p than the
    other, and we prefer that one.
    """

    if a * a > 1e-20:
        discriminant = 4 * a * p + 1
        if discriminant < 0:
            return None
        h = math.sqrt(discriminant)
        roots = [(-1 + h) / (2 * a),
                 (-1 - h) / (2 * a)]
        return closest(p, roots)
    else:
        # avoid divide by zero
        return p
    

class Transform(object):
    '''Transform base class with fit function'''
    
    @classmethod
    def fit(cls, toPts, fromPts):
        '''Solve for the best transform parameters given input/output point pairs.'''
        params0 = cls.getInitParams(toPts, fromPts)
        # lambda is a function that takes "params" as argument
        # and returns the toPts calculated from fromPts and params.
        params = optimize(toPts.flatten(),
                          lambda params: forwardPts(cls.fromParams(params), fromPts).flatten(),
                          params0)
        return cls.fromParams(params)

    @classmethod
    def getInitParams(cls, toPts, fromPts):
        raise NotImplementedError('implement in derived class')

    @classmethod
    def fromParams(cls, params):
        '''Given a vector of parameters, it initializes the transform'''
        raise NotImplementedError('implement in derived class')


class CameraModelTransform(Transform):
    '''Simple pinhole camera camera model.
        The tranform functions convert between pixel coords and projected coordinates in meters'''
    def __init__(self, params, width, height, Fx, Fy):
        self.params = params
        self.width  = width
        self.height = height
        self.Fx     = Fx
        self.Fy     = Fy
        
    @classmethod
    def fit(cls, toPts, fromPts, imageId):
        # extract width and height of image.
        params0 = cls.getInitParams(toPts, fromPts, imageId)        
        height  = params0[len(params0) -1]
        width   = params0[len(params0) -2]
        Fy      = params0[len(params0) -3]
        Fx      = params0[len(params0) -4]
        numPts  = len(toPts.flatten())
        params0 = params0[:len(params0)-4]
        # optimize params
        params = optimize(toPts.flatten(),
                          lambda params: forwardPts(cls.fromParams(params, width, height, Fx, Fy), fromPts).flatten(),
                          params0)   
        return cls.fromParams(params, width, height, Fx, Fy)

    def forward(self, pt):
        '''Takes in a point in pixel coordinate and returns point in gmap units (meters)'''
        lat, lon, alt, roll, pitch, yaw = self.params
        width  = self.width
        height = self.height
        Fx     = self.Fx
        Fy     = self.Fy
        camLonLatAlt  = (lon, lat, alt)  # camera position in lon,lat,alt
        opticalCenter = (int(width / 2.0), int(height / 2.0))
        focalLength   = (Fx, Fy)
        rotMatrix     = rotFromEul(roll, pitch, yaw)
        # Convert image pixel coordinates to ecef
        ecef = imageCoordToEcef(camLonLatAlt, pt, opticalCenter, focalLength, rotMatrix) 
        try: 
            ptLonLatAlt = transformEcefToLonLatAlt(ecef)  # convert image pixel coordinates to ecef
        except:
            return None
        toPt = [ptLonLatAlt[0], ptLonLatAlt[1]]  # [lon, lat]
        xy_meters = lonLatToMeters(toPt) 
        return xy_meters

    def reverse(self, pt):
        '''Takes a point in gmap meters and converts it to image coordinates'''
        lat, lon, alt, roll, pitch, yaw = self.params  # camera parameters (location, orientation, focal length)
        width  = self.width  # image width
        height = self.height  # image height
        Fx     = self.Fx
        Fy     = self.Fy
        # convert input pt from meters to lat lon
        ptlon, ptlat = metersToLatLon([pt[0], pt[1]])
        ptalt = 0
        px, py, pz = transformLonLatAltToEcef([ptlon, ptlat, ptalt])
        pt = numpy.array([[px, py, pz, 1]]).transpose()  # convert to column vector
        cameraMatrix = numpy.matrix([[Fx,  0,  width /2.0],  # matrix of intrinsic camera parameters
                                     [0,   Fy, height/2.0],
                                     [0,   0,  1]],
                                   dtype='float64')  
        x,y,z = transformLonLatAltToEcef((lon,lat,alt))  # camera pose in ecef
        rotation = rotFromEul(roll, pitch, yaw)  # euler to matrix
        rotation = numpy.transpose(rotation)
        cameraPoseColVector = numpy.array([[x, y, z]]).transpose()
        translation = -1* rotation * cameraPoseColVector
        rotTransMat = numpy.c_[rotation, translation]  # append the translation matrix (3x1) to rotation matrix (3x3) -> becomes 3x4
        ptInImage   = cameraMatrix * rotTransMat * pt
        u = ptInImage.item(0) / ptInImage.item(2)
        v = ptInImage.item(1) / ptInImage.item(2)
        ptInImage =  [u, v]
        return ptInImage

    @classmethod
    def getInitParams(cls, toPts, fromPts, imageId):
        mission, roll, frame = imageId.split('-')
        issImage = ISSimage(mission, roll, frame, '')
        try:
            issLat = issImage.extras.nadirLat
            issLon = issImage.extras.nadirLon
            issAlt = issImage.extras.altitude
            foLenX = issImage.extras.focalLength[0]
            foLenY = issImage.extras.focalLength[1]
            camLonLatAlt = (issLon,issLat,issAlt)
            rotMatrix = rotMatrixOfCameraInEcef(issLon, transformLonLatAltToEcef(camLonLatAlt))  # initially nadir pointing
            roll, pitch, yaw = eulFromRot(rotMatrix)  # initially set to nadir rotation
            # these values are not going to be optimized. But needs to be passed to fromParams 
            # to set it as member vars.
            width = issImage.extras.width
            height = issImage.extras.height
        except Exception as e:
            print "Could not retrieve image metadata from the ISS MRF: " + str(e)
        return [issLat, issLon, issAlt, roll, pitch, yaw, foLenX, foLenY, width, height]


    @classmethod
    def fromParams(cls, params, width, height, Fx, Fy):
        # this makes params field passed from getInitParams accessible as a parameter of self!
        return cls(params, width, height, Fx, Fy)
    

class LinearTransform(Transform):
    '''Just implements a basic matrix transform.
       The input matrix must be an Nx3 numpy matrix.
       Input vectors must be 2x1 vectors.'''
    def __init__(self, matrix):
        self.matrix  = matrix
        self.inverse = None # Inverse is computed the first time in is used

    def forward(self, pt):
        u = numpy.array(list(pt) + [1], dtype='float64') # Homogenize the input point
        v = self.matrix.dot(u) # Multiply the matrix by the vector
        return v[:2].tolist()  # Return first two elements

    def reverse(self, pt):
        if self.inverse is None:
            self.inverse = numpy.linalg.inv(self.matrix)
        v = numpy.array(list(pt) + [1], dtype='float64') # Homogenize the input point
        u = self.inverse.dot(v) # Multiply the matrix by the vector
        return u[:2].tolist()   # Return first two elements

    def getJsonDict(self):
        return {'type': 'projective',
                'matrix': self.matrix.tolist()}


class TranslateTransform(LinearTransform):
    '''Implementation of transform class for translation-only.
       Input/output coordinates must by 2x1.'''
    @classmethod
    def fit(cls, toPts, fromPts):
        meanDiff = (numpy.mean(toPts, axis=0) -
                    numpy.mean(fromPts, axis=0))
        tx, ty = meanDiff

        matrix = numpy.array([[1, 0, tx],
                              [0, 1, ty],
                              [0, 0, 1]],
                             dtype='float64')
        return cls(matrix)
    
    def getJsonDict(self):
        return {'type': 'translate',
                'matrix': self.matrix.tolist()}


class RotateScaleTranslateTransform(LinearTransform):
    '''Implementation of transform class for translation/rotation/scale.
       Input/output coordinates must by 2x1.'''
    @classmethod
    def fromParams(cls, params):
        tx, ty, scale, theta = params
        translateMatrix = numpy.array([[1, 0, tx],
                                       [0, 1, ty],
                                       [0, 0, 1]],
                                      dtype='float64')
        scaleMatrix = numpy.array([[scale, 0, 0],
                                   [0, scale, 0],
                                   [0, 0, 1]],
                                  dtype='float64')
        rotateMatrix = numpy.array([[math.cos(theta), -math.sin(theta), 0],
                                    [math.sin(theta), math.cos(theta), 0],
                                    [0, 0, 1]],
                                   dtype='float64')
        matrix = translateMatrix.dot(scaleMatrix).dot(rotateMatrix)
        return cls(matrix)

    @classmethod
    def getInitParams(cls, toPts, fromPts):
        tmat = AffineTransform.fit(toPts, fromPts).matrix
        tx = tmat[0, 2]
        ty = tmat[1, 2]
        scale = tmat[0, 0] * tmat[1, 1] - tmat[1, 0] * tmat[0, 1]
        theta = math.atan2(-tmat[0, 1], tmat[0, 0])
        return [tx, ty, scale, theta]

    def getJsonDict(self):
        return {'type': 'rotate_scale',
                'matrix': self.matrix.tolist()}

class AffineTransform(LinearTransform):
    '''Implementation of transform class for affine transform.
       Input/output coordinates must by 2x1.'''
    @classmethod
    def fit(cls, toPts, fromPts):
        n = toPts.shape[0]
        V = numpy.zeros((2 * n, 1))
        U = numpy.zeros((2 * n, 6))
        for i in xrange(0, n):
            V[2 * i,     0  ] = toPts[i, 0]
            V[2 * i + 1, 0  ] = toPts[i, 1]
            U[2 * i,     0:3] = fromPts[i, 0], fromPts[i, 1], 1
            U[2 * i + 1, 3:6] = fromPts[i, 0], fromPts[i, 1], 1
        soln, _residues, _rank, _sngVals = numpy.linalg.lstsq(U, V)
        params = soln[:, 0]
        matrix = numpy.array([[params[0], params[1], params[2]],
                              [params[3], params[4], params[5]],
                              [0, 0, 1]],
                             dtype='float64')
        return cls(matrix)


class ProjectiveTransform(Transform):
    '''Implementation of Transform class for projective transforms.
       See http://www.corrmap.com/features/homography_transformation.php'''
    def __init__(self, matrix):
        self.matrix  = matrix
        self.inverse = None # Inverse matrix is computed when first used.

    def _apply(self, matrix, pt):
        u  = numpy.array(list(pt) + [1], 'd')
        v0 = matrix.dot(u)
        # projective rescaling: divide by z and truncate
        v = (v0 / v0[2])[:2]
        return v.tolist()

    def forward(self, pt):
        return self._apply(self.matrix, pt)

    def reverse(self, pt):
        if self.inverse is None:
            self.inverse = getProjectiveInverse(self.matrix)
        return self._apply(self.inverse, pt)

    @classmethod
    def fromParams(cls, params):
        matrix = numpy.append(params, 1).reshape((3, 3))
        return cls(matrix)

    @classmethod
    def getInitParams(cls, toPts, fromPts):
        tmat = AffineTransform.fit(toPts, fromPts).matrix
        return tmat.flatten()[:8]
 
    def getJsonDict(self):
        return {'type': 'projective',
                'matrix': self.matrix.tolist()}
 
class QuadraticTransform(Transform):
    '''TODO'''
    def __init__(self, matrix):
        self.matrix = matrix
 
        # there's a projective transform hiding in the quadratic
        # transform if we drop the first two columns. we use it to
        # estimate an initial value when calculating the inverse.
        self.proj = ProjectiveTransform(self.matrix[:, 2:])
 
    def _residuals(self, v, u):
        vapprox = self.forward(u)
        return (vapprox - v)
 
    def forward(self, ulist):
        u  = numpy.array([ulist[0] ** 2, ulist[1] ** 2, ulist[0], ulist[1], 1])
        v0 = self.matrix.dot(u)
        v  = (v0 / v0[2])[:2]
        return v.tolist()
 
    def reverse(self, vlist):
        v = numpy.array(vlist)
 
        # to get a rough initial value, apply the inverse of the simpler
        # projective transform. this will give the exact answer if the
        # quadratic terms happen to be 0.
        u0 = self.proj.reverse(vlist)
 
        # optimize to get an exact inverse.
        umin = optimize(v,
                        lambda u: numpy.array(self.forward(u)),
                        numpy.array(u0))
 
        return umin.tolist()
 
    def getJsonDict(self):
        return {'type': 'quadratic',
                'matrix': self.matrix.tolist()}
 
    @classmethod
    def fromParams(cls, params):
        matrix = numpy.zeros((3, 5))
        matrix[0, :  ] = params[0:5]
        matrix[1, :  ] = params[5:10]
        matrix[2, 2:4] = params[10:12]
        matrix[2, 4  ] = 1
        return cls(matrix)
 
    @classmethod
    def getInitParams(cls, toPts, fromPts):
        tmat   = AffineTransform.fit(toPts, fromPts).matrix
        params = numpy.zeros(12)
        params[ 2: 5] = tmat[0, :]
        params[ 7:10] = tmat[1, :]
        params[10:12] = tmat[2, 0:2]
        return params


class QuadraticTransform2(Transform):
    '''TODO'''
    SCALE = 1e+7

    def __init__(self, matrix, quadraticTerms):
        self.matrix = matrix
        self.quadraticTerms = quadraticTerms
        self.projInverse = None

    def forward(self, ulist):
        u = numpy.array(list(ulist) + [1])
        v0 = self.matrix.dot(u)
        v1 = (v0 / v0[2])[:2]

        x, y = v1
        a, b, c, d = self.quadraticTerms

        p = x + a * x * x
        q = y + b * y * y
        r = p + c * q * q
        s = q + d * r * r

        # correct for pre-conditioning
        r = r * self.SCALE
        s = s * self.SCALE

        return [r, s]

    def reverse(self, vlist):
        if self.projInverse is None:
            self.projInverse = getProjectiveInverse(self.matrix)

        v = numpy.array(list(vlist) + [1])

        r, s = v[:2]

        # correct for pre-conditioning
        r = r / self.SCALE
        s = s / self.SCALE

        a, b, c, d = self.quadraticTerms

        q = s - d * r * r
        p = r - c * q * q
        x0 = solveQuad(a, p)
        if x0 is None:
            return None
        y0 = solveQuad(b, q)
        if y0 is None:
            return None

        v0 = numpy.array([x0, y0, 1])
        u0 = self.projInverse.dot(v0)
        x, y = (u0 / u0[2])[:2]

        return [x, y]

    def getJsonDict(self):
        return {'type': 'quadratic',
                'matrix': self.matrix.tolist(),
                'quadraticTerms': list(self.quadraticTerms)}

    @classmethod
    def fromParams(cls, params):
        matrix = numpy.append(params[:8], 1).reshape((3, 3))
        quadTerms = params[8:]
        return cls(matrix, quadTerms)

    @classmethod
    def getInitParams(cls, toPts, fromPts):
        # pre-conditioning by SCALE improves numerical stability
        tmat = AffineTransform.fit(toPts / cls.SCALE,
                                   fromPts).matrix
        return numpy.append(tmat.flatten()[:8],
                            numpy.zeros(4))


def makeTransform(transformDict):
    '''Make a transform from a specialized dictionary object'''
    transformType = transformDict['type']
    if transformType == 'CameraModelTransform': # Handle pinhole camera model case
        params  = transformDict['params' ]
        imageId = transformDict['imageId']
        mission, roll, frame = imageId.split('-')
        issImage = ISSimage(mission, roll, frame, '')
        return CameraModelTransform(params, issImage.extras.width, issImage.extras.height,
                                    issImage.extras.focalLength[0], issImage.extras.focalLength[1])
    else: # Handle all the matrix transform cases
        transformMatrix = numpy.array(transformDict['matrix'])
        if transformType == 'projective':
            return ProjectiveTransform(transformMatrix)
        elif transformType == 'quadratic':
            return QuadraticTransform(transformMatrix)
        elif transformType == 'quadratic2':
            return QuadraticTransform2(transformMatrix,
                                       transformDict['quadraticTerms'])
        else:
            raise ValueError('unknown transform type %s, expected one of: projective, quadratic'
                             % transformType)


def forwardPts(tform, fromPts):
    '''Applies the provided forward transform to each of the input points.'''
    toPts = numpy.zeros(fromPts.shape)
    for i, pt in enumerate(fromPts):
        toPts[i, :] = tform.forward(pt)
    return toPts


def getTransformClass(n):
    '''Given the number of available tie points, decide which transform type to use.'''
    if n < 2:
        raise ValueError('not enough tie points')
    elif n == 2:
        return RotateScaleTranslateTransform
    elif n == 3:
        return AffineTransform
    elif n < 7:
        return ProjectiveTransform
    else:
        return QuadraticTransform2


def getTransform(toPts, fromPts):
    '''Find the best transform to describe to input/output point pairs.
       Inputs must be packed into numpy array objects.'''
    n   = toPts.shape[0]
    cls = getTransformClass(n)
    return cls.fit(toPts, fromPts)


def splitPoints(points):
    '''Seperate a merged input/output point list into two lists.'''
    toPts   = numpy.array([v[0:2] for v in points])
    fromPts = numpy.array([v[2:4] for v in points])
    return toPts, fromPts

