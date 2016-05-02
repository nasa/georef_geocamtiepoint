# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

# from django.conf.urls import patterns, url, include
# from django.shortcuts import redirect
# from django.core.urlresolvers import reverse

from django.conf.urls import include, url

from django.views.generic.base import TemplateView
from geocamTiePoint import views


urlpatterns = [ ## New Workflow ##
                url(r'^b/$', views.backbone,
                    {}, 'geocamTiePoint_backbone'),
            
                ## for export data products (kml, geotiff, html) ##
                url(r'^getExportFilesList$', views.getExportFilesList, 
                    {}, 'geocamTiePoint_getExportFilesList'),
            
                url(r'^getExportFile/(?P<name>.*)$', views.getExportFile,
                    {}, 'geocamTiePoint_getExportFile'),
            
                ## transform.js sends a ajax request to retrieve camera model transform value from server side. ##
                url(r'^cameraModelTransformFit/$', views.cameraModelTransformFit, 
                    {}, 'geocamTiePoint_cameraModelTransformFit'),
                
                ## transform.js sends a ajax request to retrieve tformed pt in meters from server side. ##
                url(r'^cameraModelTransformForward/$', views.cameraModelTransformForward, 
                    {}, 'geocamTiePoint_cameraModelTransformForward'),
                
                ## rotation slider sends ajax request to create a new overlay with rotated image ##
                url(r'^rotateOverlay/$', views.rotateOverlay, 
                    {}, 'geocamTiePoint_rotateOverlay'), 
                
                ## image enhancement requests from the client handled here
                url(r'^enhanceContrast/$', views.createEnhancedImageTiles, 
                    {}, 'geocamTiePoint_createEnhancedImageTiles'),    
                
                ## overlays ##
                url(r'^overlays/new\.json$', views.overlayNewJSON,
                    {}, 'geocamTiePoint_overlayNew_JSON'),
                                   
                ## Urls to make current pages work with new workflow ##
                url(r'^overlays/list\.html$', lambda request: redirect(reverse('geocamTiePoint_backbone') + '#overlays/'),
                    {}, 'geocamTiePoint_overlayIndex'),
            
                url(r'^overlays/new\.html$', lambda request: redirect(reverse('geocamTiePoint_backbone') + '#overlays/new'),
                    {}, 'geocamTiePoint_overlayNew'),
            
                url(r'^overlay/(?P<key>\d+)/generateExport/(?P<type>\w+)$', views.overlayGenerateExport,
                    {}, 'geocamTiePoint_overlayGenerateExport'),
                                   
                ## for integrating with Catalog ## 
                url(r'^catalog/(?P<mission>\w+)/(?P<roll>\w+)/(?P<frame>\d+)/(?P<sizeType>\w+)/$', views.createOverlayAPI, 
                    {}, 'geocamTiePoint_createOverlayAPI'),
                
                # duplicate url that starts with 'backend' so we can set 'login: admin'
                # on the backend version of the view.
                url(r'^backend/overlay/(?P<key>\d+)/generateExport/$', views.overlayGenerateExport,
                    {}, 'geocamTiePoint_overlayGenerateExportBackend'),
            
                url(r'^overlay/(?P<key>\d+)/export/(?P<type>\w+)/(?P<fname>[^/]*)$', views.overlayExport,
                    {}, 'geocamTiePoint_overlayExport'),
                
                url(r'^overlay/(?P<key>\d+)/delete\.html$', views.overlayDelete,
                    {}, 'geocamTiePoint_overlayDelete'),
            
                url(r'^overlay/(?P<key>\d+)/simpleViewer_(?P<slug>[^/\.]*)\.html$', views.simpleAlignedOverlayViewer,
                    {}, 'geocamTiePoint_simpleAlignedOverlayViewer'),
            
                ## Image storage pass-thru ##
                url(r'^tile/(?P<quadTreeId>\d+)/$',
                    views.dummyView,
                    {}, 'geocamTiePoint_tileRoot'),
            
                url(r'^tile/(?P<quadTreeId>[^/]+)/\[ZOOM\]/\[X\]/\[Y\].png$',
                    views.getTile,
                    {}, 'geocamTiePoint_tile'),
                                   
                url(r'^tile/(?P<quadTreeId>[^/]+)/(?P<zoom>[^/]+)/(?P<x>[^/]+)/(?P<y>[^/]+)$',
                    views.getTile,
                    {}, 'geocamTiePoint_tile'),
            
                url(r'^public/tile/(?P<quadTreeId>[^/]+)/(?P<zoom>[^/]+)/(?P<x>[^/]+)/(?P<y>[^/]+)$',
                    views.getPublicTile,
                    {}, 'geocamTiePoint_publicTile'),
            
                url(r'^public/tile/(?P<quadTreeId>[^/]+)/\[ZOOM\]/\[X\]/\[Y\].png$',
                    views.getPublicTile,
                    {}, 'geocamTiePoint_publicTile'),
            
                url(r'^overlay/(?P<key>\d+)/(?P<fileName>\S+)$',
                    views.overlayIdImageFileName,
                    {}, 'geocamTiePoint_overlayIdImageFileName'),
            
                ## JSON API ##
                url(r'^overlay/(?P<key>\d+).json$', views.overlayIdJson,
                    {}, 'geocamTiePoint_overlayIdJson'),
            
                ## testing ui demo ##
                url(r'^overlays\.json$', views.overlayListJson,
                    {}, 'geocamTiePoint_overlayListJson'),
            
                url(r'^gc/(?:(?P<dryRun>\d+)/)?$', views.garbageCollect,
                    {}, 'geocamTiePoint_garbageCollect')
    ]
