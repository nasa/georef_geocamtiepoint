var app = app || {};
app.models = app.models || {};

// All these globals should be loaded from elsewhere.
assert(! _.isUndefined(getNormalizedCoord),
       'Missing global: getNormalizedCoord');
assert(! _.isUndefined(fillTemplate),
       'Missing global: fillTemplate');
assert(! _.isUndefined(TILE_SIZE),
       'Missing global: TILE_SIZE');
assert(! _.isUndefined(MIN_ZOOM_OFFSET),
       'Missing global: MIN_ZOOM_OFFSET');

$(function($) {
	// Represents a single tie point
	app.models.TiePoint = Backbone.RelationalModel.extend({
		  defaults: {
			  imageCoords:[], // holds (x,y) coordinate pairs for image.
		  	  mapCoords:{} // holds 
		  },
		  constructor: function(attributes, options){
			  Backbone.RelationalModel.apply( this, arguments );
			  this.parse(attributes, options);
		  },
		  isValid: function() {
				var result =  (!_.isEmpty(this.get('mapCoords')) && 
							   !_.isEmpty(this.get('imageCoords')) &&
							   $.isNumeric(this.get('mapCoords').x) &&  
							   $.isNumeric(this.get('imageCoords')[0]));
				return result;
		  },
		  toJSON : function() {
			  var result = [];
			  if (!_.isEmpty(this.get('mapCoords'))){
				  result.push(this.get('mapCoords').x);
				  result.push(this.get('mapCoords').y);
			  } else {
				  result = [null, null];
			  }
			  if (!_.isEmpty(this.get('imageCoords'))){
				  result.push.apply(result, this.get('imageCoords'));
			  } else {
				  result.push.apply(result, [null, null]);
			  }
			  return result;
		  },
		  isMapCoord: function(value) {
			  //TODO does this make any sense?
			  value = Math.abs(value);
			  return value >= 999999;
		  },
		  parse: function(data, options){
			  if (Array.isArray(data) && !_.isEmpty(data)){
				  if (data.length == 4){
					  this.set('mapCoords',{x:data[0], 
							  	   			y:data[1]});
					  this.set('imageCoords', [data[2], data[3]]);;
				  } else if (data.length == 2) {
					  //TODO how do we know if it is map or image coords stored?
					  if (this.isMapCoord(data[0])) {
						  this.set('mapCoords',{x:data[0], 
				  	   							y:data[1]});
					  } else {
						  this.set('imageCoords', [data[0], data[1]]);
					  }
				  }
			  }
		  }
		});

	// represents a single map overlay
    app.models.Overlay = Backbone.RelationalModel.extend({
        idAttribute: 'key', // Backend uses "key" as the primary key

        relations: [
                    {
                    	type: Backbone.HasMany,
                    	key: 'points',
                    	relatedModel: app.models.TiePoint
                    }
        ],
        defaults: {
        	points: [],
        },
        
        initialize: function(arguments) {
            // Bind all the model's function properties to the instance,
            // so they can be passed around as event handlers and such.
            //_.bindAll(this);  //TODO does not seem to be necessary, remove
            this.on('before_warp', this.beforeWarp);
//            this.on('change', this.save);
//            this.on('change:points', this.save, this);
//            this.on('add:points', this.save, this);
//            this.on('remove:points', this.save, this);
        },

        url: function() {
            var pk = (_.isUndefined(this.get('id')) ?
                      this.get('key') : this.get('id'));
            return this.get('url') || '/overlay/' + pk + '.json';
        },

        getImageTileUrl: function(coord, zoom) {
            assert(this.get('unalignedTilesUrl'),
                   'Overlay is missing an unalignedTilesUrl property.' +
                   ' Likely it does not have an unalignedQuadTree set' +
                   ' on the backend.');
            var normalizedCoord = getNormalizedCoord(coord, zoom);
            if (!normalizedCoord) { return null; }
            var url = fillTemplate(this.get('unalignedTilesUrl'), {
                zoom: zoom,
                x: normalizedCoord.x,
                y: normalizedCoord.y
            });
            return url;
        },

//        parse: function(resp, xhr) {
//            // Ensure server-side state never overwrites local points value
//        	// TODO why would this happen, if we control the sync?
//            if (this.has('points') && 'points' in resp) {
//                delete resp.points;
//            }
//            return resp;
//        },

        getAlignedImageTileUrl: function(coord, zoom) {
            var normalizedCoord = getNormalizedCoord(coord, zoom);
            if (!normalizedCoord) {
            	return null;
            }
            return fillTemplate(this.get('alignedTilesUrl'),
                {zoom: zoom,
                 x: normalizedCoord.x,
                 y: normalizedCoord.y});
        },

        maxDimension: function() {
            var size = this.get('imageSize');
            if (_.isUndefined(size)) {
                throw "Overlay image's size is not defined or not yet loaded.";
            }
            return Math.max(size[0], size[1]);
        },

        maxZoom: function() {
            var mz = (Math.ceil(Math.log(this.maxDimension() / TILE_SIZE) /
                                Math.log(2)) +
                      MIN_ZOOM_OFFSET);
            return mz;
        },

        imageBounds: function() {
            var imageSize = this.get('imageSize');
            var w = imageSize[0];
            var h = imageSize[1];
            var sw = pixelsToLatLon({x: 0, y: 0}, this.maxZoom());
            var ne = pixelsToLatLon({x: w, y: h}, this.maxZoom());
            var bounds = new google.maps.LatLngBounds(sw, ne);
            return bounds;
        },

        mapBounds: function() {
            var bounds = this.get('bounds');
            return new google.maps.LatLngBounds(
                new google.maps.LatLng(bounds.south, bounds.west),
                new google.maps.LatLng(bounds.north, bounds.east)
            );
        },
        
        getFirstEmptyTiepoint: function(coordKey) {
        	// if there is a tiepoint that has coordinates from the other side but not whichSide, return it.
        	var found = null;
        	var points = this.get('points');
        	if (points.isEmpty()){
        		return found;
        	}
        	points.each(function(point){
				    				if (found == null && _.isEmpty(point.get(coordKey))){
				    					found = point;
				    					return;
				    				}
		        				});
		    return found;
        },

        /**
         * Update one "side" (map or image) of an entry in the model's
         * tiepoint array.  Will add a new tiepoint if one doesn't
         * already exist at that index.
        */
        updateTiepoint: function(whichSide, pointIndex, coords, drawMarkerFlag) {
        	// drawMarkerFlag is set to true unless function is called with 'false' as an arg.
        	drawMarkerFlag = typeof drawMarkerFlag !== 'undefined' ? drawMarkerFlag : true;
        	//  this flag is set to true if this fcn is called by handle click
        	var clickedOnImageViewFlag = (whichSide == 'image') && (drawMarkerFlag == false);
            if (clickedOnImageViewFlag) { 
            	var overlay = this;
            	// undo the rotation on tie pts before saving the coords.
            	coords = maputils.undoTiePtRotation(coords, overlay);
            }
            var points = this.get('points');
            var initial_length = points.length;
            var tiepoint = points[pointIndex] || [null, null, null, null];
            var coordIdx = {
                'map': [0, 1],
                'image': [2, 3]
            }[whichSide];
            assert(coordIdx, 'Unexpected whichSide argument: ' + whichSide);
            tiepoint[coordIdx[0]] = coords.x;
            tiepoint[coordIdx[1]] = coords.y;
            points[pointIndex] = tiepoint;
            this.set('points', points);
            if (points.length > initial_length) this.trigger('add_point');
            // if it is a map side or if the draw marker flag is on, trigger overlay's drawMarker call.
            if (!clickedOnImageViewFlag) { 
            	// we don't want to call this if it is new point on the 
            	// image side (from user click) because it will rotate the 
            	// already rotated point again.
            	this.trigger('change:points');
            }
        },
        
        // applies current transform to the center pixel of image to get the
        // new world coordinates of the center point.
        updateCenterPoint: function() {
        	var model = this;
    		if (model.get('transform')) {
    			var transform = (geocamTiePoint.transform.deserializeTransform
    					(model.get('transform')));
    			var imageSize = model.get('imageSize');
    			var w = imageSize[0];
    			var h = imageSize[1];
    			if (transform && centerPointMarker) {
    				var updateCenter = false;
    				if (transform.toDict().type == 'CameraModelTransform') {
    					// if it is a cameraModelTransform, center will be updated in the 
    					// forward function.
    					updateCenter = true; 
    				}
					// calculate the new center
					var transformedCenter = forwardTransformPixel(transform, {x: w/2, y: h/2}, updateCenter);
					if (updateCenter == false) {
						var lat = transformedCenter.lat();
						var lon = transformedCenter.lng();
						lat = lat.toFixed(2);
						lon = lon.toFixed(2);
						// update the overlay model's center pt in db
						model.set('centerLat', lat);
						model.set('centerLon', lon);
						model.save();
					}
    			} else {
    				console.log("Transformation matrix not available. Center point cannot be updated");
    			}
    		}
        },

        deleteTiepoint: function(index) {
            actionPerformed();
            points = this.get('points');
            points.splice(index, 1);
            this.set('points', points);
            this.trigger('change:points');
        },

        computeTransform: function() {
            // only operate on points that have all four values.
        	var points = [];
        	this.get('points').each(function(point){
        		if (point.isValid()){
        			points.push(point.toJSON());
        		} 
        	});
//            var points = _.filter(this.get('points').models, function(point) {
//            	return point.isValid();
////                return _.all(coords, _.identity);
//            });
            // a minimum of two tiepoints are required to compute the transform
            if (points.length < 2) {
            	return false;
            }
            
            // issMRF will be undefined for all other transforms besides CameraModelFrame
            // set the 'transform' field of the overlay model with the newly computed tform.
            var transform = geocamTiePoint.transform.getTransform(points, this.get('issMRF'), this);
            if (typeof transform != 'undefined') {
            	this.set('transform',
                        (points ?
                         transform.toDict() :
                         {type: '', matrix: []})
                );	
            }
        },

        save: function(attributes, options) {
            // Always compute transform on before save.
            this.computeTransform();
            return Backbone.RelationalModel.prototype.save.apply(this, attributes, options);
        },

        beforeWarp: function() {
            // We have to clear this because this.fetch() won't.
            this.unset('htmlExportUrl');
            this.unset('kmlExportUrl');
            this.unset('geotiffExportUrl');
        },

        warp: function(options) {
            // Save the overlay, which triggers a server-side warp.
            options = options || {};
            var model = this;
            model.trigger('before_warp');
            saveOptions = {
                error: function(model, response) {
                    if (response.readyState < 4) {
                        model.trigger('warp_server_unreachable');
                    } else {
                        model.trigger('warp_server_error');
                    }
                    if (options.error) options.error();
                },
                success: function(model, response) {
                    if (options.success) options.success();
                    model.trigger('warp_success');
                }
            };
            this.save({}, saveOptions);  // hits overlayIdJson on serverside
        },
        
        getExportPendingObj: function(type) {
            switch(type) {
            case 'html':
                return this.htmlExportPending;
            case 'kml':
            	return this.kmlExportPending;
            case 'geotiff':
            	return this.geotiffExportPending;
            default:
            	return null;
            }	
        },
        
        startExport: function(options) {
            var exportType = options.exportType;
            var exportUrl = exportType + 'ExportUrl';
            var event = exportType + '_export_ready';
            
            assert(! this.get(exportUrl), 'Model has an exportUrl already.');
            var request_url = this.get('url').replace('.json',
                                                      '/generateExport/'+exportType);
            var exportPending = this.getExportPendingObj(exportType);
            exportPending = true;
            var model = this;
            model.on(event, function() {
            		exportPending = false;},
            	this);
            $.post(request_url, '', function() {
                model.fetch({ success: function() {
                	if (model.get(exportUrl)) {
                		model.trigger(event);
                	}
                } });
            }, 'json')
            .error(function(xhr, status, error) {
                 this.exportPending = false;
                 if (options.error) options.error();
            });
        }
    });

    // TODO delete as we are just working on a single overlay
    app.models.OverlayCollection = Backbone.Collection.extend({
        model: app.models.Overlay,
        url: '/overlays.json',
        comparator: function(overlay) {
            // Sort by modified time, descending
            return -1 * Date.parse(overlay.get('lastModifiedTime'));
        }
    });

    app.overlays = new app.models.OverlayCollection();
});
