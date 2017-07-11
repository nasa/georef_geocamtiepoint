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

function fitNamedBounds(b, map) {
    var bounds = (new google.maps.LatLngBounds
                  (new google.maps.LatLng(b.south, b.west),
                   new google.maps.LatLng(b.north, b.east)));
    map.fitBounds(bounds);
}

function fillTemplate(tmpl, fields) {
    var result = decodeURI(tmpl);
    $.each(fields, function(field, val) {
        var pattern = '[' + field.toUpperCase() + ']';
        result = result.replace(pattern, val);
    });
    return result;
}

// Convenient assertions.  Nice for debugging.
function AssertException(message) { this.message = message; }
AssertException.prototype.toString = function() {
  return 'AssertException: ' + this.message;
};
function assert(exp, message) {
  if (!exp) {
    throw new AssertException(message);
  }
}

if (window.Handlebars != undefined) {
    // helper for debugging handlebars templates.
    Handlebars.registerHelper('debug', function(optionalValue) {
        console.log('Current Context');
        console.log('====================');
        console.log(this);
        if (optionalValue) {
            console.log('Value');
            console.log('====================');
            console.log(optionalValue);
        }
    });
}

function flicker(f1, f2, msecs, n) {
    for (var i = 0; i < n; i++) {
        setTimeout(f1, 2 * i * msecs);
        setTimeout(f2, (2 * i + 1) * msecs);
    }
}
