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
import json
import time
import glob
import rfc822
import urllib2
import numpy
import csv
import re
import operator

import logging
from django.core.files.base import ContentFile

import PIL.Image
import PIL.ImageEnhance

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from geocamUtil.ErrorJSONResponse import ErrorJSONResponse, checkIfErrorJSONResponse

from geocamUtil import registration as register
from geocamUtil import imageInfo

from geocamTiePoint.models import Overlay, QuadTree, ImageData, ISSimage
from django.conf import settings
from geocamTiePoint import quadTree, transform, garbage
from geocamTiePoint import anypdf as pdf

from georef_imageregistration import ImageFetcher
from georef_imageregistration import IrgStringFunctions, IrgGeoFunctions
from georef_imageregistration import register_image


"""
Globals
"""
TRANSPARENT_PNG_BINARY = '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x01sRGB\x00\xae\xce\x1c\xe9\x00\x00\x00\rIDAT\x08\xd7c````\x00\x00\x00\x05\x00\x01^\xf3*:\x00\x00\x00\x00IEND\xaeB`\x82'
DISPLAY = 2
ENHANCED = 1 
UNENHANCED = 0
_template_cache = None


"""
Misc Helpers
"""

def arraysToNdArray(xPts, yPts):
    """
    given arrays of x pts and y pts, it neatly organizes it
    into numpy ndarray of size (n,2) where each row (or is it column?)
    is a point (x,y) . 
    
    this format is what is required for to and from pts
    by the fit function in Transforms.
    """
    n = len(xPts)
    ndarray = numpy.ndarray(shape=(n,2), dtype=float)   
    for i in range(n):
        ndarray[i][0] = xPts[i]
        ndarray[i][1] = yPts[i]
    return ndarray


def ndarrayToList(ndarray):
    """
    takes an ndarray, flattens it and converts it to 
    a list object so that it is json-izable.
    """
    return list(ndarray.flatten())


def toMegaBytes(numBytes):
    return '%.1d' % (numBytes / (1024 * 1024))


def get_handlebars_templates(source):
    global _template_cache
    if settings.GEOCAM_TIE_POINT_TEMPLATE_DEBUG or not _template_cache:
        templates = {}
        for thePath in source:
            inp = os.path.join(settings.PROJ_ROOT, 'apps', thePath)
            for template_file in glob.glob(os.path.join(inp, '*.handlebars')):
                with open(template_file, 'r') as infile:
                    template_name = os.path.splitext(os.path.basename(template_file))[0]
                    templates[template_name] = infile.read()
        _template_cache = templates
    return _template_cache


def transparentPngData():
    return (TRANSPARENT_PNG_BINARY, 'image/png')


def dumps(obj):
    return json.dumps(obj, sort_keys=True, indent=4)


def export_settings(export_vars=None):
    if export_vars == None:
        export_vars = ('GEOCAM_TIE_POINT_DEFAULT_MAP_VIEWPORT',
                       'GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION',
                       'STATIC_URL',
                       )
    return dumps(dict([(k, getattr(settings, k)) for k in export_vars]))

"""
Image related stuff
"""

def getImage(imageData, flag):
    """
    Returns the PIL image object from imageData based on the flag.
    """
    image = None
    try: 
        if flag == ENHANCED:
            image = PIL.Image.open(imageData.enhancedImage.file)
        elif flag == UNENHANCED:
            image = PIL.Image.open(imageData.unenhancedImage.file)
        elif flag == DISPLAY:
            image = PIL.Image.open(imageData.image.file)
    except: 
        logging.error("image cannot be read from the image data")
        return None
    return image


def saveImageToDatabase(PILimage, imageData, flags):
    """
    Given PIL image object, saves the image bits to the imageData object.
    flags is a list that determines whether image should be saved as 
    enhancedImage, unenhancedImage, or image in the imageData object in db. 
    """
    out = StringIO()
    PILimage.save(out, format='png')
    convertedBits = out.getvalue()
    out.close()
    # the file name is dummy because it gets set to a new file name on save
    if ENHANCED in flags: 
        imageData.enhancedImage.delete()  # delete the old image
        imageData.enhancedImage.save("dummy.png", ContentFile(convertedBits), save=False)
    if UNENHANCED in flags: 
        imageData.unenhancedImage.delete()
        imageData.unenhancedImage.save("dummy.png", ContentFile(convertedBits), save=False)
    if DISPLAY in flags:
        imageData.image.delete()
        imageData.image.save("dummy.png", ContentFile(convertedBits), save=False)
    imageData.contentType = 'image/png'
    imageData.save()
    

"""
Creators
"""
def createImageData(imageFile, sizeType):
    # create new image data object to save the data to.
    contentType = imageFile.content_type
    imageData = ImageData(contentType=contentType, sizeType=sizeType, raw=True)
    bits = imageFile.file.read()
    imageContent = None
    image = None
    # handle PDFs (convert pdf to png)
    if contentType in settings.PDF_MIME_TYPES:
        if not settings.PDF_IMPORT_ENABLED:
            return None
        # convert PDF to raster image
        pngData = pdf.convertPdf(bits)
        imageContent = pngData
        imageData.contentType = 'image/png'
    else:
        try:
            image = PIL.Image.open(StringIO(bits))
        except Exception as e:  # pylint: disable=W0703
            logging.error("PIL failed to open image: " + str(e))
            return None
        if image.mode != 'RGBA':
            # add alpha channel to image for better
            # transparency handling later
            image = image.convert('RGBA')
            out = StringIO()
            image.save(out, format='png')
            convertedBits = out.getvalue()
            logging.info('converted image to RGBA')
            imageContent = convertedBits
            imageData.contentType = 'image/png'
        else:
            imageData.contentType = contentType
        if image:
            # save image width, height and sizeType
            imageSize = image.size
            imageData.width = imageSize[0]
            imageData.height = imageSize[1]
    
    imageData.image.save('dummy.png', ContentFile(imageContent), save=False)
    imageData.unenhancedImage.save('dummy.png', ContentFile(imageContent), save=False)
    imageData.save()
    return imageData


def createOverlay(author, imageFile, issImage=None, sizeType=None):
    """
    Creates an imageData object and an overlay object from the information 
    gathered from an uploaded image.
    """
    try: 
        imageData = createImageData(imageFile, sizeType)
    except: 
        raise ValueError("Could not create image data")
    #if the overlay with the image name already exists, return it.
    imageOverlays = Overlay.objects.filter(name=imageFile.name)
    if len(imageOverlays) > 0:
        return imageOverlays[0]
    # create and save new empty overlay so we can refer to it
    overlay = Overlay(author=author, isPublic=settings.GEOCAM_TIE_POINT_PUBLIC_BY_DEFAULT)
    overlay.save()
    # fill in overlay info
    overlay.name = imageFile.name
    overlay.imageData = imageData
    overlay.creator = author.first_name + ' ' + author.last_name
    # set overlay extras fields
    overlay.extras.points = []
    if issImage:
        try: 
            overlay.imageData.issMRF = issImage.mission + '-' + issImage.roll + '-' + str(issImage.frame)
            overlay.imageData.save()
        except:
            pass
        centerPtDict = register.getCenterPoint(issImage)
        overlay.centerLat = round(centerPtDict["lat"],2)
        overlay.centerLon = round(centerPtDict["lon"],2)
        overlay.nadirLat = issImage.extras.nadirLat
        overlay.nadirLon = issImage.extras.nadirLon
        ad = issImage.extras.acquisitionDate
        overlay.extras.acquisitionDate = ad[:4] + '/' + ad[4:6] + '/' + ad[6:] # convert YYYYMMDD to YYYY:MM:DD 
        at = issImage.extras.acquisitionTime
        overlay.extras.acquisitionTime = at[:2] + ':' + ad[2:4] + ':' + ad[4:6] # convert HHMMSS to HH:MM:SS
        overlay.extras.focalLength_unitless = issImage.extras.focalLength_unitless
    # save overlay to database.
    overlay.save()
    # link overlay to imagedata
    imageData.overlay = overlay
    imageData.save()
    return overlay


# def createOverlayFromFileUpload(form, author):
#     # 10% "grace period" on max import file size
#     imageFileField = form.cleaned_data['image']
#     if ImageFileField: 
#         if imageFileField.size > settings.MAX_IMPORT_FILE_SIZE * 1.1:
#             return ErrorJSONResponse("Your overlay image is %s MB, larger than the maximum allowed size of %s MB."
#                                      % (toMegaBytes(imageRef.size),
#                                         toMegaBytes(settings.MAX_IMPORT_FILE_SIZE)))
#         overlay = createOverlay(author, imageFileField)
#         return overlay
#     else: 
#         return ErrorJSONResponse("imageFileField not valid")
# 
# 
# def createOverlayFromURL(form, author):
#     imageUrl = form.cleaned_data['imageUrl']
#     imageFile = imageInfo.getImageFile(imageUrl)
#     overlay = createOverlay(author, imageFile, issImage)
#     return overlay


def createOverlayFromID(mission, roll, frame, sizeType, author):
    try:
        # this is the only case where we can calculate the initial center point.
        issImage = ISSimage(mission, roll, frame, sizeType)
        imageUrl = issImage.imageUrl
        # get image data from url
        imageFile = imageInfo.getImageFile(imageUrl)
        overlay = createOverlay(author, imageFile, issImage, sizeType)
    except: 
        raise ValueError("Could not create overlay from ID")
    return overlay, issImage


"""
Image enhancement 
"""
def autoenhance(im): 
    """
    Takes in PIL image and does histogram matching.
    """
    h = im.convert("L").histogram()
    lut = []
    for b in range(0, len(h), 256):
        # step size
        step = reduce(operator.add, h[b:b+256]) / 255
        # create equalization lookup table
        n = 0
        for i in range(256):
            lut.append(n / step)
            n = n + h[i+b]
    # map image through lookup table
    layers = 4 # RGBA
    return im.point(lut*layers)


def applyEnhancement(imageData):
    """
    Apply enhancements based on enhancement values in the imageData object.
    """
    originalImage = getImage(imageData, UNENHANCED)
    if imageData.autoenhance == True:
        enhancedIm = autoenhance(originalImage)
    saveImageToDatabase(enhancedIm, imageData, [ENHANCED, DISPLAY])


def saveEnhancementValToDB(imageData, enhanceType, value):
    """
    Given type of the enhancement, stores the value in appropriate 
    enhancement parameter inside image data.
    """
    if enhanceType == 'autoenhance':
        imageData.autoenhance = True
        imageData.contrast = 0
        imageData.brightness = 0
    imageData.save()
