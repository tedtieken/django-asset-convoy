from django import template
from django.template.base import Node
from django.utils.encoding import iri_to_uri
from django.utils.six.moves.urllib.parse import urljoin
from django.contrib.staticfiles.templatetags.staticfiles import StaticFilesNode, do_static
from django.contrib.staticfiles.storage import staticfiles_storage
from django.middleware.gzip import re_accepts_gzip
from collections import OrderedDict
from django.core.exceptions import ImproperlyConfigured

from django.conf import settings

register = template.Library()

CONVOY_DURING_DEBUG = getattr(settings, "CONVOY_DURING_DEBUG", False)
CONVOY_CONSERVATIVE_MSIE_GZIP = getattr(settings, "CONVOY_CONSERVATIVE_MSIE_GZIP", False)
#TODO, find a better name for CONVOY_GZIP_IN_TEMPLATE
CONVOY_GZIP_IN_TEMPLATE = getattr(settings, "CONVOY_GZIP_IN_TEMPLATE", True)
CARPOOL_DURING_DEBUG = getattr(settings, "CARPOOL_DURING_DEBUG", False)

if settings.DEBUG and CARPOOL_DURING_DEBUG and not CONVOY_DURING_DEBUG:
    raise ImproperlyConfigured("When DEBUG=True and CARPOOL_DURING_DEBUG=True, you must also set CONVOY_DURING_DEBUG=True")
        
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
    
        
class ConvoyStaticNode(StaticFilesNode):
    def url(self, context):
        path = self.path.resolve(context)
        return convoy_from_context(path, context)


@register.tag('convoy')
def do_convoy(parser, token):
    """
    Joins the given path with the STATIC_URL setting.
    Walks the convoy manifest chain to get appropriate terminus file

    Usage::

        {% convoy path [as varname] %}

    Examples::

        {% convoy "myapp/css/base.css" %}
        {% convoy variable_with_path %}
        {% convoy "myapp/css/base.css" as admin_base_css %}
        {% convoy variable_with_path as varname %}

    """
    return ConvoyStaticNode.handle_token(parser, token)


CSS_TEMPLATE = u'<link rel="stylesheet" href="%s" >\n'
JS_TEMPLATE  = u'<script type="text/javascript" src="%s" ></script>\n'
START_COMMENT_TEMPLATE = u"\n<!-- %s -->\n"
END_COMMENT_TEMPLATE = START_COMMENT_TEMPLATE
CARPOOL_PATH_FRAGMENT = getattr(settings, "CARPOOL_CACHE_PATH_FRAGMENT", "CARPOOL")
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files.base import ContentFile
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import get_storage_class

import os
import re
import posixpath
import time
import hashlib
import copy

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
        if hasattr(storage, "_local"):
            #For cached s3 storage
            self.storage = storage._local
        else:
            self.storage = storage
        self.utime = int(time.time())

    def get_and_process(self, path, *args, **kwargs):
        with self.storage.open(path) as f:
            self.content = f.read().decode(settings.FILE_CHARSET)
        self.abs_path = self.storage.path(path)
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
        resolved_path = abs_resolved_path.split(self.storage.location, 1)[-1]
        if hasattr(self.storage, "get_terminal_url"):
            full_url = self.storage.get_terminal_url(resolved_path.lstrip("/"))
        else:
            full_url = self.storage.url(resolved_path.lstrip("/"))
        return template % full_url

    def url_converter(self, matchobj):
        return self._converter(matchobj, 1, "url('%s')")

    def src_converter(self, matchobj):
        return self._converter(matchobj, 2, "src='%s'")



def concatenate_and_hash(paths, comment_key, format, storage=None):
    print "starting concat and hash"
    
    if not storage:
        storage = staticfiles_storage
    storage._should_hash = False
    css_abs = CssAbsolute(storage=storage)
    
    # If we get here there either was a cache miss or storage is non-caching
    # Either way, we have to open and process the files in the request or return
    # Check if we actually want to do that
    if not getattr(settings, "CARPOOL_DURING_REQUEST", True):
        #TODO: create mechanisms for enqueuing this to be compressed after the request
        # celery, monkey patched close
        return False
    
    try:
        #Ok, get and concatenate the files
        content = u"/*!" + comment_key + "*/"
        for path in paths:
            content += u"\n /*!" + path + "*/ \n"
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

        if hasattr(storage, 'file_hash'):
            #Respect the storage's file_hash if they have one
            hashed_name = storage.file_hash(comment_key, content)
        elif content is not None:
            #Hash the content ourselves if they don't
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
                    # Add a blank line before the traceback, otherwise it's
                    # too easy to miss the relevant part of the error message.
                if processed:
                    print "Post-processed '%s' as '%s'" % (orig_path, processed_path)
                else:
                    print("Skipped post-processing '%s'" % orig_path)
        print stored_name
        return stored_name
        
    except Exception as e:
        if settings.DEBUG:
            raise
        else:
            # In production, fall back to including each file individually 
            # if there is any error -- concatenation simply isn't important 
            # enough to bring down the production site
            return False


class CarpoolNode(template.Node):
    def __init__(self, nodelist, format, storage=None):
        if not storage:
            self.storage = staticfiles_storage
        self.nodelist = nodelist
        self.format = format
        self.compressed_file_name = None
        
    def resolve_paths_to_combine(self, paths):
        convoyable_paths = []
        unconvoyable_paths = []
        
        for p in paths:
            #we can't concatenate gziped files
            chain = convoy_chain(p, gzip=False)
            if chain:
                if getattr(settings, "CARPOOL_COMBINE_ORIGINALS", False):
                    convoyable_paths.append(chain[0])
                else:
                    convoyable_paths.append(chain[-1])
            else:
                unconvoyable_paths.append(path)
        
        return convoyable_paths, unconvoyable_paths     
        
    def comment_key_in_cache(self, comment_key):
        storage = self.storage
        #Check if we already have an entry for this key
        if hasattr(storage, 'get_next_link'):
            # First within the convoy project's storages
            return self.storage.get_next_link(comment_key) 
        elif hasattr(storage, 'hashed_files'):
            # Then within the default django static files
            return self.storage.hashed_files.get(comment_key)
        return False

        
    def render(self, context):
        node_text = self.nodelist.render(context)
        # if the line has content get just the path without whitespaces or quotes
        paths = [x.strip(' \'"\r') for x in node_text.split('\n') if bool(x.strip())]
        convoyable_paths, unconvoyable_paths = self.resolve_paths_to_combine(paths)
        comment_key = u"+++".join(convoyable_paths)
        print comment_key

        out = START_COMMENT_TEMPLATE % comment_key
        
        if settings.DEBUG and not CARPOOL_DURING_DEBUG:
            unconvoyable_paths = paths
        else:             
            #TODO: clean this up, we're setting compressed_file_name by side effect
            already_hashed = self.comment_key_in_cache(comment_key) 
            self.compressed_file_name = already_hashed
            if not already_hashed:
                #Combine the if we can
                self.compressed_file_name = concatenate_and_hash(convoyable_paths, comment_key, self.format)

            if self.compressed_file_name:
                if self.format == "css":
                    out += CSS_TEMPLATE % convoy_from_context(self.compressed_file_name, context) 
                elif self.format == "js":
                    out += JS_TEMPLATE % convoy_from_context(self.compressed_file_name, context)
            else:
                #We couldn't compress for some reason, render all files separately
                unconvoyable_paths = paths
            
        for path in unconvoyable_paths: 
            if self.format == "css":
                out += CSS_TEMPLATE % convoy_from_context(path, context)
            elif self.format == "js":
                out += JS_TEMPLATE % convoy_from_context(path, context)
        out += END_COMMENT_TEMPLATE % comment_key   
        return out

@register.tag
def carpool(parser, token):
    """
    Turns a newline separated list of paths into concatenated and hashed files.

    Usage::

        {% carpool [js,css] %}
            'file/path/to/concatenate.[js,css]'
            'file/path/to/join.[js,css]'
        {% endcarpool %}

    Examples::

        {% carpool css %}
            "myapp/css/base.css"
            "myapp/css/second.css"
            "myapp/css/third.css"
        {% endcarpool %}
        
        If there were a concatenated, minified version, would render something like:
            <!-- myapp/css/base.css+++myapp/css/second.css+++myapp/css/third.css -->
            <link rel="stylesheet" href="/static/CACHE/css/fb12a26e32dc.cmin.css' ">
            <!-- myapp/css/base.css+++myapp/css/second.css+++myapp/css/third.css -->
            
        If not, would render:
            <!-- myapp/css/base.css+++myapp/css/second.css+++myapp/css/third.css -->
            <link rel="stylesheet" href="/static/myapp/css/base.css' >
            <link rel="stylesheet" href="/static/myapp/css/second.css' >
            <link rel="stylesheet" href="/static/myapp/css/third.css' >
            <!-- myapp/css/base.css+++myapp/css/second.css+++myapp/css/third.css -->
        
        {% carpool js %}
            "myapp/css/base.js"
            "myapp/css/second.js"
            "myapp/css/third.js"
        {% endcarpool %}

        Would render something like:
            <!-- myapp/css/base.js+++myapp/css/second.js+++myapp/css/third.js -->
            <script src="/static/CACHE/js/1fc48d23e7b6.cmin.js' >
            <!-- myapp/css/base.js+++myapp/css/second.js+++myapp/css/third.js -->

    """
    nodelist = parser.parse(('endcarpool',))
    parser.delete_first_token()

    args = token.split_contents()

    if len(args) != 2:
        raise template.TemplateSyntaxError(
            "%r tag must specify format of either 'js' or 'css' {%% carpool js %%} or {%% carpool css %%}." % args[0])        
    
    format = args[1]
    
    if format not in ('css', 'js'):
        raise template.TemplateSyntaxError(
            "%r tag must specify format of either 'js' or 'css' {%% carpool js %%} or {%% carpool css %%}." % args[0])        
    
    return CarpoolNode(nodelist, format)   


@register.tag('static')
def do_old_static(parser, token):
    return do_static(parser, token)