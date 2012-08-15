# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

# in the future we might (more efficiently) pre-generate entire
# quadTrees and write all the tiles to a persistent store. at the moment
# we can do this in the native django environment, but for debugging
# purposes only. the server will not actually use the persistent store
# when answering queries.
GEOCAM_TIE_POINT_PRE_GENERATE_TILES = False

# default initial viewport for alignment interface. if we can detect the
# user's position we'll use that instead. these bounds cover the
# continental US.
GEOCAM_TIE_POINT_DEFAULT_MAP_VIEWPORT = {
    "west": -130,
    "south": 22,
    "east": -59,
    "north": 52,
}
