# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

# avoid warnings due to pylint not understanding DotDict objects
# pylint: disable=E1101

import os
import datetime
import re
import logging
import threading
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import PIL.Image
import pyproj
import numpy as np
from osgeo import gdal

from django.db import models
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from geocamUtil import anyjson as json
from geocamUtil import gdal2tiles
from geocamUtil.models.ExtrasDotField import ExtrasDotField
from geocamTiePoint import quadTree, transform, settings, rpcModel, gdalUtil

# poor man's local memory cache for one quadtree tile generator. a
# common access pattern is that the same instance of the app gets
# multiple tile requests on the same quadtree. optimize for that case by
# keeping the generator in memory. note: an alternative approach would
# use the memcached cache, but that would get rid of much of the benefit
# in terms of serialization/deserialization.
cachedGeneratorG = threading.local()


def getNewImageFileName(instance, filename):
    return 'geocamTiePoint/overlay_images/' + filename


def getNewExportFileName(instance, filename):
    return 'geocamTiePoint/export/' + filename


def dumps(obj):
    return json.dumps(obj, sort_keys=True, indent=4)


class MissingData(object):
    pass
MISSING = MissingData()


def dosys(cmd):
    logging.info('running: %s', cmd)
    ret = os.system(cmd)
    if ret != 0:
        logging.warn('command exited with non-zero return value %s', ret)
    return ret


class ImageData(models.Model):
    lastModifiedTime = models.DateTimeField()
    # image.max_length needs to be long enough to hold a blobstore key
    image = models.ImageField(upload_to=getNewImageFileName,
                              max_length=255)
    contentType = models.CharField(max_length=50)
    overlay = models.ForeignKey('Overlay', null=True, blank=True)
    checksum = models.CharField(max_length=128, blank=True)
    # we set unusedTime when a QuadTree is no longer referenced by an Overlay.
    # it will eventually be deleted.
    unusedTime = models.DateTimeField(null=True, blank=True)
    # If certain angle is requested and image data is available in db, 
    # we can just pull up that image.
    rotationAngle = models.IntegerField(null=True, blank=True, default=0)
    # holds image that hasn't been enhanced (but may have been rotated)
    unenhancedImage = models.ImageField(upload_to = getNewImageFileName,
                                        max_length=255, null=True, blank=True)
    #holds image that has been enhanced (and may have been rotated)
    enhancedImage = models.ImageField(upload_to = getNewImageFileName,
                                        max_length=255, null=True, blank=True)
    contrast = models.FloatField(null=True, blank=True, default=0)
    brightness = models.FloatField(null=True, blank=True, default=0)
    isOriginal = models.BooleanField(default=False)

    def __unicode__(self):
        if self.overlay:
            overlay_id = self.overlay.key
        else:
            overlay_id = None
        return ('ImageData overlay_id=%s checksum=%s %s'
                % (overlay_id, self.checksum, self.lastModifiedTime))

    def save(self, *args, **kwargs):
        self.lastModifiedTime = datetime.datetime.utcnow()
        super(ImageData, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.image.delete()
        super(ImageData, self).delete(*args, **kwargs)


class QuadTree(models.Model):
    lastModifiedTime = models.DateTimeField()
    imageData = models.ForeignKey('ImageData', null=True, blank=True)
    # transform is either an empty string (simple quadTree) or a JSON-formatted
    # definition of the warping transform (warped quadTree)
    transform = models.TextField(blank=True)

    # note: 'exportZip' is a bit of a misnomer since the archive may not
    # be a zipfile (tarball by default).  but no real need to change the
    # field name and force a db migration.
    htmlExportName = models.CharField(max_length=255,
                                     null=True, blank=True)
    htmlExport = models.FileField(upload_to=getNewExportFileName,
                                 max_length=255,
                                 null=True, blank=True)
    kmlExportName = models.CharField(max_length=255,
                                     null=True, blank=True)
    kmlExport = models.FileField(upload_to=getNewExportFileName,
                                 max_length=255,
                                 null=True, blank=True)
    geotiffExportName = models.CharField(max_length=255,
                                     null=True, blank=True)
    geotiffExport = models.FileField(upload_to=getNewExportFileName,
                                     max_length=255,
                                     null=True, blank=True)

    # we set unusedTime when a QuadTree is no longer referenced by an Overlay.
    # it will eventually be deleted.
    unusedTime = models.DateTimeField(null=True, blank=True)

    def __unicode__(self):
        return ('QuadTree id=%s imageData_id=%s transform=%s %s'
                % (self.id, self.imageData.id, self.transform,
                   self.lastModifiedTime))

    def save(self, *args, **kwargs):
        self.lastModifiedTime = datetime.datetime.utcnow()
        super(QuadTree, self).save(*args, **kwargs)

    def getBasePath(self):
        return settings.DATA_ROOT + 'geocamTiePoint/tiles/%d' % self.id

    def convertImageToRgbaIfNeeded(self, image):
        """
        With the latest code we convert to RGBA on image import. This
        special case helps migrate any remaining images that didn't get
        that conversion.
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
            out = StringIO()
            image.save(out, format='png')
            self.imageData.image.save('dummy.png', ContentFile(out.getvalue()), save=False)
            self.imageData.contentType = 'image/png'
            self.imageData.save()

    def getImage(self):
        # apparently image.file is not a very good file work-alike,
        # so let's delegate to StringIO(), which PIL is tested against
        bits = self.imageData.image.file.read()
        logging.info('getImage len=%s header=%s',
                     len(bits), repr(bits[:10]))
        fakeFile = StringIO(bits)

        im = PIL.Image.open(fakeFile)
        self.convertImageToRgbaIfNeeded(im)
        return im

    @classmethod
    def getGeneratorCacheKey(cls, quadTreeId):
        return 'geocamTiePoint.QuadTreeGenerator.%s' % quadTreeId

    @classmethod
    def getGeneratorWithCache(cls, quadTreeId):
        cachedGeneratorCopy = getattr(cachedGeneratorG, 'gen',
                                      {'key': None, 'value': None})
        key = cls.getGeneratorCacheKey(quadTreeId)
        if cachedGeneratorCopy['key'] == key:
            logging.debug('getGeneratorWithCache hit %s', key)
            result = cachedGeneratorCopy['value']
        else:
            logging.debug('getGeneratorWithCache miss %s', key)
            q = get_object_or_404(QuadTree, id=quadTreeId)
            result = q.getGenerator()
            cachedGeneratorG.gen = dict(key=key, value=result)
        return result

    def getGenerator(self):
        image = self.getImage()
        if self.transform:
            return quadTree.WarpedQuadTreeGenerator(self.id,
                                                   image,
                                                   json.loads(self.transform))
        else:
            return quadTree.SimpleQuadTreeGenerator(self.id,
                                                image)

    @staticmethod
    def getSimpleViewHtml(tileRootUrl, metaJson, slug):
        return render_to_string('geocamTiePoint/simple-view.html',
                                {'name': metaJson['name'],
                                 'slug': slug,
                                 'tileRootUrl': tileRootUrl,
                                 'bounds': dumps(metaJson['bounds']),
                                 'tileUrlTemplate': '%s/[ZOOM]/[X]/[Y].png' % slug,
                                 'tileSize': 256})

    def reversePts(self, toPts):
        """
        Helper needed for fitRpcToModel. 
        Does v = T(u).
            @v is a 3 x n matrix of n 3D points in WGS84 (lon, lat, alt)
            @u is a 2 x n matrix of n 2D points in image (px, py)
        """
        transformDict  = json.loads(self.transform)
        tform =  transform.makeTransform(transformDict)
        pixels = None
        for column in toPts.T:
            # convert column (3D pts in WGS84) to gmap meters
            lonlat = column[:2]
            gmap_meters = transform.lonLatToMeters(lonlat)
            px, py = tform.reverse(gmap_meters)
            newCol = np.array([[px],[py]])
            if pixels is None:
                pixels = newCol
            else:
                pixels = np.column_stack((pixels, newCol))
        return pixels        


    def generateHtmlExport(self, exportName, metaJson, slug):
        gen = self.getGeneratorWithCache(self.id)
        now = datetime.datetime.utcnow()
        timestamp = now.strftime('%Y-%m-%d-%H%M%S-UTC')
        # generate html export
        htmlExportName = exportName + ('-small-html_%s' % timestamp)
        viewHtmlPath = 'view.html'
        tileRootUrl = './%s' % slug
        html = self.getSimpleViewHtml(tileRootUrl, metaJson, slug)
        logging.debug('html: len=%s head=%s', len(html), repr(html[:10]))
        # tar the html export
        writer = quadTree.TarWriter(htmlExportName)
        gen.writeQuadTree(writer, slug)
        writer.writeData(viewHtmlPath, html)
        writer.writeData('meta.json', dumps(metaJson))
        self.htmlExportName = '%s.tar.gz' % htmlExportName
        self.htmlExport.save(self.htmlExportName,
                            ContentFile(writer.getData()))

        
    def generateGeotiffExport(self, exportName, metaJson, slug):
        """
        This generates a geotiff from RPC.
        """
        now = datetime.datetime.utcnow()
        timestamp = now.strftime('%Y-%m-%d-%H%M%S-UTC')
        
        # get image width and height
        overlay = Overlay.objects.get(alignedQuadTree = self) 
        imageWidth, imageHeight = overlay.extras.imageSize
        
        # update the center point with current transform and use those values
        transformDict  = overlay.extras.transform
        tform =  transform.makeTransform(transformDict)
        center_meters = tform.forward([imageWidth / 2, imageHeight / 2])
        clon, clat  = transform.metersToLatLon(center_meters)
        # get the RPC values 
        T_rpc = rpcModel.fitRpcToModel(self.reversePts, 
                                     imageWidth, imageHeight,
                                     clon, clat)
        srs = gdalUtil.EPSG_4326
        # get original image
        imgPath = overlay.getOriginalImageData().image.url.replace('/data/', settings.DATA_ROOT)
        
        # reproject and tar the output tiff
        geotiffExportName = exportName + ('-small-geotiff_%s' % timestamp)
        outputDir = settings.DATA_ROOT + 'geocamTiePoint/export/' + geotiffExportName
        dosys('mkdir %s' % outputDir)
        resultPath = outputDir + '/' + geotiffExportName +'.tif'
        gdalUtil.reprojectWithRpcMetadata(imgPath, T_rpc.getVrtMetadata(), srs, resultPath)
        geotiff_writer = quadTree.TarWriter(outputDir)
        arcName = geotiffExportName + '.tif'
        geotiff_writer.addFile(resultPath, arcName)  # double check this line (second arg may not be necessary)
        self.geotiffExportName = '%s.tar.gz' % geotiffExportName
        self.geotiffExport.save(self.geotiffExportName,
                                ContentFile(geotiff_writer.getData()))

    
    def generateKmlExport(self, exportName, metaJson, slug):
        """
        this generates the kml and the tiles.
        """
        now = datetime.datetime.utcnow()
        timestamp = now.strftime('%Y-%m-%d-%H%M%S-UTC')
        
        kmlExportName = exportName + ('-small-kml_%s' % timestamp)
        outputDir = settings.DATA_ROOT + 'geocamTiePoint/export/' + kmlExportName
        
        # get the path to latest geotiff file
        inputFile = self.geotiffExportName.replace('.tar.gz', '')
        inputFile = settings.DATA_ROOT + 'geocamTiePoint/export/' + inputFile + '/' + inputFile + ".tif"
        #TODO: make this call the gdal2tiles
        
        g2t = gdal2tiles.GDAL2Tiles(["--force-kml", str(inputFile), str(outputDir)])
        g2t.process()
        
        # tar the kml
        kml_writer = quadTree.TarWriter(outputDir)
        arcName = kmlExportName
        kml_writer.addFile(outputDir, arcName)  # double check. second arg may not be necessary
        self.kmlExportName = '%s.tar.gz' % kmlExportName
        self.kmlExport.save(self.kmlExportName, 
                            ContentFile(kml_writer.getData()))      
        
        
class Overlay(models.Model):
    key = models.AutoField(primary_key=True, unique=True)
    # author: user who owns this overlay in the MapFasten system
    author = models.ForeignKey(User, null=True, blank=True)
    lastModifiedTime = models.DateTimeField()
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    imageSourceUrl = models.URLField(blank=True) #, verify_exists=False)
    imageData = models.ForeignKey(ImageData, null=True, blank=True,
                                  related_name='currentOverlays',
                                  on_delete=models.SET_NULL)
    unalignedQuadTree = models.ForeignKey(QuadTree, null=True, blank=True,
                                          related_name='unalignedOverlays',
                                          on_delete=models.SET_NULL)
    alignedQuadTree = models.ForeignKey(QuadTree, null=True, blank=True,
                                        related_name='alignedOverlays',
                                        on_delete=models.SET_NULL)
    isPublic = models.BooleanField(default=settings.GEOCAM_TIE_POINT_PUBLIC_BY_DEFAULT)
    coverage = models.CharField(max_length=255, blank=True,
                                verbose_name='Name of region covered by the overlay')

    # creator: name of person or organization who should get the credit
    # for producing the overlay
    creator = models.CharField(max_length=255, blank=True)
    sourceDate = models.CharField(max_length=255, blank=True,
                                  verbose_name='Source image creation date')
    rights = models.CharField(max_length=255, blank=True,
                              verbose_name='Copyright information')
    license = models.URLField(blank=True,
                              verbose_name='License permitting reuse (optional)',
                              choices=settings.GEOCAM_TIE_POINT_LICENSE_CHOICES)
    # stores mission roll frame of the image. i.e. "ISS039-E-12345"
    issMRF = models.CharField(max_length=255, null=True, blank=True,
                              help_text="Please use the following format: <em>[Mission ID]-[Roll]-[Frame number]</em>") # ISS mission roll frame id of image.
    # extras: a special JSON-format field that holds additional
    # schema-free fields in the overlay model. Members of the field can
    # be accessed using dot notation. currently used extras subfields
    # include: imageSize, points, transform, bounds, centerPointLatLon, rotatedImageSize
    extras = ExtrasDotField()
    # import/export configuration
    exportFields = ('key', 'lastModifiedTime', 'name', 'description', 'imageSourceUrl', 
                    'issMRF', 'centerPointLatLon')
    importFields = ('name', 'description', 'imageSourceUrl')
    importExtrasFields = ('points', 'transform', 'centerPointLatLon')


    def getOriginalImageData(self):
        """
        Returns the original image data created upon image upload (not rotated, not enhanced)
        """
        imageData = ImageData.objects.filter(overlay__key = self.key).filter(isOriginal = True)
        return imageData[0]


    def getAlignedTilesUrl(self):
        if self.isPublic:
            urlName = 'geocamTiePoint_publicTile'
        else:
            urlName = 'geocamTiePoint_tile'
        return reverse(urlName,
                       args=[str(self.alignedQuadTree.id),
                             '[ZOOM]',
                             '[X]',
                             '[Y].png'])

    def getJsonDict(self):
        # export all schema-free subfields of extras
        result = self.extras.copy()

        # export other schema-controlled fields of self (listed in exportFields)
        for key in self.exportFields:
            val = getattr(self, key, None)
            if val not in ('', None):
                result[key] = val

        # conversions
        result['lastModifiedTime'] = (result['lastModifiedTime']
                                      .replace(microsecond=0)
                                      .isoformat()
                                      + 'Z')

        # calculate and export urls for client convenience
        result['url'] = reverse('geocamTiePoint_overlayIdJson', args=[self.key])
        if self.unalignedQuadTree is not None:
            result['unalignedTilesUrl'] = reverse('geocamTiePoint_tile',
                                                  args=[str(self.unalignedQuadTree.id),
                                                        '[ZOOM]',
                                                        '[X]',
                                                        '[Y].jpg'])
            result['unalignedTilesZoomOffset'] = quadTree.ZOOM_OFFSET
        if self.alignedQuadTree is not None:
            result['alignedTilesUrl'] = self.getAlignedTilesUrl()

            # note: when exportZip has not been set, its value is not
            # None but <FieldFile: None>, which is False in bool() context
            if self.alignedQuadTree.htmlExport: 
                result['htmlExportUrl'] = reverse('geocamTiePoint_overlayExport',
                                              args=[self.key, 
                                                    'html',
                                                    str(self.alignedQuadTree.htmlExportName)])
            if self.alignedQuadTree.kmlExport: 
                result['kmlExportUrl'] = reverse('geocamTiePoint_overlayExport',
                                              args=[self.key,
                                                    'kml',
                                                    str(self.alignedQuadTree.kmlExportName)])
            if self.alignedQuadTree.geotiffExport: 
                result['geotiffExportUrl'] = reverse('geocamTiePoint_overlayExport',
                                              args=[self.key,
                                                    'geotiff',
                                                    str(self.alignedQuadTree.geotiffExportName)])

        return result

    def setJsonDict(self, jsonDict):
        # set schema-controlled fields of self (listed in
        # self.importFields)
        for key in self.importFields:
            val = jsonDict.get(key, MISSING)
            if val is not MISSING:
                setattr(self, key, val)

        # set schema-free subfields of self.extras (listed in
        # self.importExtrasFields)
        for key in self.importExtrasFields:
            val = jsonDict.get(key, MISSING)
            if val is not MISSING:
                self.extras[key] = val

    jsonDict = property(getJsonDict, setJsonDict)

    class Meta:
        ordering = ['-key']

    def __unicode__(self):
        return ('Overlay key=%s name=%s author=%s %s'
                % (self.key, self.name, self.author.username,
                   self.lastModifiedTime))

    def save(self, *args, **kwargs):
        self.lastModifiedTime = datetime.datetime.utcnow()
        super(Overlay, self).save(*args, **kwargs)

    def getSlug(self):
        return re.sub('[^\w]', '_', os.path.splitext(self.name)[0])

    def getExportName(self):
        now = datetime.datetime.utcnow()
        return 'mapfasten-%s' % self.getSlug() 
#         return ('mapfasten-%s-%s'
#                 % (self.getSlug(),
#                    now.strftime('%Y-%m-%d-%H%M%S-UTC')))

    def generateUnalignedQuadTree(self):
        qt = QuadTree(imageData=self.imageData)
        qt.save()

        self.unalignedQuadTree = qt
        self.save()

        return qt

    def generateAlignedQuadTree(self):
        if self.extras.get('transform') is None:
            return None
        # grab the original image's imageData
        originalImageData = self.getOriginalImageData()
        qt = QuadTree(imageData=originalImageData,
                    transform=dumps(self.extras.transform))
        qt.save()
        self.alignedQuadTree = qt
        return qt

    def generateHtmlExport(self):
        (self.alignedQuadTree.generateHtmlExport
         (self.getExportName(),
          self.getJsonDict(),
          self.getSlug()))
        return self.alignedQuadTree.htmlExport 

    def generateKmlExport(self):
        (self.alignedQuadTree.generateKmlExport
         (self.getExportName(),
          self.getJsonDict(),
          self.getSlug()))
        return self.alignedQuadTree.kmlExport 

    def generateGeotiffExport(self):
        (self.alignedQuadTree.generateGeotiffExport
         (self.getExportName(),
          self.getJsonDict(),
          self.getSlug()))
        return self.alignedQuadTree.geotiffExport 

    def updateAlignment(self):
        toPts, fromPts = transform.splitPoints(self.extras.points)
        tform = transform.getTransform(toPts, fromPts)
        self.extras.transform = tform.getJsonDict()

    def getSimpleAlignedOverlayViewer(self, request):
        alignedTilesPath = re.sub(r'/\[ZOOM\].*$', '', self.getAlignedTilesUrl())
        alignedTilesRootUrl = request.build_absolute_uri(alignedTilesPath)
        return (self.alignedQuadTree
                .getSimpleViewHtml(alignedTilesRootUrl,
                                   self.getJsonDict(),
                                   self.getSlug()))
