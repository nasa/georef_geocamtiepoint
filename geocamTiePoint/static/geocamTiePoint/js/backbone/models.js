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
		  	  mapCoords:{} // holds dictionary of x: y: where the values are meters in the map
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
		  parse: function(data, options){
			  if (Array.isArray(data) && !_.isEmpty(data)){
				  if (data.length == 4){
					  if (data[0] !== null){
						  this.set('mapCoords',{x:data[0], 
							  	   				y:data[1]});
					  }
					  if (data[2] !== null){
						  this.set('imageCoords', [data[2], data[3]]);
					  }
					  this.unset('0',['silent']);
					  this.unset('1',['silent']);
					  this.unset('2',['silent']);
					  this.unset('3',['silent']);
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
                    	relatedModel: app.models.TiePoint,
                    	reverseRelation: {
                    	      key: 'overlay'
                    	    }
                    }
        ],
        
        defaults: {
        	points: [],
        },
        initialize: function(arguments) {
        	this.hasChangedSinceLastSync = false;
        	this.on('postActionPerformed', this.warp, this);
        	vent.on('undo', this.handleChange, this);
        	vent.on('redo', this.handleChange, this);
            this.on('change:points', this.modelChanged, this);
            this.on('add:points', this.modelChanged, this);
            this.on('remove:points', this.modelChanged, this);
        	this.on('sync', this.handleWarpSuccess, this);
        	this.on('error', function(model, response, options) {this.handleWarpError(response)}, this);
        },
        
        modelChanged: function() {
            this.hasChangedSinceLastSync = true;
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

        set: function(attributes, options){
        	if (!_.isUndefined(attributes.points) && !_.isUndefined(this.get('points'))) {
        		_.each(_.clone(this.get('points').models), function(point) {
        			  point.destroy();
        			});
        	}
        	return Backbone.RelationalModel.prototype.set.apply(this, arguments);
        },
        
        parse: function(resp, xhr) {
            // Ensure server-side state never overwrites local points value
            if (!_.isEmpty(this.get('points')) && 'points' in resp) {
                delete resp['points'];
            }
            return resp;
        },
        
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
        
        getFirstIncompleteTiepoint: function(coordKey) {
        	// if there is a tiepoint that has coordinates from the other side but not whichSide, return it.
        	var found = null;
        	var points = this.get('points');
        	if (points.isEmpty()){
        		return found;
        	}
        	points.each(function(point){
				    				if (found === null && _.isEmpty(point.get(coordKey))){
				    					found = point;
				    					return;
				    				}
		        				});
		    return found;
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
    			if (transform) {
					// calculate the new center lat lon
					var transformedCenter = forwardTransformPixel(transform, {x: w/2, y: h/2});
					var lat = transformedCenter.lat();
					var lon = transformedCenter.lng();
					lat = lat.toFixed(2);
					lon = lon.toFixed(2);
					// update the overlay model's center pt in db
					model.set('centerLat', lat);
					model.set('centerLon', lon);
					model.save(model.attributes);
    			} else {
    				console.log("Transformation matrix not available. Center point cannot be updated");
    			}
    		}
    		
    		
        },

        computeTransform: function() {
            // only operate on points that have all four values.
        	var points = [];
        	this.get('points').each(function(point){
        		if (point.isValid()){
        			points.push(point.toJSON());
        		} 
        	});
        	
            // a minimum of two tiepoints are required to compute the transform
            if (points.length < 2) {
            	this.trigger('points_lt_2');
            	this.unset('transform');
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

        handleWarpError: function(response){
        	if (response.readyState < 4) {
                this.trigger('warp_server_unreachable');
            } else {
                this.trigger('warp_server_error');
            }
        },
        handleWarpSuccess: function() {
        	this.hasChangedSinceLastSync = false;
        	this.trigger('warp_success')
        },
        handleChange: function() {
        	if (this.hasChangedSinceLastSync){
        		this.warp();
        	}
        },
        warp: function(options) {
            // Warp the overlay on the server by computing the transform and saving.
            this.trigger('before_warp');
            this.save();  // hits overlayIdJson on serverside
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

    // TODO delete when we refactor to take list out of backbone.html
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
