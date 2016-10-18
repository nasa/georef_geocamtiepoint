//    app.views.ImageQtreeView = app.views.OverlayGoogleMapsView.extend({
//        template: '<div id="image_canvas"></div>',
//
//        beforeRender: function() {
//            // somebody set us up the global variable!
//            window.maxZoom0G = this.model.maxZoom();
//        },
//
//        afterRender: function() {
//            app.gmap = new google.maps.Map(this.$('#image_canvas')[0], {
//                zoom: MIN_ZOOM_OFFSET,
//                streetViewControl: false,
//                backgroundColor: 'rgb(192, 192, 192)',
//                mapTypeControl: false,
//                draggableCursor: 'crosshair'
//            });
//            var gmap = app.gmap;
//
//            // disable 45-degree imagery
//            gmap.setTilt(0);
//
//            // initialize viewport to contain image
//            var imageSize = this.model.get('imageSize');
//            var w = imageSize[0];
//            var h = imageSize[1];
//            var maxZoom = this.model.maxZoom();
//
//            gmap.mapTypes.set('image-map', maputils.ImageMapType(this.model));
//            gmap.setMapTypeId('image-map');
//            this.gmap = gmap;
//
//            this.gmap.fitBounds(this.model.imageBounds());
//
//            (google.maps.event.addListenerOnce
//    		(this.gmap, 'idle', _.bind(function() { 
//    			 var imageQtreeView = this;
//    			 imageQtreeView.drawMarkers();
//    			 imageQtreeView.drawCenterPointMarker.apply(imageQtreeView);
//    			 imageQtreeView.trigger('gmap_loaded');
//                 if (imageQtreeView.options.debug) imageQtreeView.debugInstrumentation.apply(imageQtreeView);
//                 //add rotation control slider
//                 var mapType = new maputils.ImageMapType(imageQtreeView.model);
//                 maputils.createRotationControl(imageQtreeView);
//                 // submit rotation on enter 
//                 $("form#rotationInputForm").submit(function() {
//                	 event.preventDefault();
//					 var angle = parseInt($("input#rotationAngle")[0].value);
//					 var data = new FormData();
//					 data.append('rotation', angle);
//					 var overlayId = parseInt($("input#overlayId")[0].value);
//                	 data.append('overlayId', overlayId);
//                	 // set the rotateKnob position
//                	 rotateKnobPosition = maputils.getRotationSliderPosition(angle);
//                	 // save current zoom level
//                	 var zoom = imageQtreeView.gmap.zoom;
//                	 // submit the rotation angle to the server to generate new tiles for rotated image.
//					 maputils.submitRequestToServer(rotateOverlayUrl, data, imageQtreeView);
//             	}, event, imageQtreeView);
//                 //add image enhancement control sliders
//                 maputils.createImageEnhacementControls(imageQtreeView);
//    		}, this)));
//        },
//        
//        // markers are redrawn after event.
//        drawMarkers: function() {
//        	var model = this.model;
//        	var latLons_in_gmap_space = [];
//            _.each(model.get('points'), function(point) {
//                var pixelCoords = { x: point[2], y: point[3] };
//                if (! _.any(_.values(pixelCoords), _.isNull)) {
//                	// if overlay has been rotated, redraw the markers in rotated frame.
//                	// rotateTiePt handles the case where rotation = 0
//                	var angle = model.get('totalRotation');
//                	var rotatedCoords = maputils.rotateTiePt(pixelCoords, model);
//                	var latLon = pixelsToLatLon(rotatedCoords, model.maxZoom());
//                	latLons_in_gmap_space.push(latLon);
//                }
//            });
//            // when markers are drawn, calculate the center point too.
//            model.fetch({ 'success': function(model) {
//            	model.updateCenterPoint();
//				// update the marker title
//            	var lat = model.get('centerLat');
//            	var lon = model.get('centerLon');
//				var centerPtLabel = maputils.createCenterPointLabelText(lat, lon);
//				centerPointMarker.title = centerPtLabel;
//        	}});
//			return this._drawMarkers(latLons_in_gmap_space);
//        },
//        
//		drawCenterPointMarker: function() {
//            // rotate the center by rotation angle in overlay.
//			var model = this.model;
//            var rotationAngle = model.get('totalRotation');
//            var imageSize = null;
//            if (rotationAngle == 0) {
//            	imageSize = model.get('imageSize');
//            } else {
//            	imageSize = model.get('rotatedImageSize');
//            }
//            var w = imageSize[0];
//            var h = imageSize[1];
//            var maxZoom = model.maxZoom();
//            var centerImageViewLatLon = pixelsToLatLon({x: w / 2.0 , y: h / 2.0}, maxZoom);
//            
//            // get the calculated center pt lat lon from the overlay model.    
//            var centerLat = model.get('centerLat');
//            var centerLon = model.get('centerLon');
//            if (centerLat && centerLon) {
//	            centerPointMarker = maputils.createCenterPointMarker(centerImageViewLatLon,
//	            		centerLat, centerLon,
//	            		this.gmap);
//            }
//		},
//		
//        updateTiepointFromMarker: function(index, marker, drawMarkerFlag) {
//        	//drawMarker flag is set to true unless specified by passing 'false' as an arg.
//        	drawMarkerFlag = typeof drawMarkerFlag !== 'undefined' ? drawMarkerFlag : true;
//            var coords = latLonToPixel(marker.getPosition());
//            this.model.updateTiepoint('image', index, coords, drawMarkerFlag);
//        }
//
//    }); // end ImageQtreeView