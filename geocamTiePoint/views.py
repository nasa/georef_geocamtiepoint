# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

from django.shortcuts import render_to_response
from django.http import HttpResponse, HttpResponseRedirect
from django.http import HttpResponseForbidden, Http404
from django.http import HttpResponseNotAllowed, HttpResponseBadRequest
from django.template import RequestContext
from django.utils.translation import ugettext, ugettext_lazy as _

import json, base64, os.path, os, math
import numpy

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

from PIL import Image

from geocamTiePoint import models, forms, settings

TILE_SIZE = 256.
INITIAL_RESOLUTION = 2 * math.pi * 6378137 / TILE_SIZE
ORIGIN_SHIFT = 2 * math.pi * 6378137 / 2.
ZOOM_OFFSET = 3

def overlayIndex(request):
    if request.method == 'GET':
        overlays = models.Overlay.objects.all()
        return render_to_response('overlay-index.html', {'overlays':overlays},
                                  context_instance=RequestContext(request))
    else:
        return HttpResponseNotAllowed(['GET','POST'])

def overlayDelete(request, key):
    if request.method == 'GET':
        try:
            overlay = models.Overlay.objects.get(key=key)
        except models.Overlay.DoesNotExist:
            raise Http404()
        return render_to_response('overlay-delete.html', {'overlay':overlay,
                                                          'index_url':'/'+settings.TIEPOINT_URL+'/'},
                                  context_instance=RequestContext(request))
    elif request.method == 'POST':
        try:
            overlay = models.Overlay.objects.get(key=key)
        except models.Overlay.DoesNotExist:
            raise Http404()
        overlay.delete()
        return HttpResponseRedirect("/"+settings.TIEPOINT_URL+'/')

def overlayNew(request):
    if request.method == 'GET':
        form = forms.NewOverlayForm()
        return render_to_response('new-overlay.html', {'form':form},
                                  context_instance=RequestContext(request))
    elif request.method == 'POST':
        form = forms.NewOverlayForm(request.POST, request.FILES)
        if not form.is_valid():
            return HttpResponseBadRequest()
        image = form.cleaned_data['image']
        preData = {}
        overlay = models.Overlay(image=image, imageType=image.content_type,
                                 name=os.path.split(image.name)[-1],
                                 data=json.dumps(preData))
        overlay.save()
        image = Image.open(models.dataStorage.path(overlay.image))
        basePath = models.dataStorage.path('geocamTiePoint/tiles/'+str(overlay.key))
        generateQuadTree(image,basePath)
        preData['points'] = []
        preData['url'] = '/'+settings.TIEPOINT_URL+'/'+str(overlay.key)+'.json'
        preData['tilesUrl'] = settings.DATA_URL+'geocamTiePoint/tiles/'+str(overlay.key)
        preData['imageSize'] = (overlay.image.width, overlay.image.height)
        preData['key'] = overlay.key
        overlay.data = json.dumps(preData)
        overlay.save()
        return render_to_response('new-overlay-result.html', {'status':'success',
                                                              'id':overlay.key},
                                  context_instance=RequestContext(request))
    else:
        return HttpResponseNotAllowed(['GET','POST'])

def overlayId(request, key):
    if request.method == 'GET':
        # this line maybe should be try/catched to check for non-existing overlays
        try:
            overlay = models.Overlay.objects.get(key=key)
        except models.Overlay.DoesNotExist:
            raise Http404()
        else:
            return render_to_response('map-simple.html', {'overlay':overlay},
                                      context_instance=RequestContext(request))
    else:
        return HttpResponseNotAllowed(['GET'])

def overlayIdJson(request, key):
    if request.method == 'GET':
        try:
            overlay = models.Overlay.objects.get(key=key)
        except models.Overlay.DoesNotExist:
            raise Http404()
        return HttpResponse(overlay.data)
    elif request.method == 'POST':
        try:
            overlay = models.Overlay.objects.get(key=key)
        except models.Overlay.DoesNotExist:
            raise Http404()
        overlay.data = request.POST['data']
        overlay.name = request.POST['name']
        overlay.imageType = request.POST['imageType']
        overlay.save()
        return HttpResponse("")
    else:
        return HttpResponseNotAllowed(['GET','POST'])

def overlayIdWarp(request, key):
    if request.method == 'GET':
        return render_to_response('warp-form.html',{},
                                  context_instance=RequestContext(request))
    elif request.method == 'POST':
        # "eventually"
        return HttpResponse()
    else:
        return HttpResponseNotAllowed(['GET','POST'])

def overlayIdImageFileName(request, key, fileName):
    if request.method == 'GET':
        try:
            overlay = models.Overlay.objects.get(key=key)
        except models.Overlay.DoesNotExist:
            raise Http404()
        fobject = overlay.image; fobject.open()
        response = HttpResponse(fobject.read(), content_type=overlay.imageType)
        return response
    else:
        return HttpResponseNotAllowed(['GET'])

def splitArray(array, by):
    by = int(by)
    assert(by > 1)
    newArray = []
    for i in range(0, int(float(len(array))/by)+1, by):
        newArray.append(array[i:i+by])
    return newArray

def generateQuadTree(image, basePath):
    coords = ((0,0),(image.size[0],0),(0,image.size[1]),image.size)
    makeQuadTree(image, coords, basePath)

def makeQuadTree(image, coords, basePath):
    if image.size[0] > image.size[1]:
        maxZoom = int(math.ceil(math.log(image.size[0]/TILE_SIZE,2)))
    else:
        maxZoom = int(math.ceil(math.log(image.size[1]/TILE_SIZE,2)))
    for i in xrange(maxZoom, -1, -1):
        for ix in xrange(nx):
            for iy in xrange(ny):
                if testOutsideImage((TILE_SIZE*ix,TILE_SIZE*iy),coords) or\
                        testOutsideImage((TILE_SIZE*(ix+1),TILE_SIZE*iy),coords) or\
                        testOutsideImage((TILE_SIZE*ix,TILE_SIZE*(iy+1)),coords) or\
                        testOutsideImage((TILE_SIZE*(ix+1),TILE_SIZE*(iy+1)),coords):
                    continue
                if not os.path.exists(basePath+'/%s/%s/' % (i+ZOOM_OFFSET,ix)):
                    os.makedirs(basePath+'/%s/%s' % (i+ZOOM_OFFSET,ix))
                newImage = image.crop([TILE_SIZE*ix,TILE_SIZE*iy,TILE_SIZE*(ix+1),TILE_SIZE*(iy+1)])
                newImage.save(basePath+'/%s/%s/%s.jpg' % (i+ZOOM_OFFSET,ix,iy))
        image = image.resize((int(math.ceil(image.size[0]/2.)),
                              int(math.ceil(image.size[1]/2.))),
                             Image.ANTIALIAS)
                    

def testOutsideImage(point, coords):
    upperLeft, upperRight, lowerLeft, lowerRight = coords
    if point[0] < min(upperLeft[0], lowerLeft[0]):
        return True
    if point[1] < min(upperLeft[1], upperRight[1]):
        return True
    if point[0] > max(upperRight[0], lowerRight[0]):
        return True
    if point[1] > max(lowerLeft[1], lowerRight[1]):
        return True
    if point[0] > max(upperLeft[0], lowerLeft[0]) and\
            point[0] < min(upperRight[0], lowerRight[0]) and\
            point[1] > max(lowerLeft[1], lowerRight[1]) and\
            point[1] < min(upperRight[1], upperRight[1]):
        return False
    # just assuming it's in the image, even though it might not be
    return False

def generateWarpedQuadTree(image, method, data, basePath):
    if method in ('similarity, affine'):
        warpedImage = image.transform(image.size, Image.AFFINE, data)
        
    elif method in ('projective'):
        warpedImage = image.transform(image.size, Image.QUAD, data)
    else:
        raise ValueError("Incorrect warp method")
    

def transformMapTileMatrix(tile):
    zoom, x, y = tile
    latSize = (180.) / (2 ** zoom)
    pixelSize = 256.
    s = pixelSize / latsize
    lon0 = -180 + (x * latSize)
    lat0 = 90 - (y * latSize)
    return [s, 0, -s * lon0,
            0, -s, s * lat0,
            0, 0, 1]

