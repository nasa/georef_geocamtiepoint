var maputils = maputils || {};

$(function($) {
    /*
     * Map helper stuff... cleaned up versions of code formerly found in
     * overlay-view.js Probably this stuff should find a new home.
     * Depends upon constants defined in in coords.js.  and
     * fitNamedBounds, defined in utils.js
    */

    maputils.handleNoGeolocation = function(gmap, errorFlag) {
        assert(! _.isUndefined(fitNamedBounds),
               'Missing global: fitNamedBounds');
        fitNamedBounds(settings.GEOCAM_TIE_POINT_DEFAULT_MAP_VIEWPORT,
                       gmap);
    };

    maputils.ImageMapType = function(overlayModel) {
        assert(typeof TILE_SIZE !== 'undefined',
               'Missing global: TILE_SIZE');
        assert(typeof MIN_ZOOM_OFFSET !== 'undefined',
               'Missing global: MIN_ZOOM_OFFSET');
        var levelsPast =
            settings.GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION;
        assert(typeof levelsPast !== 'undefined',
               'Missing: settings.' +
               'GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION');
        return new google.maps.ImageMapType({
            getTileUrl: overlayModel.getImageTileUrl,
            tileSize: new google.maps.Size(TILE_SIZE, TILE_SIZE),
            maxZoom: (overlayModel.maxZoom() + levelsPast),
            minZoom: MIN_ZOOM_OFFSET,
            name: 'image-map'
        });
    };

    maputils.AlignedImageMapType = function(overlayModel) {
        assert(typeof TILE_SIZE !== 'undefined',
               'Missing global: TILE_SIZE');
        assert(typeof MIN_ZOOM_OFFSET !== 'undefined',
               'Missing global: MIN_ZOOM_OFFSET');
        var levelsPast =
            settings.GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION;
        assert(typeof levelsPast !== 'undefined',
               'Missing: settings.' +
               'GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION');
        return new google.maps.ImageMapType({
            getTileUrl: overlayModel.getAlignedImageTileUrl,
            tileSize: new google.maps.Size(TILE_SIZE, TILE_SIZE),
            maxZoom: (overlayModel.maxZoom() + levelsPast),
            minZoom: MIN_ZOOM_OFFSET,
            name: 'image-map'
        });
    };


	function copyToClipboard(text) {
	  window.prompt("Copy to clipboard: Ctrl+C, Enter", text);
	}

	maputils.createCenterPointLabelText = function createCenterPointLabelText(lat, lon) {
		return "lat,lon:"+lat+","+lon;
	};
	
    maputils.createCenterPointMarker = function(latLng, label, map, options) {
    	var image = '/static/geocamTiePoint/images/crosshairs.png';
    	var markerOpts = {
            title: "center point",
            draggable: false,
		    position: latLng,
		    map: map,
		    raiseOnDrag: false, 
		    label: label,
		    icon: image
		    
		};
		markerOpts = _.extend(markerOpts, options);
		var marker = new google.maps.Marker(markerOpts);
		marker.label.span.setAttribute("class", "centerpoint-label")
		google.maps.event.addListener(marker, 'click', function() {
			copyToClipboard(marker.label.text);
		});
        return marker;
    };

    maputils.createLabeledMarker = function(latLng, label, map, options) {
        var unselectedIcon =
            'https://maps.gstatic.com/mapfiles/markers2/marker_blank.png';
        var selectedIcon =
            'https://maps.google.com/intl/en_us/mapfiles/ms/micons/blue.png';
        
        var markerOpts = {
            title: '' + label,
            draggable: true,
		    position: latLng,
		    map: map,
		    icon: new google.maps.MarkerImage(unselectedIcon),
		    label: label,
		    raiseOnDrag: false
		};
		markerOpts = _.extend(markerOpts, options);
		
		var marker = new google.maps.Marker(markerOpts);
        google.maps.event.addListener(marker, 'selected_changed', function() {
            marker.setIcon(marker.get('selected') ?
                           selectedIcon :
                           unselectedIcon);
        });
		
        return marker;
    };
    

    maputils.locationSearchBar = function(search_bar, map) {
        // expecting search_bar to either be a selector string or a
        // jquery object.
        var input = _.isString(search_bar) ? $(search_bar)[0] : search_bar[0];
        var autoComplete = new google.maps.places.SearchBox(input);

        autoComplete.bindTo('bounds', map);

        var infoWindow = new google.maps.InfoWindow();
        var marker = new google.maps.Marker({
            map: map
        });

        (google.maps.event.addListener
         (autoComplete, 'places_changed', function() {
            infoWindow.close();
            var place = autoComplete.getPlaces()[0];
            if (place.geometry.viewport) {
                map.fitBounds(place.geometry.viewport);
            } else {
                map.setCenter(place.geometry.location);
                map.setZoom(17);
            }

            var address = '';
            if (place.address_components) {
                address = [(place.address_components[0] &&
                            place.address_components[0].short_name || ''),
                           (place.address_components[1] &&
                            place.address_components[1].short_name || ''),
                           (place.address_components[2] &&
                            place.address_components[2].short_name || '')
                          ].join(' ');
            }

            infoWindow.setContent('<div><strong>' + place.name +
                                  '</strong><br>' +
                                  address + '</div>');
            infoWindow.open(map, marker);
        }));

    };


    maputils.fitMapToBounds = function(map, bounds) {
        // Source: https://gist.github.com/1255671
        map.fitBounds(bounds);   // does the job asynchronously
        (google.maps.event.addListenerOnce
         (map, 'bounds_changed', function(event) {
             // the span of the map set by Google fitBounds (always
             // larger by what we ask)
             var newSpan = map.getBounds().toSpan();
             // the span of what we asked for
             var askedSpan = bounds.toSpan();
             // the % of increase on the latitude
             var latRatio = (newSpan.lat() / askedSpan.lat()) - 1;
             // the % of increase on the longitude
             var lngRatio = (newSpan.lng() / askedSpan.lng()) - 1;
             // if the % of increase is too big (> to a threshold) we zoom in
             if (Math.min(latRatio, lngRatio) > 0.46) {
                 // 0.46 is the threshold value for zoming in. It has
                 // been established empirically by trying different
                 // values.
                 this.setZoom(map.getZoom() + 1);
             }
         }));
    }

});


// helper needed for transparency and rotation sliders.
maputils.findPosLeft = function(obj) {
	var curleft = 0;
    if (obj.offsetParent) {
        do {
            curleft += obj.offsetLeft;
        } while (obj = obj.offsetParent);
        return curleft;
    }
    return undefined;
};



maputils.pixelToCart = function(pixel, width, height) {
	//need to add 0.5 to pixel coords
	var pixelX = pixel.x + 0.5;
	var pixelY = pixel.y + 0.5;
	var cartX = pixelX - width/2;
	var cartY = -1*pixelY + height/2;
	return [parseFloat(cartX), parseFloat(cartY)];
};


maputils.cartToPixel = function(cart, width, height) {
	var pixelX = parseFloat(cart[0]) + width/2;
	var pixelY = height/2 - parseFloat(cart[1]);
	// need to subtract 0.5 from cartesian coords
	pixelX = pixelX - 0.5;
	pixelY = pixelY - 0.5;
	return {x: parseInt(pixelX), y: parseInt(pixelY)};
};


maputils.rotateTiePt = function(pixelCoord, overlay){
	var angle = overlay.get('totalRotation');
	if (angle == 0) { // if no rotation, return pt as pixel coord.
		return pixelCoord;
	} 
	angle = -1* angle; // need to rotate counter clock wise.
	// get center pt of unrotate image in pixel coords
	var imageSize = overlay.get('orgImageSize');
	var width = parseFloat(imageSize[0]);
	var height = parseFloat(imageSize[1]);
    // convert angle to theta
    var theta = angle * (Math.PI / 180); 
    // construct rotation matrix
    var rotateMatrix = new Matrix(3, 3,
            [[Math.cos(theta), -Math.sin(theta), 0],
             [Math.sin(theta), Math.cos(theta), 0],
             [0, 0, 1]]);
    // transform the pt so that center pt becomes the origin.
	var cart = maputils.pixelToCart(pixelCoord, width, height);
    // put tie point in a 3 x 1 matrix.
    var tiePt = new Matrix(1,3, [[cart[0]],
                                 [cart[1]],
                                 [1]]);
    var transformedTiePt = rotateMatrix.multiply(tiePt).values;
	// get center pt of rotated image in pixel coords
	var rotatedImageSize = overlay.get('rotatedImageSize');
	var rwidth = parseFloat(rotatedImageSize[0]);
	var rheight = parseFloat(rotatedImageSize[1]);
	console.log("size of the rotated image", rwidth + ',  ' + rheight);
	// convert back to pixel coords.
    var pixel = maputils.cartToPixel(transformedTiePt, rwidth, rheight);
    // transform the tie point back by adding back the center pt offset.
    return pixel;
};


//set up a rotation slider on image side
maputils.createRotationControl = function(imageQtreeView, mapType) {//function(map, mapType, overlay) {
	var map = imageQtreeView.gmap;
	var overlay = imageQtreeView.model;
	var ROTATION_MAX_PIXELS = 57; //slider spans 57 pixels
	var sliderImageUrl = '/static/geocamTiePoint/images/rotation_slider.png';
	
	//create slider bar
	var rotationSliderDiv = document.createElement('DIV');
	(rotationSliderDiv.setAttribute
     ('style',
      'margin: 5px;' +
      ' overflow-x: hidden;' +
      ' overflow-y: hidden;' +
      ' background: url(' + sliderImageUrl + ') no-repeat;' +
      ' width: 71px;' +
      ' height: 21px;' +
      ' cursor: pointer;'));
	
	//create knob
    var rotationKnobDiv = document.createElement('DIV');
    (rotationKnobDiv.setAttribute
     ('style',
      'padding: 0;' +
      ' margin: 0;' +
      ' overflow-x: hidden;' +
      ' overflow-y: hidden;' +
      ' background: url(' + sliderImageUrl + ') no-repeat -71px 0;' +
      ' width: 14px;' +
      ' height: 21px;'));
    rotationSliderDiv.appendChild(rotationKnobDiv);
    
    //create text input box div
    var rotationInputDiv = document.createElement('DIV');
    var rotationInputSpan = document.createElement('span');
    rotationInputSpan.className = "input-prepend";
    spanAddOn = document.createElement('span');
    spanAddOn.className = "add-on";
    spanAddOn.innerHTML = "Rotate";
    rotationInputSpan.appendChild(spanAddOn);
    //text box
    var rotationInput = document.createElement("input");
    rotationInput.type = "text";
    rotationInput.placeholder = "Angle";
    rotationInput.id = "rotationAngle"; 
    rotationInputSpan.appendChild(rotationInput);

    var rotationCtrlKnob = new ExtDraggableObject(rotationKnobDiv, {
        restrictY: true,
        container: rotationSliderDiv
    });
    
    google.maps.event.addListener(rotationCtrlKnob, 'drag', function() {
    	var angle = getAngle(mapType, rotationCtrlKnob.valueX());
    	rotationInput.value = angle | 0;
    	//TODO: do some fancy transparency overlay here using initAlignedOverlay to show
        //what the rotation will potentially look like.
	});
	
	google.maps.event.addDomListener(rotationSliderDiv, 'click', function(e) {
        var x = rotationCtrlKnob.valueX();
        var angle = getAngle(mapType, x);
		// add the angle to the total angles dictionary
        var data = new FormData();
		data.append('rotation', parseInt(angle));
		data.append('overlayId', overlay.id);
		// make a call to the server to generate new tiles from rotated image.
		$.ajax({
			url: rotateOverlayUrl,
			crossDomain: false,
			data: data,
			cache: false, 
			contentType: false, 
			processData: false,
			type: 'POST', 
            success: (_.bind (submitSuccess,
                     this)),
            error: (_.bind (submitError,
                   this))
		});
	});
	
	function submitSuccess(data) {
		console.log('got data back from rotate');
        try {
            var json = JSON.parse(data);
        } catch (error) {
            console.log('Failed to parse response as JSON: ' +
                        error.message);
            return;
        }
        if (json['status'] == 'success') {
        	console.log("json angle", json['angle']);
    		overlay.fetch({ 'success': function (overlay) {
    			imageQtreeView.render();
    		}});
        }
	}
	
	function submitError() {
		
	}
	
    function getAngle(mapType, pixelX) {
        // pixelX in range 0 to ROTATION_MAX_PIXELS
        var rotationAngle = 360 * (pixelX / ROTATION_MAX_PIXELS);
        // max angle value goes slightly over 360 so set it to 360 if it does.
        if (rotationAngle > 360) rotationAngle = 360;
        return Math.round(rotationAngle);
    }

    map.controls[google.maps.ControlPosition.TOP_RIGHT].push(rotationInputSpan);
    map.controls[google.maps.ControlPosition.RIGHT_TOP].push(rotationSliderDiv);
};


//maputils.testRotateTiePt = function() {
//	var angle = 90;
//	var pixelCoord = {x: 6, y: 1};
//	
//	if (angle == 0) { // if no rotation, return pt as pixel coord.
//		return pixelCoord;
//	} 
//	// get center pt in pixel coords
//	var width = 9;
//	var height = 7;
//	
//    // convert angle to theta
//    var theta = angle * (Math.PI / 180); 
//    
//    // construct rotation matrix
//    var rotateMatrix = new Matrix(3, 3,
//            [[Math.cos(theta), -Math.sin(theta), 0],
//             [Math.sin(theta), Math.cos(theta), 0],
//             [0, 0, 1]]);
//    
//    // transform the pt so that center pt becomes the origin.
//	var cart = maputils.pixelToCart(pixelCoord, width, height);
//    
//    // put tie point in a 3 x 1 matrix.
//    var tiePt = new Matrix(1,3, [[cart[0]],
//                                 [cart[1]],
//                                 [1]]);
//    var transformedTiePt = rotateMatrix.multiply(tiePt).values;
//    
//    console.log("rotated tie point in cartesian: ", transformedTiePt);
//    
//    // convert back to pixel coords.
//    var pixel = maputils.cartToPixel(transformedTiePt, width, height);
//    console.log("in pixel coords: ", pixel);
//    
//    // transform the tie point back by adding back the center pt offset.
//    return pixel;
//};


//set up a transparency slider
maputils.createOpacityControl = function(map, mapType, overlay) {
    var OPACITY_MAX_PIXELS = 57;
    var sliderImageUrl = '/static/geocamTiePoint/images/opacity-slider3d6.png';
    // Create main div to hold the control.
    var opacityDiv = document.createElement('DIV');
    (opacityDiv.setAttribute
     ('style',
      'margin: 5px;' +
      ' overflow-x: hidden;' +
      ' overflow-y: hidden;' +
      ' background: url(' + sliderImageUrl + ') no-repeat;' +
      ' width: 71px;' +
      ' height: 21px;' +
      ' cursor: pointer;'));

    // Create knob
    var opacityKnobDiv = document.createElement('DIV');
    (opacityKnobDiv.setAttribute
     ('style',
      'padding: 0;' +
      ' margin: 0;' +
      ' overflow-x: hidden;' +
      ' overflow-y: hidden;' +
      ' background: url(' + sliderImageUrl + ') no-repeat -71px 0;' +
      ' width: 14px;' +
      ' height: 21px;'));
    opacityDiv.appendChild(opacityKnobDiv);

    var opacityCtrlKnob = new ExtDraggableObject(opacityKnobDiv, {
                            restrictY: true,
                            container: opacityDiv
    });

    google.maps.event.addListener(opacityCtrlKnob, 'drag', function() {
            setOpacity(mapType, opacityCtrlKnob.valueX());
    });

    google.maps.event.addDomListener(opacityDiv, 'click', function(e) {
        var left = maputils.findPosLeft(this);
        var x = e.pageX - left - 5;
        opacityCtrlKnob.setValueX(x);
        setOpacity(mapType, x);
    });

    var opacity = overlay.overlayOpacity;
    map.controls[google.maps.ControlPosition.TOP_RIGHT].push(opacityDiv);
    var initialValue = OPACITY_MAX_PIXELS / (100 / opacity);
    opacityCtrlKnob.setValueX(initialValue);
    setOpacity(mapType, initialValue);

    function setOpacity(mapType, pixelX) {
        // pixelX in range 0 to OPACITY_MAX_PIXELS
        var opacityPercent = (100 / OPACITY_MAX_PIXELS) * pixelX;

        if (opacityPercent < 0) opacityPercent = 0;
        if (opacityPercent > 100) opacityPercent = 100;

        //console.log("opacity: " + opacityPercent);
        overlay.overlayOpacity = opacityPercent;
        mapType.setOpacity(opacityPercent / 100.0);
    }

};

