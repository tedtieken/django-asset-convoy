from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.middleware.gzip import re_accepts_gzip

from collections import OrderedDict
from django.core.files.base import ContentFile

import os
import re
import posixpath
import time
import hashlib

CONVOY_DURING_DEBUG = getattr(settings, "CONVOY_DURING_DEBUG", False)
#TODO, find a better name for CONVOY_GZIP_IN_TEMPLATE
CONVOY_GZIP_IN_TEMPLATE = getattr(settings, "CONVOY_GZIP_IN_TEMPLATE", True)
CONVOY_CONSERVATIVE_MSIE_GZIP = getattr(settings, "CONVOY_CONSERVATIVE_MSIE_GZIP", False)
CARPOOL_PATH_FRAGMENT = getattr(settings, "CARPOOL_CACHE_PATH_FRAGMENT", "CARPOOL")

URL_PATTERN = re.compile(r'url\(([^\)]+)\)')
SRC_PATTERN = re.compile(r'src=([\'"])(.+?)\1')
OFFSITE_SCHEMES = ('http://', 'https://', '//')
ABSOLUTE_SCHEMES = ('/')
DATA_SCHEMES = ('data:', '#')


class CssAbsolute(object):
    '''
    Based on CSS Absolute Filter from django-compressor
    Copyright (c) 2009-2014 Django Compressor authors
    Licensed under MIT(https://github.com/django-compressor/django-compressor/blob/develop/LICENSE)
    '''

    def __init__(self, storage=None, *args, **kwargs):
        if not storage:
            storage = staticfiles_storage
        self.storage = storage
        self.utime = int(time.time())

    def get_and_process(self, path, *args, **kwargs):
        with self.storage.open(path) as f:
            self.content = f.read().decode(settings.FILE_CHARSET)
        if hasattr(self.storage, "_local"):
            #Special case for CachedS3 storages
            #S3 storage doesn't implement the `path` method
            self.abs_path = self.storage._local.path(path)
            self.storage_location = self.storage._local.location
        else:
            self.abs_path = self.storage.path(path)
            self.storage_location = self.storage.location
        self.relative_dir = os.path.dirname(self.abs_path)
        return SRC_PATTERN.sub(self.src_converter,
            URL_PATTERN.sub(self.url_converter, self.content))

    def add_offsite_cachebuster(self, url):
        '''
        It would be unreasonable to retrieve and hash the offsite files
        so we use the time when we reference them as the cache buster.
        The file content may still change under us, but this way we can
        force our users' browsers to use a copy that is no older than when 
        we compress the CSS
        '''
        #TODO add a setting to toggle this behavior
        fragment = None
        if "#" in url:
            url, fragment = url.rsplit("#", 1)            
        if "?" in url:
            url = "%s&%s" % (url, self.utime)
        else:
            url = "%s?%s" % (url, self.utime)
        if fragment is not None:
            url = "%s#%s" % (url, fragment)
        return url

    def _converter(self, matchobj, group, template):
        url = matchobj.group(group)
        url = url.strip(' \'"')
        if url.startswith('#'):
            return "url('%s')" % url
        elif url.startswith(OFFSITE_SCHEMES) or url.startswith(ABSOLUTE_SCHEMES):
            return "url('%s')" % self.add_offsite_cachebuster(url)
        elif url.startswith(DATA_SCHEMES):
            return "url('%s')" % url
        abs_resolved_path = posixpath.normpath('/'.join([str(self.relative_dir), url]))
        resolved_path = abs_resolved_path.split(self.storage_location, 1)[-1]
        if hasattr(self.storage, "get_terminal_url"):
            full_url = self.storage.get_terminal_url(resolved_path.lstrip("/"))
        else:
            full_url = self.storage.url(resolved_path.lstrip("/"))
        return template % full_url

    def url_converter(self, matchobj):
        return self._converter(matchobj, 1, "url('%s')")

    def src_converter(self, matchobj):
        return self._converter(matchobj, 2, "src='%s'")


def concatenate_and_hash(paths, comment_key, format, storage=None, fail_loudly=False):
    if not storage:
        storage = staticfiles_storage
    storage._should_hash = False
    css_abs = CssAbsolute(storage=storage)
    
    try:
        content = u"/*!" + comment_key + u"*/"
        for path in paths:
            content += u"\n /*!" + path + u"*/ \n"
            if format == "css":
                processed = css_abs.get_and_process(path)
                if "@import" in processed:
                    raise ValueError("%s: convoy cannot safely concatenate css files that use the @import statement"  % path)
                content += processed
            elif format == "js":
                with storage.open(path) as f:
                    f_content = f.read().decode(settings.FILE_CHARSET)
                    content += f_content
        content = ContentFile(content)

        # Use the storage's file_hash if possible
        if hasattr(storage, 'file_hash'):
            hashed_name = storage.file_hash(comment_key, content)
        elif content is not None:
            hashed_name = hashlib.md5()
            for chunk in content.chunks():
                hashed_name.update(chunk)        
        file_name = CARPOOL_PATH_FRAGMENT + u"/" + hashed_name + u"." + format

        #Save it
        if storage.exists(file_name):
            storage.delete(file_name)
        stored_name = storage.save(file_name, content)
        
        #Store it in the cache
        if hasattr(storage, "hashed_files"):                
            hashed_files = OrderedDict()
            hashed_files[storage.hash_key(comment_key)] = stored_name
            storage.hashed_files.update(hashed_files)
        
        #Post process it
        if hasattr(storage, "post_process"):
            found_files = OrderedDict()
            found_files[stored_name] = (storage, stored_name)
            processor = storage.post_process(found_files, False)
            for orig_path, processed_path, processed in processor:
                if isinstance(processed, Exception):
                    print "Post-processing '%s' failed!" % orig_path
                    raise processed
                if processed:
                    print "Post-processed '%s' as '%s'" % (orig_path, processed_path)
                else:
                    print("Skipped post-processing '%s'" % orig_path)
        return stored_name
        
    except Exception as e:
        if settings.DEBUG or fail_loudly:
            raise
        else:
            # Fall back to including each file individually 
            # if there is any error -- concatenation simply isn't important 
            # enough to bring down the site
            return False
            #TODO: add logging here


def request_accepts_gzip(request):
    # MSIE has issues with gzipped response of various content types
    # but, if we're only gzipping text/css and javascript, we should be ok
    if CONVOY_CONSERVATIVE_MSIE_GZIP:
        if "msie" in request.META.get('HTTP_USER_AGENT', '').lower():
            return False
    ae = request.META.get('HTTP_ACCEPT_ENCODING', '')
    if re_accepts_gzip.search(ae):
        return True
    return False


def convoy_terminus(path, dry_mode=False, gzip=False, storage=None):
    if not storage:
        storage = staticfiles_storage
    if hasattr(storage, "get_terminal_url"):
        return storage.get_terminal_url(path, dry_mode, gzip)
    return storage.url(path) 
    
def convoy_chain(path, dry_mode=False, gzip=False, storage=None):
    if not storage:
        storage = staticfiles_storage
    if hasattr(storage, "get_chain"):        
        return storage.get_chain(path, gzip=False) 
    return [storage.url(path)]

def convoy_from_context(path, context, storage=None):
    if not storage:
        storage = staticfiles_storage    
    dry_mode = False
    gzip = False
    if settings.DEBUG:
        if CONVOY_DURING_DEBUG:
            #NB: using this setting requires 
            # $ python manage.py runserver --nostatic
            # with an explicit static serving urls.py 
            # url(r'^static/(?P<path>.*)$', 'django.views.static.serve',{'document_root': settings.STATIC_ROOT}),
            # or some other kind of self-served static.  Django's default static serving is insufficient
            dry_mode = False
        else:
            dry_mode = True
    if CONVOY_GZIP_IN_TEMPLATE:
        if context.has_key('request'):
            if request_accepts_gzip(context['request']):
                gzip=True
    return convoy_terminus(path, dry_mode, gzip, storage)