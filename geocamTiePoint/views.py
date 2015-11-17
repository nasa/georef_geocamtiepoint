# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os
import json
import logging
import time
import glob
import rfc822
import urllib2
import numpy
import csv

from fileinput import filename
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import PIL.Image
import PIL.ImageEnhance

from django.shortcuts import render_to_response
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotFound
from django.http import HttpResponseNotAllowed, Http404
from django.template import RequestContext
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.core.urlresolvers import reverse
from django.core.files.base import ContentFile
from django.core.files import File
from django.db import transaction
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.decorators import login_required

from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save, post_delete

from geocamTiePoint import forms, settings
from geocamTiePoint.models import Overlay, QuadTree, ImageData, ISSimage
from geocamTiePoint import quadTree, transform, garbage
from geocamTiePoint import anypdf as pdf
from geocamUtil import registration as register
from geocamUtil import imageInfo as imageInfo
from geocamUtil.ErrorJSONResponse import ErrorJSONResponse, checkIfErrorJSONResponse
from geocamUtil.icons import rotate
import re

if settings.USING_APP_ENGINE:
    from google.appengine.api import backends
    from google.appengine.api import taskqueue

TRANSPARENT_PNG_BINARY = '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x01sRGB\x00\xae\xce\x1c\xe9\x00\x00\x00\rIDAT\x08\xd7c````\x00\x00\x00\x05\x00\x01^\xf3*:\x00\x00\x00\x00IEND\xaeB`\x82'

PDF_MIME_TYPES = ('application/pdf',
                  'application/acrobat',
                  'application/nappdf',
                  'application/x-pdf',
                  'application/vnd.pdf',
                  'text/pdf',
                  'text/x-pdf',
                  )

DISPLAY = 2
ENHANCED = 1 
UNENHANCED = 0

_template_cache = None


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


@login_required
def backbone(request):
    initial_overlays = Overlay.objects.order_by('pk')
    templates = get_handlebars_templates(settings.GEOCAM_TIE_POINT_HANDLEBARS_DIR)
    
    if request.method == 'GET':
        return render_to_response('geocamTiePoint/backbone.html',
            {
                'templates': templates,
                'initial_overlays_json': dumps(list(o.jsonDict for o in initial_overlays)) if initial_overlays else [],
                'settings': export_settings(),
                'cameraModelTransformFitUrl': reverse('geocamTiePoint_cameraModelTransformFit'), 
                'cameraModelTransformForwardUrl': reverse('geocamTiePoint_cameraModelTransformForward'), 
                'rotateOverlayUrl': reverse('geocamTiePoint_rotateOverlay'),
                'enhanceImageUrl': reverse('geocamTiePoint_createEnhancedImageTiles'),
            },
            context_instance=RequestContext(request))
    else:
        return HttpResponseNotAllowed(['GET'])


def overlayDelete(request, key):
    if request.method == 'GET':
        overlay = get_object_or_404(Overlay, key=key)
        return render_to_response('geocamTiePoint/overlay-delete.html',
                                  {'overlay': overlay,
                                   'overlayJson': dumps(overlay.jsonDict)},
                                  context_instance=RequestContext(request))
    elif request.method == 'POST':
        overlay = get_object_or_404(Overlay, key=key)
        overlay.delete()
        return HttpResponseRedirect(reverse('geocamTiePoint_overlayIndex'))
        

def toMegaBytes(numBytes):
    return '%.1d' % (numBytes / (1024 * 1024))


class FieldFileLike(object):
    """
    Given a file-like object, vaguely simulate a Django FieldFile.
    """
    def __init__(self, f, content_type):
        self.file = f
        self.content_type = content_type


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


# def getImage(imageData, flag):
#     """
#     Returns the PIL image object from imageData based on the flag.
#     """
#     image = None
#     try: 
#         if flag == ENHANCED:
#             image = PIL.Image.open(imageData.enhancedImage.file)
#         elif flag == UNENHANCED:
#             image = PIL.Image.open(imageData.unenhancedImage.file)
#         elif flag == DISPLAY:
#             image = PIL.Image.open(imageData.image.file)
#     except: 
#         logging.error("image cannot be read from the image data")
#         return None
#     return image

def getPILimage(imageData):
    try: 
        image = PIL.Image.open(imageData.image.file) 
    except: 
        logging.error("image cannot be read from the image data")
        return None
    return image


# def getRotatedImageData(overlayId, totalRotation):
#     """
#     For Re-using image data that already exists in the db. 
#     
#     Searches thru image data objects to find the one
#     that has the given rotation value. If that doesn't exist, 
#     returns None
#     """
#     imagedata = ImageData.objects.filter(overlay__key = overlayId).filter(rotationAngle = totalRotation)
#     if imagedata:
#         imagedata = imagedata[0]
#         return imagedata
#     else:
#         return None

# def saveImageToDatabase(PILimage, imageData, flags):
#     """
#     Given PIL image object, saves the image bits to the imageData object.
#     flags is a list that determines whether image should be saved as 
#     enhancedImage, unenhancedImage, or image in the imageData object in db. 
#     """
#     out = StringIO()
#     PILimage.save(out, format='png')
#     convertedBits = out.getvalue()
#     # the file name is dummy because it gets set to a new file name on save
#     if ENHANCED in flags: 
#         imageData.enhancedImage.save("dummy.jpg", ContentFile(convertedBits), save=False)
#     if UNENHANCED in flags: 
#         imageData.unenhancedImage.save("dummy.jpg", ContentFile(convertedBits), save=False)
#     if DISPLAY in flags:
#         imageData.image.save("dummy.jpg", ContentFile(convertedBits), save=False)
#     imageData.contentType = 'image/png'
#     imageData.save()


# def saveEnhancementValToDB(imageData, enhancementType, value):
#     """
#     Given type of the enhancement, stores the value in appropriate 
#     enhancement parameter inside image data.
#     """
#     if enhancementType == "contrast":
#         imageData.contrast = value
#     elif enhancementType == "brightness":
#         imageData.brightness = value
#     imageData.save()
# 
# 
# def getEnhanceValue(enhanceType, imageData):
#     """
#     Given enhancement type, returns the value stored in imageData object.
#     """
#     if enhanceType == "contrast":
#         return imageData.contrast
#     elif enhanceType == "brightness":
#         return imageData.brightness
# 
# 
# def getEnhancer(type):
#     """
#     Given image enhancement type, returns the PIL's enhancer.
#     """
#     if type == u'contrast':
#         return PIL.ImageEnhance.Contrast
#     elif type == u'brightness':
#         return PIL.ImageEnhance.Brightness
#     else: 
#         logging.error("invalid type provided for image enhancer")
#         return None
# 
# 
# def enhanceImage(enhanceType, value, im):
#     """
#     Processes image thru an enhancer and returns an enhanced image.
#     enhanceType specifies whether it's 'contrast' or 'brightness' 
#     operation. value is input to the enhancer. im is the input image.
#     """
#     # enhance the image
#     enhancer = getEnhancer(enhanceType)
#     enhancer = enhancer(im)
#     enhancedIm = enhancer.enhance(value) 
#     return enhancedIm

 
@csrf_exempt
def createEnhancedImageTiles(request):
    """
    Receives request from the client to enhance the images. The
    type of enhancement and value are specified in the 'data' json
    package from client.
    """
    if request.is_ajax() and request.method == 'POST':
        data = request.POST
#         value = data['value']
#         value = float(value)
        overlayId = data["overlayId"]
        overlay = Overlay.objects.get(key=overlayId)
#         previousQuadTree = None
#         if overlay.imageData.isOriginal != True: 
#             previousQuadTree = overlay.unalignedQuadTree
#         imageData = overlay.imageData
#         enhanceType = data['enhanceType']
#         # save the new enhancement value only for 'enhanceType' in database
#         saveEnhancementValToDB(imageData, enhanceType, value)   
#         checkAndApplyEnhancement(imageData)     
#         overlay.imageData.save()
#         overlay.save()
#         overlay.generateUnalignedQuadTree()  # generate tiles
#         if previousQuadTree != None:
#             previousQuadTree.delete()  # delete the old tiles
        data = {'status': 'success', 'id': overlay.key}
        return HttpResponse(json.dumps(data))


# def checkAndApplyEnhancement(imageData):
#     """
#     If any of the imageData's enhancement parameters (contrast, brightness)
#     are non-zero, apply the enhancement to the unenhanced image and set it as the 'image' field
#     of imageData
#     """
#     unenhancedIm = getImage(imageData, UNENHANCED)
#     enhancedIm = unenhancedIm
#     saveToDB = False
#     if imageData.contrast != 0:
#         enhancedIm = enhanceImage("contrast", imageData.contrast, enhancedIm)
#         saveToDB = True
#     if imageData.brightness != 0:
#         enhancedIm = enhanceImage("brightness", imageData.brightness, enhancedIm)
#         saveToDB = True
#     if saveToDB:
#         saveImageToDatabase(enhancedIm, imageData, [ENHANCED, DISPLAY])
   

@csrf_exempt
def rotateOverlay(request):
    """
    Called in response to the ajax request sent from the client when 
    user moves the rotation slider or inputs rotation. 

    re renders page with rotated image.
    """
    if request.is_ajax() and request.method == 'POST':
        data = request.POST
        # get the rotation angle input from the user
        rotationAngle = data["rotation"]        
        rotationAngle = int(rotationAngle) # convert str to int
        # get the id of the current overlay
        overlayId = data["overlayId"]
        # get the overlay object
        overlay = Overlay.objects.get(key=overlayId)
        # add the user's new rotation request to the total rotation
        overlay.extras.totalRotation = rotationAngle
        # original image uploaded by the user
        rawImageData = overlay.getRawImageData()
        rawPILimage = getPILimage(rawImageData)
        # save out the original image size
        overlay.extras.orgImageSize = rawPILimage.size
        #rotate the image (minus sign since PIL rotates counter clockwise)
        rotatedImage = rawPILimage.rotate(-1*overlay.extras.totalRotation, 
                                            PIL.Image.BICUBIC, expand=1)
        # data that needs to be deleted after overlay save
        isRaw = overlay.imageData.raw
        previousImageDataId = overlay.imageData.id
        previousQuadTreeId = overlay.unalignedQuadTree.id
        # create a new image data object with new image
        newImageData = overlay.imageData
        newImageData.pk = None
        newImageData.raw = False
        # save the rotated image to the new ImageData object
        out = StringIO()
        rotatedImage.save(out, format='png')
        convertedBits = out.getvalue()
        newImageData.image.save("dummy.jpg", ContentFile(convertedBits), save=False)
        newImageData.contentType = 'image/png'
        newImageData.rotationAngle = overlay.extras.totalRotation
        newImageData.save()
        # replace the imageData of overlay
        overlay.imageData = newImageData
        overlay.extras.rotatedImageSize = rotatedImage.size
        overlay.save()
        # generate new set of tiles
        overlay.generateUnalignedQuadTree()
        
        if not isRaw:
            QuadTree.objects.get(id=previousQuadTreeId).delete()
            ImageData.objects.get(id=previousImageDataId).delete()
        
        data = {'status': 'success', 'id': overlay.key}
        return HttpResponse(json.dumps(data))
        

@csrf_exempt
def cameraModelTransformFit(request):
    """
    Handles the call from the client side, which is sent 
    when "CameraModelTransform.fit" is called from transform.js. 
    Returns the optimized parameters returned by 'fit' in the CameraModelTransform class. 
    """ 
    if request.is_ajax() and request.method == 'POST':
        data = request.POST
        toPtsX = []
        toPtsY = []
        fromPtsX = []
        fromPtsY = []
        issImageId = ""
        for key, value in data.iterlists():
            if 'imageId' in key:
                issImageId = value[0] # want the str, not the list.
            elif 'toPts[0][]' == key:
                toPtsX = value
            elif 'toPts[1][]' == key:
                toPtsY = value
            elif 'fromPts[0][]' in key:
                fromPtsX = value
            elif 'fromPts[1][]' in key:
                fromPtsY = value
        toPts = arraysToNdArray(toPtsX, toPtsY)
        fromPts = arraysToNdArray(fromPtsX, fromPtsY)
        tform = transform.CameraModelTransform.fit(toPts, fromPts, issImageId)
        params = tform.params
        params = ndarrayToList(params)
        return HttpResponse(json.dumps({'params': params}), content_type="application/json")
    else: 
        return HttpResponse(json.dumps({'Status': "error"}), content_type="application/json")


@csrf_exempt
def cameraModelTransformForward(request):
    if request.is_ajax() and request.method == 'POST':
        data = request.POST
        pt = data.getlist('pt[]', None)
        params = data.getlist('params[]', None)
        issMRF = data.get('imageId', None)
        mission, roll, frame = issMRF.split('-')
        imageMetaData = imageInfo.getIssImageInfo(mission, roll, frame)
        # get the width and height from imageId
        width = imageMetaData['width']
        height = imageMetaData['height']
        Fx = imageMetaData['focalLength'][0]
        Fy = imageMetaData['focalLength'][1]
        # create a new transform and set its params, width, and height
        params = [float(param) for param in params]  # convert params from unicode to float.
        pt = [float(c) for c in pt]  # convert pt from unicode to float.
        tform = transform.CameraModelTransform(params, width, height, Fx, Fy)
        # call forward on it
        meters = tform.forward(pt)
        return HttpResponse(json.dumps({'meters': meters}), content_type="application/json")
    else: 
        return HttpResponse(json.dumps({'Status': "error"}), content_type="application/json")


@transaction.commit_on_success
def createOverlay(author, imageName, imageFB, imageType, issImage): #mission, roll, frame, sizeType):
    """
    Creates a imageData object and an overlay object from the information 
    gathered from an uploaded image.
    """    
    #if the overlay with the image name already exists, return it.
    imageOverlays = Overlay.objects.filter(name=imageName)
    if len(imageOverlays) > 0:
        return imageOverlays[0]
    
    imageData = ImageData(contentType=imageType)
    bits = imageFB.read()
    imageContent = None
    image = None
    if imageType in PDF_MIME_TYPES:
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
            imageData.contentType = imageType
    imageData.image.save('dummy.png', ContentFile(imageContent), save=False)

#     imageData.unenhancedImage.save('dummy.png', ContentFile(imageContent), save=False)

    # create and save new empty overlay so we can refer to it
    # this causes a ValueError if the user isn't logged in
    overlay = Overlay(author=author,
                             isPublic=settings.GEOCAM_TIE_POINT_PUBLIC_BY_DEFAULT)
    overlay.save()
    imageData.overlay = overlay
    
    # set this image data as the raw image.
    imageData.raw = True
    imageData.save()

    if image is None:
        image = PIL.Image.open(imageData.image.file)

    # fill in overlay info
    overlay.name = imageName
    overlay.imageData = imageData
    overlay.extras.points = []
    overlay.extras.imageSize = image.size    
    overlay.extras.totalRotation = 0 # set initial rotation value to 0
    width, height = image.size
    # set center point
    if issImage:
        centerPtDict = register.getCenterPoint(width, height, issImage)
        overlay.extras.centerPointLatLon = [round(centerPtDict["lat"],2), round(centerPtDict["lon"],2)]
        overlay.issMRF = issImage.mission + '-' + issImage.roll + '-' + str(issImage.frame)
    overlay.save()
    
    # generate initial quad tree
    overlay.generateUnalignedQuadTree()
    return overlay


def createOverlayFromUrl(request, mission, roll, frame, size):
    """
    HttpRequest sent, which then constructs a url to pull the image
    from. It converts the image into an overlay and saves it to the database.
    At the end, it renders the overlay edit page. 
    """
    imageUrl = None
    imageName = None
    imageFB = None
    imageType = None
    overlay = None
      
    issImage = ISSimage(mission, roll, frame, size)
    imageUrl = issImage.imageUrl
    retval = imageInfo.getImageDataFromImageUrl(imageUrl)
    if checkIfErrorJSONResponse(retval):
        return retval
    else:
        imageName, imageFB, imageType, imageId = retval
     
    overlay = createOverlay(request.user, imageName, imageFB, imageType, issImage)
    # check if createOverlay returned a ErrorJSONResponse (if so, return right away)
    if checkIfErrorJSONResponse(overlay):
        return retval
             
    redirectUrl = "b/#overlay/" + str(overlay.key) + "/edit"
    return HttpResponseRedirect(settings.SCRIPT_NAME + redirectUrl)


@transaction.commit_on_success
def overlayNewJSON(request):
    if request.method == 'POST':
        form = forms.NewImageDataForm(request.POST, request.FILES)
        if not form.is_valid():
            return ErrorJSONResponse(form.errors)
        else:
            image = None
            imageRef = form.cleaned_data['image']
            imageFB = None
            imageType = None
            imageName = None
            issImage = None
            # test to see if there is an image file
            if imageRef:
                # file takes precedence over image url
                imageFB = imageRef.file
                imageType = imageRef.content_type
                imageName = imageRef.name
                imageSize = imageRef.size
                # 10% "grace period" on max import file size
                if imageSize > settings.MAX_IMPORT_FILE_SIZE * 1.1:
                    return ErrorJSONResponse("Your overlay image is %s MB, larger than the maximum allowed size of %s MB."
                                             % (toMegaBytes(imageSize),
                                                toMegaBytes(settings.MAX_IMPORT_FILE_SIZE)))
            else:
                # no image, proceed to check for url
                imageUrl = form.cleaned_data['imageUrl']
                if not imageUrl:
                    # no image url, proceed to check for mission, roll, and frame
                    mission = form.cleaned_data['mission']
                    roll = form.cleaned_data['roll']
                    frame = form.cleaned_data['frame']
                    sizeType = form.cleaned_data['imageSize']  # small or large
                    # if user didn't input anything, error.
                    if not (mission and roll and frame): 
                        # what did the user even do
                        return ErrorJSONResponse("No image url or mission id in returned form data")
                    # get image url from mission roll frame input
                    issImage = ISSimage(mission, roll, frame, sizeType)
                # get image data from url
                retval = imageInfo.getImageDataFromImageUrl(issImage.imageUrl)
                if checkIfErrorJSONResponse(retval):
                    return retval
                else:
                    imageName, imageFB, imageType, imageId = retval
#                 # if mission wasn't set by the user, get it from imageId in url.
#                 if not issImage.mission:  
#                     if imageId: 
#                         mission, roll, frame = imageId.split('-')
#                         frame = frame.split('.')[0]
            overlay = createOverlay(request.user, imageName, imageFB, imageType, issImage)
            # check if createOverlay returned a ErrorJSONResponse (if so, return right away)
            if checkIfErrorJSONResponse(overlay):
                return retval
            # respond with json
            data = {'status': 'success', 'id': overlay.key}
            return HttpResponse(json.dumps(data))
    else:
        return HttpResponseNotAllowed(('POST'))



@csrf_exempt
def overlayIdJson(request, key):
    if request.method == 'GET':
        overlay = get_object_or_404(Overlay, key=key)
        return HttpResponse(dumps(overlay.jsonDict), content_type='application/json')
    elif request.method in ('POST', 'PUT'):
        overlay = get_object_or_404(Overlay, key=key)
        overlay.jsonDict = json.loads(request.body)
        transformDict = overlay.extras.get('transform')
        if transformDict:
            try: 
                overlay.extras.bounds = (quadTree.imageMapBounds
                                         (overlay.extras.imageSize,
                                          transform.makeTransform(transformDict)))
                overlay.generateAlignedQuadTree()
            except:
                # could not generate aligned quad tree from opimized params
                return HttpResponse(dumps(overlay.jsonDict), content_type='application/json')        
        overlay.save()
        return HttpResponse(dumps(overlay.jsonDict), content_type='application/json')
    elif request.method == 'DELETE':
        get_object_or_404(Overlay, pk=key).delete()
        return HttpResponse("OK")
    else:
        return HttpResponseNotAllowed(['GET', 'POST', 'PUT', 'DELETE'])


@csrf_exempt
def overlayListJson(request):
    # return only the last 100 overlays for now.  if it gets longer than that, we'll implement paging.
    overlays = Overlay.objects.order_by('-lastModifiedTime')[:100]
    return HttpResponse(dumps(list(o.jsonDict for o in overlays)), content_type='application/json')


def overlayIdImageFileName(request, key, fileName):
    if request.method == 'GET':
        overlay = get_object_or_404(Overlay, key=key)
        fobject = overlay.imageData.image.file
        response = HttpResponse(fobject.read(), content_type=overlay.imageData.contentType)
        return response
    else:
        return HttpResponseNotAllowed(['GET'])


def getTileData(quadTreeId, zoom, x, y):
    gen = QuadTree.getGeneratorWithCache(quadTreeId)
    try:
        return gen.getTileData(zoom, x, y)
    except quadTree.ZoomTooBig:
        return transparentPngData()
    except quadTree.OutOfBounds:
        return transparentPngData()


def neverExpires(response):
    """
    Manually sets the HTTP 'Expires' header one year in the
    future. Normally the Django cache middleware handles this, but we
    are directly using the low-level cache API.

    Empirically, this *hugely* reduces the number of requests from the
    Google Maps API. One example is that zooming out one level stupidly
    loads all the tiles in the new zoom level twice if tiles immediately
    expire.
    """
    response['Expires'] = rfc822.formatdate(time.time() + 365 * 24 * 60 * 60)
    return response


def getTile(request, quadTreeId, zoom, x, y):
    quadTreeId = int(quadTreeId)
    zoom = int(zoom)
    x = int(x)
    y = int(os.path.splitext(y)[0])
    
    key = quadTree.getTileCacheKey(quadTreeId, zoom, x, y)
    data = cache.get(key)
    if data is None:
        logging.info('\ngetTile MISS %s\n', key)
        data = getTileData(quadTreeId, zoom, x, y)
        cache.set(key, data)
    else:
        logging.info('getTile hit %s', key)

    bits, contentType = data
    response = HttpResponse(bits, content_type=contentType)
    return neverExpires(response)


def getPublicTile(request, quadTreeId, zoom, x, y):
    cacheKey = 'geocamTiePoint.QuadTree.isPublic.%s' % quadTreeId
    quadTreeIsPublic = cache.get(cacheKey)
    if quadTreeIsPublic is None:
        logging.info('getPublicTile MISS %s', cacheKey)
        try:
            q = QuadTree.objects.get(id=quadTreeId)
            overlay = q.alignedOverlays.get()
        except ObjectDoesNotExist:
            overlay = None
        if overlay:
            quadTreeIsPublic = overlay.isPublic
        else:
            quadTreeIsPublic = False
        cache.set(cacheKey, quadTreeIsPublic, 60)
    else:
        logging.info('getPublicTile hit %s', cacheKey)

    if quadTreeIsPublic:
        return getTile(request, quadTreeId, zoom, x, y)
    else:
        return HttpResponseNotFound('QuadTree %s does not exist or is not public'
                                    % quadTreeId)


def dummyView(*args, **kwargs):
    return HttpResponseNotFound()


@csrf_exempt
def overlayGenerateExport(request, key, type):
    if request.method == 'GET':
        return (HttpResponse
                ('<form action="." method="post">'
                 + '<input type="submit" name="submit"'
                 + ' value="Create Export Archive"/>'
                 + '</form>'))
    elif request.method == 'POST':
        if settings.USING_APP_ENGINE:
            onFrontEndInstance = (backends.get_backend() == None)
            if onFrontEndInstance:
                # on app engine, quadTree generation may take too long
                # for a frontend instance, so we pass it to a backend
                taskqueue.add(url='/backend' + request.path,
                              target='processing')
                return HttpResponse('{"result": "ok"}',
                                    content_type='application/json')
        overlay = get_object_or_404(Overlay, key=key)
        if type == 'html':
            overlay.generateHtmlExport()
        elif type == 'kml':
            overlay.generateKmlExport()
        elif type == 'geotiff':
            overlay.generateGeotiffExport()
        else: 
            return HttpResponse('{"result": "error! Export type invalid."}',
                            content_type='application/json')
 
        return HttpResponse('{"result": "ok"}',
                            content_type='application/json')
    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


def overlayExport(request, key, type, fname):
    """
    Displays the generated exports.
    """
    if request.method == 'GET':
        overlay = get_object_or_404(Overlay, key=key)
        if type == 'html': 
            if not (overlay.alignedQuadTree and overlay.alignedQuadTree.htmlExport):
                raise Http404('no export archive generated for requested overlay yet')
            return HttpResponse(overlay.alignedQuadTree.htmlExport.file.read(),
                                content_type='application/x-tgz')
        elif type == 'kml':
            if not (overlay.alignedQuadTree and overlay.alignedQuadTree.kmlExport):
                raise Http404('no export archive generated for requested overlay yet')
            return HttpResponse(overlay.alignedQuadTree.kmlExport.file.read(),
                                content_type='application/x-tgz')
        elif type == 'geotiff':
            if not (overlay.alignedQuadTree and overlay.alignedQuadTree.geotiffExport):
                raise Http404('no export archive generated for requested overlay yet')
            return HttpResponse(overlay.alignedQuadTree.geotiffExport.file.read(),
                                content_type='application/x-tgz')
    else:
        return HttpResponseNotAllowed(['GET'])


@csrf_exempt
def getExportFilesList(request):
    """
    Downloads a csv file containing list of all available export products (kml, geotiff, html).
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="GeoRefExportProductsList.csv"'
    exports = QuadTree.objects.values_list('htmlExportName', 'geotiffExportName', 'kmlExportName')
    writer = csv.writer(response)
    for set in exports:
        for data in set:
            if data is not None:
                writer.writerow([data])
    return response


@csrf_exempt
def getExportFile(request, name):
    if "kml" in name:
        quadTree = QuadTree.objects.filter(kmlExportName = name)[0]
        return HttpResponse(quadTree.kmlExport.file.read(),
                            content_type='application/x-tgz')
    elif "geotiff" in name:
        quadTree = QuadTree.objects.filter(geotiffExportName = name)[0]
        return HttpResponse(quadTree.geotiffExport.file.read(),
                            content_type='application/x-tgz')
    elif "html" in name:
        quadTree = QuadTree.objects.filter(htmlExportName = name)[0]
        return HttpResponse(quadTree.htmlExport.file.read(),
                            content_type='application/x-tgz')
    else:
        raise Http404('Export file of the name %s does not exist' % name)


@csrf_exempt
def garbageCollect(request, dryRun='1'):
    if request.method == 'GET':
        return render_to_response('geocamTiePoint/gc.html',
                                  {},
                                  context_instance=RequestContext(request))
    elif request.method == 'POST':
        dryRun = int(dryRun)
        garbage.garbageCollect(dryRun)
        return HttpResponse('{"result": "ok"}', content_type='application/json')
    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


def simpleAlignedOverlayViewer(request, key, slug=None):
    if request.method == 'GET':
        overlay = get_object_or_404(Overlay, key=key)
        return HttpResponse(overlay.getSimpleAlignedOverlayViewer(request))
    else:
        return HttpResponseNotAllowed(['GET'])
