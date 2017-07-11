//__BEGIN_LICENSE__
// Copyright (c) 2017, United States Government, as represented by the
// Administrator of the National Aeronautics and Space Administration.
// All rights reserved.
//
// The GeoRef platform is licensed under the Apache License, Version 2.0
// (the "License"); you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// http://www.apache.org/licenses/LICENSE-2.0.
//
// Unless required by applicable law or agreed to in writing, software distributed
// under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied. See the License for the
// specific language governing permissions and limitations under the License.
//__END_LICENSE__

var maputils = maputils || {};

$(function($) {
	/*
	 * Map helper stuff... cleaned up versions of code formerly found in
	 * overlay-view.js Probably this stuff should find a new home. Depends upon
	 * constants defined in in coords.js. and fitNamedBounds, defined in
	 * utils.js
	 */
	maputils.handleNoGeolocation = function(gmap, errorFlag) {
		assert(!_.isUndefined(fitNamedBounds), 'Missing global: fitNamedBounds');
		fitNamedBounds(settings.GEOCAM_TIE_POINT_DEFAULT_MAP_VIEWPORT, gmap);
	};

	maputils.ImageMapType = function(overlayModel) {
		assert(typeof TILE_SIZE !== 'undefined', 'Missing global: TILE_SIZE');
		assert(typeof MIN_ZOOM_OFFSET !== 'undefined',
		'Missing global: MIN_ZOOM_OFFSET');
		var levelsPast = settings.GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION;
		assert(typeof levelsPast !== 'undefined', 'Missing: settings.'
				+ 'GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION');
		return new google.maps.ImageMapType({
			getTileUrl : overlayModel.getImageTileUrl,
			tileSize : new google.maps.Size(TILE_SIZE, TILE_SIZE),
			maxZoom : (overlayModel.maxZoom() + levelsPast),
			minZoom : MIN_ZOOM_OFFSET,
			name : 'image-map'
		});
	};

	maputils.AlignedImageMapType = function(overlayModel) {
		assert(typeof TILE_SIZE !== 'undefined', 'Missing global: TILE_SIZE');
		assert(typeof MIN_ZOOM_OFFSET !== 'undefined',
		'Missing global: MIN_ZOOM_OFFSET');
		var levelsPast = settings.GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION;
		assert(typeof levelsPast !== 'undefined', 'Missing: settings.'
				+ 'GEOCAM_TIE_POINT_ZOOM_LEVELS_PAST_OVERLAY_RESOLUTION');
		return new google.maps.ImageMapType({
			getTileUrl : function(coord, zoom) {
				return overlayModel.getAlignedImageTileUrl(coord, zoom);
			},
			tileSize : new google.maps.Size(TILE_SIZE, TILE_SIZE),
			maxZoom : (overlayModel.maxZoom() + levelsPast),
			minZoom : MIN_ZOOM_OFFSET,
			name : 'image-map'
		});
	};

	maputils.latLonToCatalogBingMapsClipboardScript = function(lat, lon) {
		return "http://www.bing.com/maps/&cp="+lat+"~"+lon;
	};

	maputils.getLatLonFromMarkerTitle = function(marker) {
		if (marker.title.indexOf(":") != -1) { //if marker title contains ":"
			var latlon = marker.title.split(":")[1].split(",");
			return latlon;
		}
	};

	maputils.copyToClipboard = function (lat,lon, text) {
		window.prompt("Copy lat,lon: "+lat+", "+lon+" to clipboard: Ctrl+C", text);
	};
	
	maputils.createLabeledMarker = function(latLng, label, map, options) {
		var unselectedIcon = 'https://maps.gstatic.com/mapfiles/markers2/marker_blank.png';
		var selectedIcon = 'https://maps.google.com/intl/en_us/mapfiles/ms/micons/blue.png';

		var markerOpts = {
				title : '' + label,
				draggable : true,
				position : latLng,
				map : map,
				icon : new google.maps.MarkerImage(unselectedIcon),
				label : label,
				raiseOnDrag : false
		};
		markerOpts = _.extend(markerOpts, options);

		var marker = new google.maps.Marker(markerOpts);
		google.maps.event.addListener(marker, 'selected_changed', function() {
			marker.setIcon(marker.get('selected') ? selectedIcon : unselectedIcon);
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
			map : map
		});
		(google.maps.event
				.addListener(
						autoComplete,
						'places_changed',
						function() {
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
								address = [
								           (place.address_components[0]
								           && place.address_components[0].short_name || ''),
								           (place.address_components[1]
								           && place.address_components[1].short_name || ''),
								           (place.address_components[2]
								           && place.address_components[2].short_name || '') ]
								.join(' ');
							}

							infoWindow.setContent('<div><strong>' + place.name
									+ '</strong><br>' + address + '</div>');
							infoWindow.open(map, marker);
						}));
	};

	maputils.fitMapToBounds = function(map, bounds) {
		// Source: https://gist.github.com/1255671
		map.fitBounds(bounds); // does the job asynchronously
		(google.maps.event.addListenerOnce(map, 'bounds_changed', function(
				event) {
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
	};

//	helper needed for transparency slider.
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
		// need to add 0.5 to pixel coords
		var pixelX = pixel.x + 0.5;
		var pixelY = pixel.y + 0.5;
		var cartX = pixelX - width / 2;
		var cartY = -1 * pixelY + height / 2;
		return [ parseFloat(cartX), parseFloat(cartY) ];
	};


	maputils.cartToPixel = function(cart, width, height) {
		var pixelX = parseFloat(cart[0]) + width / 2;
		var pixelY = height / 2 - parseFloat(cart[1]);
		// need to subtract 0.5 from cartesian coords
		pixelX = pixelX - 0.5;
		pixelY = pixelY - 0.5;
		return {
			x : parseInt(pixelX),
			y : parseInt(pixelY)
		};
	};

	function submitSuccess(response, imageQtreeView) {
		try {
			var json = JSON.parse(response);
		} catch (error) {
			console.log('Failed to parse response as JSON: ' + error.message);
			return;
		}
		if (json['status'] == 'success') {
			var overlay = imageQtreeView.model;
			overlay.fetch({
				'success' : function(overlay) {
					imageQtreeView.render();
				}
			});
		}
	}

	function submitError() {
		console.log("server failed to tile the rotated image");
	}

	maputils.submitRequestToServer = function(url, data, imageQtreeView, successCallBack, errorCallBack) {
		// if not defined, use default
		successCallBack = typeof successCallBack !== 'undefined' ? successCallBack : submitSuccess;
		errorCallBack = typeof errorCallBack !== 'undefined' ? errorCallBack : submitError;

		$.ajax({
			url : url,
			crossDomain : false,
			data : data,
			cache : false,
			contentType : false,
			processData : false,
			type : 'POST',
			success: function(response) {
				successCallBack(response, imageQtreeView)
			}, 
			error: function() {
				errorCallBack()
			}
		});
	};


	// set up a transparency slider
	maputils.createOpacityControl = function(map, mapType, overlay) {
		var OPACITY_MAX_PIXELS = 57;
		var sliderImageUrl = '/static/geocamTiePoint/images/opacity-slider3d6.png';
		// Create main div to hold the control.
		var opacityDiv = document.createElement('DIV');
		(opacityDiv.setAttribute('style', 'margin: 5px;' + ' overflow-x: hidden;'
				+ ' overflow-y: hidden;' + ' background: url(' + sliderImageUrl
				+ ') no-repeat;' + ' width: 71px;' + ' height: 21px;'
				+ ' cursor: pointer;'));

		// Create knob
		var opacityKnobDiv = document.createElement('DIV');
		(opacityKnobDiv.setAttribute('style', 'padding: 0;' + ' margin: 0;'
				+ ' overflow-x: hidden;' + ' overflow-y: hidden;'
				+ ' background: url(' + sliderImageUrl + ') no-repeat -71px 0;'
				+ ' width: 14px;' + ' height: 21px;'));
		opacityDiv.appendChild(opacityKnobDiv);

		var opacityCtrlKnob = new ExtDraggableObject(opacityKnobDiv, {
			restrictY : true,
			container : opacityDiv
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

			if (opacityPercent < 0)
				opacityPercent = 0;
			if (opacityPercent > 100)
				opacityPercent = 100;

			// console.log("opacity: " + opacityPercent);
			overlay.overlayOpacity = opacityPercent;
			mapType.setOpacity(opacityPercent / 100.0);
		}

	};
});