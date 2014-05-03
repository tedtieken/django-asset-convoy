from django.db import models
from django.http import HttpResponse
import time
import copy

# orig_close = HttpResponse.close

# def new_close(*args, **kwargs):
#    print "monkey patched close"
#    orig_close(*args, **kwargs)
#    time.sleep(5)
#    print "spent 5 seconds doing stuff without blocking the user"
   
# HttpResponse.close = new_close
  

# Create your models here.


from django.contrib.staticfiles.management.commands import collectstatic
from collections import OrderedDict

orig_collect = collectstatic.Command.collect

def new_collect(self, *args, **kwargs):
    '''
    Monkey Patches collect so we have a clean OrderedDict each time the command is run    
    This allows using the default manifest with our own cache keys
    
    To be removed once https://code.djangoproject.com/ticket/22557 is fixed
    '''
    if hasattr(self.storage, "manifest_name"):
        self.storage.hashed_files = OrderedDict()
    return orig_collect(self, *args, **kwargs)

collectstatic.Command.collect = new_collect