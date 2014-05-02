from django.middleware.gzip import GZipMiddleware
from django.conf import settings

class GzipHttpOnlyMiddleware(object):
    '''
    Wraps django's default GZIP middleware to only GZIP HTTP Requests, not HTTPS
    thus sidestepping the BREACH vulnerability on HTTPS pages and
    getting gzip performance improvements on HTTP pages
    
    Overview of BREACH and django:
    http://stacks.11craft.com/what-is-breach-how-can-we-protect-django-projects-against-it.html

    Alternate BREACH mitigation:
    https://github.com/lpomfrey/django-debreach
    https://github.com/jsocol/django-ratelimit
    '''
    def __init__(self, *args, **kwargs):
        self.gzip_middleware = GZipMiddleware(*args, **kwargs) 
    
    def process_response(self, request, response):
        if request.scheme is 'https':
          return response
          
        if request.is_secure():
          return response
        
        if request.META.get("HTTP_X_FORWARDED_PROTO", "") == 'https':
          return response
          
        return self.gzip_middleware.process_response(request, response)
    