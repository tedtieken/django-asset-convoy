from django.conf import settings

# from templatetags/convoytags.py
CONVOY_DURING_DEBUG = getattr(settings, "CONVOY_DURING_DEBUG", False)
CARPOOL_COMBINE_DURING_DEBUG = getattr(settings, "CARPOOL_COMBINE_DURING_DEBUG", False)
CARPOOL_PATH_FRAGMENT = getattr(settings, "CARPOOL_CACHE_PATH_FRAGMENT", "CARPOOL")
CARPOOL_COMBINE_ORIGINALS = getattr(settings, "CARPOOL_COMBINE_ORIGINALS", False)
CARPOOL_COMBILE_DURING_REQUEST = getattr(settings, "CARPOOL_COMBINE_DURING_REQUEST", True)
if settings.DEBUG and CARPOOL_COMBINE_DURING_DEBUG and not CONVOY_DURING_DEBUG:
    raise ImproperlyConfigured("When DEBUG=True and CARPOOL_COMBINE_DURING_DEBUG=True, you must also set CONVOY_DURING_DEBUG=True")

# from middleware.py
#TODO, find a better name for CONVOY_GZIP_IN_TEMPLATE
CONVOY_GZIP_IN_TEMPLATE = getattr(settings, "CONVOY_GZIP_IN_TEMPLATE", True)
CONVOY_CONSERVATIVE_MSIE_GZIP = getattr(settings, "CONVOY_CONSERVATIVE_MSIE_GZIP", False)
CARPOOL_PATH_FRAGMENT = getattr(settings, "CARPOOL_CACHE_PATH_FRAGMENT", "CARPOOL")

# from stores.py
CONVOY_USE_EXISTING_MIN_FILES = getattr(settings, "CONVOY_USE_EXISTING_MIN_FILES", False)
CONVOY_AWS_QUERYSTRING_AUTH = getattr(settings, 'CONVOY_AWS_QUERYSTRING_AUTH', True)
CONVOY_AWS_HEADERS = getattr(settings, 'CONVOY_AWS_HEADERS', {})
CONVOY_LOCAL_CACHE_ROOT = getattr(settings, 'CONVOY_LOCAL_CACHE_ROOT', getattr(settings, "STATIC_ROOT", ""))
