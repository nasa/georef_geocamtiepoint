Coordinate Systems
==================

GeoRef uses two main coordinate systems:

 * The image coordinate system measures position in pixels (x, y) where
   (0, 0) is the upper-left corner of the image, x increases to the
   right, and y increases down.
 * The Spherical Mercator coordinate system expresses position on the
   Earth's surface. (x, y) coordinates. Roughly speaking, x increases to
   the east and y increases to the north. The origin matches the origin
   in lat/lon coordinates. The scale of the units approximates
   displacement in meters.  This system is also known as EPSG:3857 or
   EPSG:900913.

Two-way conversions between lat/lon and Spherical Mercator can be found
in the ``latLonToMeters`` and ``metersToLatLon`` functions:

 * `JavaScript coordinate conversions <https://github.com/geocam/geocamTiePoint/blob/master/geocamTiePoint/static/geocamTiePoint/js/coords.js>`_
 * `Python coordinate conversions <https://github.com/geocam/geocamTiePoint/blob/master/geocamTiePoint/quadTree.py>`_

Some other references:

 * `Google Maps Coordinates, Tile Bounds, and Projection <http://www.maptiler.org/google-maps-coordinates-tile-bounds-projection/>`_
 * `PROJ.4 FAQ: Google Mercator <http://trac.osgeo.org/proj/wiki/FAQ#ChangingEllipsoidWhycantIconvertfromWGS84toGoogleEarthVirtualGlobeMercator>`_

Export Format
=============

Exporting an overlay produces a gzip-compressed tar archive containing
following files: 

[imageid]-no_warp.tif

-this is a GeoTIFF version of the photo that is unmodified (unwarped) in an image sense, but contains a bunch of metadata header fields indicating the list of 
	control/tie/correspondence points found for alignment and some alignment fit uncertainty measures.  This version gives an end user all they'd need to create
	their own aligned image from the embedded control points.

[imageid]-warp.tif

-this is a GeoTIFF version of the photo that is actually modified to be warped/aligned to a map, with transparency around the warped photo to fit inside a 
	rectangular image as usual.  It does not contain a header with the list of tie points, but it contains fields with alignment fit measures.

[imageid]-no_warp_metadata.txt

-this is a text file containing a formatted dump of the header fields present in the -no_warp.tif version so that someone can get the important data without 
	retrieving the image.

[imageid]-warp_metadata.txt

-same as no_warp_metadata.txt but instead corresponding to the -warp.tif version.

[imageid]-uncertainty-no_warp.tif

-This is a special synthetic image (single channel floating point) where the number at each pixel represents the uncertainty (standard deviation) in meters we 
	estimate for our fit at that pixel.  This provides data to do automated analysis of the relative accuracy of our alignment at each pixel -- 
	it will be more accurate near tie points, and worse further away.

[imageid]-uncertainty-no_warp.tif

-analogous to the -uncertainty-no_warp.tif file, this is a warped/aligned version of the uncertainty image.  It contains two floating point channels, the first 
	is the uncertainty as in the unwarped version, and the second is a "mask" that is 0 where there is no uncertainty data (the warped image doesn't exist there) 
	or 255 if there is.


Meta-Data Format: meta.json
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``transform`` field represents a best-fit transform that maps image
coordinates to Spherical Mercator coordinates. Depending on the number
of tie points specified, the transform can be expressed in two forms:

 * ``"type": "projective"``. This is a 2D projective transform. Used when
   fewer than 7 tie point pairs are specified. The ``matrix`` field is a
   3x3 transformation matrix ``M`` specified in row-major order. To apply
   the transform:

   * Start with image coordinates ``(x, y)``.

   * Convert to a length-3 column vector ``u`` in homogeneous coordinates: ``u = (x, y, 1)``

   * Matrix multiply ``(x0, y0, w) = M * u``.

   * Normalize homogeneous coordinates: ``x' = x0 / w``, ``y' = y0 / w``.

   * The resulting Spherical Mercator coordinates are ``(x', y')``.

 * ``"type": "quadratic2"``. This transform is similar to the projective
   transform but adds higher-order terms to achieve a better fit when
   the overlay image uses a different map projection from the base
   layer. Used when 7 or more tie point pairs are specified. Please
   refer to the code for full details. Some points of interest:

   * Note that despite the name, this transform is *not* exactly
     quadratic. In order to ensure the transform has a simple analytical
     inverse, corrections are applied serially, which incidentally
     introduces some 4th-order and 6th-order terms.

   * The ``matrix`` field has essentially the same interpretation as for
     the 'projective' transform.

   * In order to help with numerical stability during optimization, the
     last step of the transform is to scale the result by 1e+7.  Because
     of this, the matrix entries will appear much smaller than those in
     the projective transform.

   * The coefficients for higher-order terms are encoded in the
     ``quadraticTerms`` field. If all of those terms are 0, the
     ``quadratic2`` transform reduces to a ``projective`` transform.

See the alignment transform reference implementations in the
``ProjectiveTransform`` and ``QuadraticTransform2`` classes:

 * `JavaScript alignment transforms <https://github.com/geocam/geocamTiePoint/blob/master/geocamTiePoint/static/geocamTiePoint/js/transform.js>`_
 * `Python alignment transforms <https://github.com/geocam/geocamTiePoint/blob/master/geocamTiePoint/transform.py>`_

.. o __BEGIN_LICENSE__
.. o Copyright (C) 2008-2010 United States Government as represented by
.. o the Administrator of the National Aeronautics and Space Administration.
.. o All Rights Reserved.
.. o __END_LICENSE__
