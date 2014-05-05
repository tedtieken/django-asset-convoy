from django.conf import settings
from django.core.management.base import CommandError
from django.contrib.staticfiles.management.commands import collectstatic, runserver
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


runserver_error_message = """When CONVOY_DURING_DEBUG is set to True, you must
* run runserver with the --nostatic option: $ python manage.py runserver --nostatic
* run collectstatic each time your static files change
* configure an explicit static serving url in your urls.py: e.g. url(r'^static/(?P<path>.*)$', 'django.views.static.serve',{'document_root': settings.STATIC_ROOT}'
"""
orig_run = runserver.Command.run
def new_run(self, *args, **kwargs):
    '''
    Monkey patches collectstatic's runserver to warn when a bad set of settigns are given
    '''
    
    if settings.DEBUG:
      if getattr(settings, 'CONVOY_DURING_DEBUG', False):
        if kwargs.get('use_static_handler', True):
          raise CommandError(runserver_error_message)
    return orig_run(self, *args, **kwargs) 
runserver.Command.run = new_run   


# A monkey patch that might be able to let us do non-blocking post-request work
#from django.http import HttpResponse
#import time
# orig_close = HttpResponse.close
# def new_close(*args, **kwargs):
#    print "monkey patched close"
#    orig_close(*args, **kwargs)
#    time.sleep(5)
#    print "spent 5 seconds doing stuff without blocking the user"
# HttpResponse.close = new_close
