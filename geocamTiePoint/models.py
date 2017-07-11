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

# avoid warnings due to pylint not understanding DotDict objects
# pylint: disable=E1101

import os
import datetime
import re
import logging
import threading
import sys

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import PIL.Image
import numpy as np
from osgeo import gdal

from django.db import models
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.conf import settings

from geocamUtil import anyjson as json
from geocamUtil import gdal2tiles, imageInfo
from geocamUtil.models.ExtrasDotField import ExtrasDotField
from geocamTiePoint import quadTree, transform, rpcModel, gdalUtil
from geocamUtil.ErrorJSONResponse import ErrorJSONResponse, checkIfErrorJSONResponse
from georef_imageregistration import offline_config, registration_common

from deepzoom.models import DeepZoom


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
    exportFileName = filename
    if filename:
        try: 
            mission, roll, frame = filename.split("_")[0].split("-")
            dirName = os.path.dirname(registration_common.getWorkingDir(mission, roll, frame))
        except:
            return exportFileName
        exportFileName = dirName + '/' + filename
    return exportFileName


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
        

class ISSimage:
    def __init__(self, mission, roll, frame, sizeType):
        self.mission = mission
        self.roll = roll
        self.frame = frame
        self.sizeType = sizeType
        self.infoUrl = "http://eo-web.jsc.nasa.gov/GeoCam/PhotoInfo.pl?photo=%s-%s-%s" % (self.mission, self.roll, self.frame)
        self.imageUrl = self.__getImageUrl()
        self.width = None
        self.height = None
        # check for must have info.
        assert self.mission != ""
        assert self.roll != ""
        assert self.frame != ""
        assert self.sizeType != ""
        # set image file
        self.imageFile = imageInfo.getImageFile(self.imageUrl)
        # set extras
        self.extras = imageInfo.constructExtrasDict(self.infoUrl) 
        try:  # open it as a PIL image
            bits = self.imageFile.file.read()
            image = PIL.Image.open(StringIO(bits))
            if image.size: 
                self.width, self.height = image.size
            # set focal length
            sensorSize = (.036,.0239) #TODO: calculate this
            focalLength = imageInfo.getAccurateFocalLengths(image.size, self.extras.focalLength_unitless, sensorSize)
            self.extras['focalLength'] = [round(focalLength[0],2), round(focalLength[1],2)]        
        except Exception as e:  # pylint: disable=W0703
            logging.error("PIL failed to open image: " + str(e))
        
    def __getImageUrl(self):
        if self.sizeType == 'small':
            if (self.roll == "E") or (self.roll == "ESC"):
                rootUrl = "http://eo-web.jsc.nasa.gov/DatabaseImages/ESC/small" 
            else: 
                rootUrl = "http://eo-web.jsc.nasa.gov/DatabaseImages/ISD/lowres"
        else: 
            if (self.roll == "E") or (self.roll == "ESC"):
                rootUrl = "http://eo-web.jsc.nasa.gov/DatabaseImages/ESC/large" 
            else: 
                rootUrl = "http://eo-web.jsc.nasa.gov/DatabaseImages/ISD/highres"
        return  rootUrl + "/" + self.mission + "/" + self.mission + "-" + self.roll + "-" + self.frame + ".jpg"


class ImageData(models.Model):
    lastModifiedTime = models.DateTimeField()
    # image.max_length needs to be long enough to hold a blobstore key
    image = models.ImageField(upload_to=getNewImageFileName,
                              max_length=512, 
                              help_text="displayed image")
    #TODO: unenhancedImage and enhancedImage are deprecated. delete them later.
    unenhancedImage = models.ImageField(upload_to=getNewImageFileName,
                                        max_length=255, help_text="raw image")
    enhancedImage = models.ImageField(upload_to=getNewImageFileName,
                              max_length=255, help_text="altered image")
    width = models.PositiveIntegerField(null=True, blank=True, default=0, help_text="raw image width in pixels")
    height = models.PositiveIntegerField(null=True, blank=True, default=0, help_text="raw image height in pixels")
    sizeType = models.CharField(null=True, blank=True, max_length=50, help_text="either small (default) or large")
    contentType = models.CharField(max_length=50)
    overlay = models.ForeignKey('Overlay', null=True, blank=True)
    checksum = models.CharField(max_length=128, blank=True)
    # we set unusedTime when a QuadTree is no longer referenced by an Overlay.
    # it will eventually be deleted.
    unusedTime = models.DateTimeField(null=True, blank=True)
    # If certain angle is requested and image data is available in db, 
    # we can just pull up that image.
    rotationAngle = models.IntegerField(null=True, blank=True, default=0)
    contrast = models.FloatField(null=True, blank=True, default=1)
    brightness = models.FloatField(null=True, blank=True, default=0)
    autoenhance = models.BooleanField(default=False, blank=True)
    raw = models.BooleanField(default=False)
    # stores mission roll frame of the image. i.e. "ISS039-E-12345"
    issMRF = models.CharField(max_length=255, null=True, blank=True,
                              help_text="Please use the following format: <em>[Mission ID]-[Roll]-[Frame number]</em>") # ISS mission roll frame id of image.
    # deep zoom fields
    try:
        DEFAULT_CREATE_DEEPZOOM = settings.DEFAULT_CREATE_DEEPZOOM_OPTION
    except AttributeError:
        DEFAULT_CREATE_DEEPZOOM = False
        
    #Optionally generate deep zoom from uploaded image if set to True.
    create_deepzoom = models.BooleanField(default=DEFAULT_CREATE_DEEPZOOM,
                                          help_text="Generate deep zoom?")
     
    #Link this image to generated deep zoom.
    associated_deepzoom = models.ForeignKey(DeepZoom,
                                            null=True,
                                            blank=True,
                                            related_name="%(app_label)s_%(class)s",
                                            editable=False,
                                            on_delete=models.SET_NULL)
    
    def create_deepzoom_slug(self):
        """
        Returns a string instance for deepzoom slug.
        """
        if self.issMRF:
            try: 
                deepzoomSlug = self.issMRF + "_deepzoom_" + str(self.id)
                return deepzoomSlug.lower()
            except: 
                return "no_name"
        else: 
            return "no_name"
    
    
    def create_deepzoom_image(self):
        """
        Creates and processes deep zoom image files to storage.
        Returns instance of newly created DeepZoom instance for associating   
        uploaded image to it.
        """
        try:
            deepzoomSlug = self.create_deepzoom_slug()
            deepzoomPath = 'deepzoom/' + deepzoomSlug
            dz = DeepZoom.objects.create(associated_image=self.image.name, 
                                         name=deepzoomSlug,
                                         slug=deepzoomSlug,
                                         deepzoom_path=deepzoomPath)
            dz.create_deepzoom_files()
            self.associated_deepzoom = dz
            self.create_deepzoom = False
            self.save() 
        except (TypeError, ValueError, AttributeError) as err:
            print("Error: Incorrect deep zoom parameter(s) in settings.py: {0}".format(err))
            raise
        except:
            print("Unexpected error creating deep zoom: {0}".format(sys.exc_info()[1:2]))
            raise
        return dz

    def __unicode__(self):
        if self.overlay:
            overlay_id = self.overlay.key
        else:
            overlay_id = None
        return ('ImageData overlay_id=%s checksum=%s %s'
                % (overlay_id, self.checksum, self.lastModifiedTime))

    def duplicate(self):
        """
        Duplicate this imagedata including copying the image files
        """
        # duplicate the image data object
        newImageData = self
        newImageData.pk=None
        # save the image bits into a new file object
        newFile = ContentFile(self.image.read())
        # this assigns it a new name automatically (attaches _1)
        newFile.name = self.image.name.split('/')[-1]
        newImageData.image = newFile
        newImageData.unenhancedImage = newFile
        newImageData.enhancedImage = None
        newImageData.save()
        return newImageData
        
    def save(self, *args, **kwargs):
        self.lastModifiedTime = datetime.datetime.utcnow()
        super(ImageData, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.image.delete()
        self.unenhancedImage.delete()
        self.enhancedImage.delete()
        try: 
            dz = self.associated_deepzoom
            dz.delete_deepzoom_files()
            dz.delete()
            self.associated_deepzoom = None
            self.save()
        except Exception as e: 
            print "could not delete deepzoom files while deleting imagedata (see error below)"
            print e
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
    metadataExportName = models.CharField(max_length=255,
                                          null=True, blank=True)
    metadataExport = models.FileField(upload_to=getNewExportFileName,
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
        overlay = Overlay.objects.get(alignedQuadTree = self)
        imageSizeType = overlay.imageData.sizeType
        gen = self.getGeneratorWithCache(self.id)
        now = datetime.datetime.utcnow()
        timestamp = now.strftime('%Y-%m-%d-%H%M%S-UTC')
        # generate html export
        htmlExportName = exportName + ('-%s-html_%s' % (imageSizeType, timestamp))
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
        overlay = Overlay.objects.get(alignedQuadTree = self)
        imageSizeType = overlay.imageData.sizeType
        now = datetime.datetime.utcnow()
        timestamp = now.strftime('%Y-%m-%d-%H%M%S-UTC')
        
        # get image width and height
        imageWidth = overlay.imageData.width
        imageHeight = overlay.imageData.height
        
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
        imgPath = overlay.getRawImageData().image.url.replace('/data/', settings.DATA_ROOT)
        # reproject and tar the output tiff
        geotiffExportName = exportName + ('-%s-geotiff_%s' % (imageSizeType, timestamp))
        geotiffFolderPath = settings.DATA_ROOT + 'geocamTiePoint/export/' + geotiffExportName
        dosys('mkdir %s' % geotiffFolderPath)

        fullFilePath = geotiffFolderPath + '/' + geotiffExportName +'.tif'
        gdalUtil.reprojectWithRpcMetadata(imgPath, T_rpc.getVrtMetadata(), srs, fullFilePath)

        geotiff_writer = quadTree.TarWriter(geotiffExportName)
        arcName = geotiffExportName + '.tif'
        geotiff_writer.writeData('meta.json', dumps(metaJson))
        geotiff_writer.addFile(fullFilePath, geotiffExportName + '/' + arcName)  # double check this line (second arg may not be necessary)
        self.geotiffExportName = '%s.tar.gz' % geotiffExportName
        self.geotiffExport.save(self.geotiffExportName,
                                ContentFile(geotiff_writer.getData()))

    
    def generateKmlExport(self, exportName, metaJson, slug):
        """
        this generates the kml and the tiles.
        """
        overlay = Overlay.objects.get(alignedQuadTree = self)
        imageSizeType = overlay.imageData.sizeType
        now = datetime.datetime.utcnow()
        timestamp = now.strftime('%Y-%m-%d-%H%M%S-UTC')
        
        kmlExportName = exportName + ('-%s-kml_%s' % (imageSizeType, timestamp))
        kmlFolderPath = settings.DATA_ROOT + 'geocamTiePoint/export/' + kmlExportName
        
        # get the path to latest geotiff file
        if '.tar.gz' in self.geotiffExportName:
            filename = self.geotiffExportName.replace('.tar.gz', '')
        inputFile = settings.DATA_ROOT + 'geocamTiePoint/export/' + filename + '/' + filename + ".tif"
        #TODO: make this call the gdal2tiles
        
        g2t = gdal2tiles.GDAL2Tiles(["--force-kml", str(inputFile), str(kmlFolderPath)])
        g2t.process()
        
        # tar the kml
        kml_writer = quadTree.TarWriter(kmlExportName)
        kml_writer.writeData('meta.json', dumps(metaJson))
        kml_writer.addFile(kmlFolderPath, kmlExportName)  # double check. second arg may not be necessary
        self.kmlExportName = '%s.tar.gz' % kmlExportName
        self.kmlExport.save(self.kmlExportName, 
                            ContentFile(kml_writer.getData()))      
        
        
class Overlay(models.Model):
    # required fields 
    key = models.AutoField(primary_key=True, unique=True)
    lastModifiedTime = models.DateTimeField()
    name = models.CharField(max_length=50)
    # optional fields
    # author: user who owns this overlay in the system
    author = models.ForeignKey(User, null=True, blank=True)
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
    centerLat = models.FloatField(null=True, blank=True, default=0)
    centerLon = models.FloatField(null=True, blank=True, default=0) 
    
    nadirLat = models.FloatField(null=True, blank=True, default=0)
    nadirLon = models.FloatField(null=True, blank=True, default=0) 
    
    # extras: a special JSON-format field that holds additional
    # schema-free fields in the overlay model. Members of the field can
    # be accessed using dot notation. currently used extras subfields
    # include: imageSize, points, transform, bounds, centerLat, centerLon, rotatedImageSize
    extras = ExtrasDotField()
    # import/export configuration
    readyToExport = models.BooleanField(default=False)
    # true if output product (geotiff, RMS error, etc) has been written to file. 
    writtenToFile = models.BooleanField(default=False)
    # exportFields: export these fields to the client side (as JSON)
    exportFields = ('key', 'lastModifiedTime', 'name', 'description', 
                    'imageSourceUrl', 'creator', 'readyToExport', 
                    'centerLat', 'centerLon', 'nadirLat', 'nadirLon')
    # importFields: import these fields from the client side and save their values to the database.
    importFields = ('name', 'description', 'imageSourceUrl', 'readyToExport', 
                    'centerLat', 'centerLon', 'nadirLat', 'nadirLon')
    importExtrasFields = ('points', 'transform')

    def getRawImageData(self):
        """
        Returns the original image data created upon image upload (not rotated, not enhanced)
        """
        try:
            imageData = ImageData.objects.filter(overlay__key = self.key).filter(raw = True)
            return imageData[0]
        except:
            # print "Error: no raw image data available"
            return None
        

    def getAlignedTilesUrl(self):
        if self.isPublic:
            urlName = 'geocamTiePoint_publicTile'
        else:
            urlName = 'geocamTiePoint_tile'
        return reverse(urlName,
                       args=[str(self.alignedQuadTree.id)])

    def getJsonDict(self):
        # export all schema-free subfields of extras
        result = self.extras.copy()
        # export other schema-controlled fields of self (listed in exportFields)
        for key in self.exportFields:
            val = getattr(self, key, None)
            if val not in ('', None):
                result[key] = val
        # conversions
        result['lmt_datetime'] = result['lastModifiedTime'].strftime('%F %k:%M')
        result['lastModifiedTime'] = (result['lastModifiedTime']
                                      .replace(microsecond=0)
                                      .isoformat()
                                      + 'Z')
        # calculate and export urls for client convenience
        result['url'] = reverse('geocamTiePoint_overlayIdJson', args=[self.key])
        try: 
            deepzoomRoot = settings.DEEPZOOM_ROOT.replace(settings.PROJ_ROOT, '/')
            deepzoomFile = self.imageData.associated_deepzoom.name + '/' + self.imageData.associated_deepzoom.name + '.dzi'
            result['deepzoom_path'] = deepzoomRoot + deepzoomFile
        except: 
            pass
        # set image size
        result['imageSize'] = [self.imageData.width, self.imageData.height]
        if 'issMRF' not in result:
            result['issMRF'] = self.imageData.issMRF
        if self.unalignedQuadTree is not None:
            result['unalignedTilesUrl'] = reverse('geocamTiePoint_tile',
                                                  args=[str(self.unalignedQuadTree.id)])
            result['unalignedTilesZoomOffset'] = quadTree.ZOOM_OFFSET
        if self.alignedQuadTree is not None:
            result['alignedTilesUrl'] = self.getAlignedTilesUrl()
            # note: when exportZip has not been set, its value is not
            # None but <FieldFile: None>, which is False in bool() context
        # include image enhancement values as part of json. 
        if self.imageData is not None:
            try: 
                result['rotationAngle'] = self.imageData.rotationAngle
                result['brightness'] = self.imageData.brightness
                result['contrast'] = self.imageData.contrast
                result['autoenhance'] = self.imageData.autoenhance
            except:
                pass
        try:
            mission, roll, frame = self.name.split('-')
            result['mission'] = mission
            result['roll'] = roll
            result['frame'] = frame[:-4]
        except:
            pass
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

        # get the image enhancement values and save it to the overlay's imagedata.
        imageDataDict = {}
        imageDataDict['rotationAngle'] = jsonDict.get('rotationAngle', MISSING)
        imageDataDict['contrast'] = jsonDict.get('contrast', MISSING)
        imageDataDict['brightness'] = jsonDict.get('brightness', MISSING)
        imageDataDict['autoenhance'] = jsonDict.get('autoenhance', MISSING)
        for key, value in imageDataDict.items():
            if value is not MISSING:
                try:
                    setattr(self.imageData, key, value)
                except:
                    print "failed to save image data values from the json dict returned from client"
        self.imageData.save()

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
        return 'georef-%s' % self.getSlug()

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
        originalImageData = self.getRawImageData()
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
        
        
#########################################
# models for autoregistration pipeline  #
#########################################
class IssTelemetry(models.Model):
    issMRF = models.CharField(max_length=255, null=True, blank=True, help_text="Please use the following format: <em>[Mission ID]-[Roll]-[Frame number]</em>") 
    x = models.FloatField(null=True, blank=True, default=0)
    y = models.FloatField(null=True, blank=True, default=0)
    z = models.FloatField(null=True, blank=True, default=0)
    r = models.FloatField(null=True, blank=True, default=0)
    p = models.FloatField(null=True, blank=True, default=0)
    y = models.FloatField(null=True, blank=True, default=0)


class AutomatchResults(models.Model):
    issMRF = models.CharField(max_length=255, unique=True, help_text="Please use the following format: <em>[Mission ID]-[Roll]-[Frame number]</em>") 
    matchedImageId = models.CharField(max_length=255, blank=True)
    matchConfidence = models.CharField(max_length=255, blank=True)
    matchDate = models.DateTimeField(null=True, blank=True)
    capturedTime = models.DateTimeField(null=True, blank=True)
    centerPointSource = models.CharField(max_length=255, blank=True, help_text="source of center point. Either curated, CEO, GeoSens, or Nadir")
    centerLat = models.FloatField(null=True, blank=True, default=0)
    centerLon = models.FloatField(null=True, blank=True, default=0) 
    registrationMpp = models.FloatField(null=True, blank=True, default=0)
    extras = ExtrasDotField() # stores tie point pairs
    metadataExportName = models.CharField(max_length=255,
                                          null=True, blank=True)
    metadataExport = models.FileField(upload_to=getNewExportFileName,
                                      max_length=255,
                                      null=True, blank=True)
    writtenToFile = models.BooleanField(default=False)
    

class GeoSens(models.Model):
    issMRF = models.CharField(max_length=255, help_text="Please use the following format: <em>[Mission ID]-[Roll]-[Frame number]</em>") 
    r = models.FloatField(null=True, blank=True, default=0)
    p = models.FloatField(null=True, blank=True, default=0)
    y = models.FloatField(null=True, blank=True, default=0)
    centerLat = models.FloatField(null=True, blank=True, default=0)
    centerLon = models.FloatField(null=True, blank=True, default=0) 
