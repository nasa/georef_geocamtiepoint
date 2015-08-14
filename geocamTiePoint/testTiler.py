import numpy
import PIL
from django.core.cache import cache

from quadTree import SimpleQuadTreeGenerator

fakeFile = '/home/vagrant/geocamspace/geoRef/data/test_large.jpg'
im = PIL.Image.open(fakeFile)
dummyQuadTreeId = 1
simple = SimpleQuadTreeGenerator(dummyQuadTreeId,im)
data = simple.getTileData(3,0,0)
print data
try: 
    cache.set("testKey", data)
except: 
    print "cacheing failed"