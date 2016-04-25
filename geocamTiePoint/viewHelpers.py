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


def getPILimage(imageData):
    try: 
        image = PIL.Image.open(imageData.image.file) 
    except: 
        logging.error("image cannot be read from the image data")
        return None
    return image


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
        overlay.imageData.issMRF = issImage.mission + '-' + issImage.roll + '-' + str(issImage.frame)
        overlay.imageData.save()
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
