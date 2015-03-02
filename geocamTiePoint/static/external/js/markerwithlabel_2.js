 /**
 Courtesy of 
 http://stackoverflow.com/questions/11096094/google-maps-v3-marker-with-label
 **/
    var markerSize = { x: 22, y: 40 };

    google.maps.Marker.prototype.setLabel = function(label){
    	if (this.label) {
    		// for the center point marker, only update the text of label.
    		this.label.text = label;
    	} else {
	        this.label = new MarkerLabel({
	          map: this.map,
	          marker: this,
	          text: label
	        });
        }
        this.label.bindTo('position', this, 'position');
    };
   
    var MarkerLabel = function(options) {
        this.setValues(options);
        this.span = document.createElement('span');
        this.span.className = 'map-marker-label';
        // set the id of the label to map type and its index
        this.span.id = options.map.mapTypeId + '-' + options.text;
    };

    MarkerLabel.prototype = $.extend(new google.maps.OverlayView(), {
        onAdd: function() {
            this.getPanes().overlayImage.appendChild(this.span);
            var self = this;
            this.listeners = [
            google.maps.event.addListener(this, 'position_changed', function() { self.draw();    })];
        },
        draw: function() {
            var text = String(this.get('text'));
            var position = this.getProjection().fromLatLngToDivPixel(this.get('position'));
            this.span.innerHTML = text;
            this.span.style.left = (position.x - (markerSize.x / 2)) - (text.length * 3) + 10 + 'px';
            this.span.style.top = (position.y - markerSize.y + 40) + 'px';
        }
    });