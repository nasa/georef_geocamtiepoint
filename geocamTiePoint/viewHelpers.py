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


def getPILimage(imageData):
    try: 
        image = PIL.Image.open(imageData.image.file) 
    except: 
        logging.error("image cannot be read from the image data")
        return None
    return image


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
Rotation
"""
def getRotatedImageData(overlayId, totalRotation):
    """
    For Re-using image data that already exists in the db. 
     
    Searches thru image data objects to find the one
    that has the given rotation value. If that doesn't exist, 
    returns None
    """
    imagedata = ImageData.objects.filter(overlay__key = overlayId).filter(rotationAngle = totalRotation)
    if imagedata:
        imagedata = imagedata[0]
        return imagedata
    else:
        return None


"""
Autoregistration
"""

def registerImage(overlay):
    """
    Runs automatic registration (c++ function) on the given ISS image.
    """
    imagePath = None
    focalLength = None
    imageData = overlay.imageData
    if imageData:
        imagePath = imageData.image.url.replace('/data/', settings.DATA_ROOT)
    else: 
        print "Error: Cannot get image path!"
        return None
    centerLat = overlay.extras.centerLat
    centerLon = overlay.extras.centerLon
    focalLength = overlay.extras.focalLength_unitless
    acq_date = overlay.extras.acquisitionDate
    acq_date = acq_date[:4] + '.' + acq_date[4:6] + '.' + acq_date[6:] # convert YYYYMMDD to this YYYY.MM.DD 
    try: 
        refImagePath = None
        referenceGeoTransform = None
        debug = True
        force = False
        slowMethod = True
        (imageToProjectedTransform, confidence, imageInliers, gdcInliers) = register_image.register_image(imagePath, centerLon, centerLat,
                                                                                                          focalLength, acq_date, refImagePath, 
                                                                                                          referenceGeoTransform, debug, force, slowMethod)
    except:
        return ErrorJSONResponse("Failed to compute transform. Please again try without the autoregister option.")
    overlay.extras.transform = imageToProjectedTransform.getJsonDict()
    overlay.generateAlignedQuadTree()
    overlay.save()


"""
Creators
"""
def createImageData(imageFile):
    # create new image data object to save the data to.
    contentType = imageFile.content_type
    imageData = ImageData(contentType=contentType)
    bits = imageFile.file.read()
    imageContent = None
    image = None
    # handle PDFs (convert pdf to png)
    if contentType in settings.PDF_MIME_TYPES:
        if not settings.PDF_IMPORT_ENABLED:
            return ErrorJSONResponse("PDF images are no longer supported.")
        # convert PDF to raster image
        pngData = pdf.convertPdf(bits)
        imageContent = pngData
        imageData.contentType = 'image/png'
    else:
        try:
            image = PIL.Image.open(StringIO(bits))
        except Exception as e:  # pylint: disable=W0703
            logging.error("PIL failed to open image: " + str(e))
            return ErrorJSONResponse("There was a problem reading the image.")
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
    imageData.image.save('dummy.png', ContentFile(imageContent), save=False)
    imageData.unenhancedImage.save('dummy.png', ContentFile(imageContent), save=False)
    # set this image data as the raw image.
    imageData.raw = True
    
    imageData.save()
    return [imageData, image.size]


def createOverlay(author, imageFile, issImage=None):
    """
    Creates an imageData object and an overlay object from the information 
    gathered from an uploaded image.
    """
    imageData, widthHeight = createImageData(imageFile)
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
    overlay.extras.totalRotation = 0 # set initial rotation value to 0
    overlay.extras.imageSize = widthHeight
    if issImage:
        try: 
            overlay.imageData.issMRF = issImage.mission + '-' + issImage.roll + '-' + str(issImage.frame)
            overlay.imageData.save()
        except:
            pass
        centerPtDict = register.getCenterPoint(issImage)
        overlay.extras.centerLat = round(centerPtDict["lat"],2)
        overlay.extras.centerLon = round(centerPtDict["lon"],2)
        overlay.extras.nadirLat = issImage.extras.nadirLat
        overlay.extras.nadirLon = issImage.extras.nadirLon
        ad = issImage.extras.acquisitionDate
        overlay.extras.acquisitionDate = ad[:4] + ':' + ad[4:6] + ':' + ad[6:] # convert YYYYMMDD to YYYY:MM:DD 
        at = issImage.extras.acquisitionTime
        overlay.extras.acquisitionTime = at[:2] + ':' + ad[2:4] + ':' + ad[4:6] # convert HHMMSS to HH:MM:SS
        overlay.extras.focalLength_unitless = issImage.extras.focalLength_unitless
    # save overlay to database.
    overlay.save()
    # link overlay to imagedata
    imageData.overlay = overlay
    imageData.save()
    return overlay


def createOverlayFromFileUpload(form, author):
    # 10% "grace period" on max import file size
    imageFileField = form.cleaned_data['image']
    if ImageFileField: 
        if imageFileField.size > settings.MAX_IMPORT_FILE_SIZE * 1.1:
            return ErrorJSONResponse("Your overlay image is %s MB, larger than the maximum allowed size of %s MB."
                                     % (toMegaBytes(imageRef.size),
                                        toMegaBytes(settings.MAX_IMPORT_FILE_SIZE)))
        overlay = createOverlay(author, imageFileField)
        return overlay
    else: 
        return ErrorJSONResponse("imageFileField not valid")


def createOverlayFromID(form, author):
    # this is the only case where we can calculate the initial center point.
    mission = form.cleaned_data['mission']
    roll = form.cleaned_data['roll']
    frame = form.cleaned_data['frame']
    sizeType = form.cleaned_data['imageSize']  # small or large
    issImage = ISSimage(mission, roll, frame, sizeType)
    imageUrl = issImage.imageUrl
    # get image data from url
    imageFile = imageInfo.getImageFile(imageUrl)
    overlay = createOverlay(author, imageFile, issImage)
    return overlay, issImage
    

def createOverlayFromURL(form, author):
    imageUrl = form.cleaned_data['imageUrl']
    imageFile = imageInfo.getImageFile(imageUrl)
    overlay = createOverlay(author, imageFile, issImage)
    return overlay


"""
Image enhancement 
"""
def getEnhancer(type):
    """
    Given image enhancement type, returns the PIL's enhancer.
    """
    if type == u'contrast':
        return PIL.ImageEnhance.Contrast
    elif type == u'brightness':
        return PIL.ImageEnhance.Brightness
    else: 
        logging.error("invalid type provided for image enhancer")
        return None
    

def enhanceImage(enhanceType, value, im):
    """
    Processes image thru an enhancer and returns an enhanced image.
    enhanceType specifies whether it's 'contrast' or 'brightness' 
    operation. value is input to the enhancer. im is the input image.
    """
    # enhance the image
    enhancer = getEnhancer(enhanceType)
    enhancer = enhancer(im)
    enhancedIm = enhancer.enhance(value) 
    return enhancedIm


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


def checkAndApplyEnhancement(imageData, enhanceType):
    """
    Apply the image enhancement, save image, and set this new image as a display image
    """
    originalImage = getImage(imageData, UNENHANCED)
    if enhanceType == 'autoenhance':
        enhancedIm = autoenhance(originalImage)
    elif enhanceType == 'undo':
        enhancedIm = originalImage
    else:
        enhancedIm = originalImage
        if imageData.contrast != 0:
            enhancedIm = enhanceImage("contrast", imageData.contrast, enhancedIm)
        if imageData.brightness != 0:
            enhancedIm = enhanceImage("brightness", imageData.brightness, enhancedIm)
    saveImageToDatabase(enhancedIm, imageData, [ENHANCED, DISPLAY])
    
    
def saveImageToDatabase(PILimage, imageData, flags):
    """
    Given PIL image object, saves the image bits to the imageData object.
    flags is a list that determines whether image should be saved as 
    enhancedImage, unenhancedImage, or image in the imageData object in db. 
    """
    out = StringIO()
    PILimage.save(out, format='png')
    convertedBits = out.getvalue()
    # the file name is dummy because it gets set to a new file name on save
    if ENHANCED in flags: 
        imageData.enhancedImage.save("dummy.jpg", ContentFile(convertedBits), save=False)
    if UNENHANCED in flags: 
        imageData.unenhancedImage.save("dummy.jpg", ContentFile(convertedBits), save=False)
    if DISPLAY in flags:
        imageData.image.save("dummy.jpg", ContentFile(convertedBits), save=False)
    imageData.contentType = 'image/png'
    imageData.save()


def saveEnhancementValToDB(imageData, enhanceType, value):
    """
    Given type of the enhancement, stores the value in appropriate 
    enhancement parameter inside image data.
    """
    if enhanceType == 'autoenhance':
        imageData.autoenhance = True
        imageData.contrast = 0
        imageData.brightness = 0
    elif enhanceType == 'undo':
        imageData.autoenhance = False
        imageData.contrast = 0
        imageData.brightness = 0
    elif enhanceType == 'contrast':
        imageData.contrast = value
        imageData.autoenhance = False
    elif enhanceType == 'brightness':
        imageData.brightness = value
        imageData.autoenhance = False
    imageData.save()
