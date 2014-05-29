from django.conf import settings
from django import template
from django.template.base import Node
from django.utils.encoding import iri_to_uri
from django.utils.six.moves.urllib.parse import urljoin
from django.contrib.staticfiles.templatetags.staticfiles import StaticFilesNode, do_static
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import ImproperlyConfigured

from convoy.utils import CssAbsolute, concatenate_and_hash
from convoy.utils import request_accepts_gzip, convoy_terminus, convoy_chain, convoy_from_context

CONVOY_DURING_DEBUG = getattr(settings, "CONVOY_DURING_DEBUG", False)
CARPOOL_COMBINE_DURING_DEBUG = getattr(settings, "CARPOOL_COMBINE_DURING_DEBUG", False)
CARPOOL_PATH_FRAGMENT = getattr(settings, "CARPOOL_CACHE_PATH_FRAGMENT", "CARPOOL")
CARPOOL_COMBINE_ORIGINALS = getattr(settings, "CARPOOL_COMBINE_ORIGINALS", False)
CARPOOL_COMBILE_DURING_REQUEST = getattr(settings, "CARPOOL_COMBINE_DURING_REQUEST", True)
if settings.DEBUG and CARPOOL_COMBINE_DURING_DEBUG and not CONVOY_DURING_DEBUG:
    raise ImproperlyConfigured("When DEBUG=True and CARPOOL_COMBINE_DURING_DEBUG=True, you must also set CONVOY_DURING_DEBUG=True")

CARPOOL_CSS_TEMPLATE = getattr(settings, "CARPOOL_CSS_TEMPLATE", u'<link rel="stylesheet" href="%s" >\n')
CARPOOL_JS_TEMPLATE  = getattr(settings, "CARPOOL_JS_TEMPLATE", u'<script type="text/javascript" src="%s" ></script>\n')
CARPOOL_START_COMMENT_TEMPLATE = getattr(settings, "CARPOOL_START_COMMENT_TEMPLATE", u"\n<!-- %s -->\n")
CARPOOL_END_COMMENT_TEMPLATE = getattr(settings, "CARPOOL_END_COMMENT_TEMPLATE", CARPOOL_START_COMMENT_TEMPLATE)


register = template.Library()


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


class CarpoolNode(template.Node):
    def __init__(self, nodelist, format, storage=None):
        if not storage:
            self.storage = staticfiles_storage
        self.nodelist = nodelist
        self.format = format
        
    def resolve_paths_to_combine(self, paths):
        convoyable_paths = []
        unconvoyable_paths = []
        for p in paths:
            chain = convoy_chain(p, gzip=False) #can't concatenate gziped files
            if chain:
                if CARPOOL_COMBINE_ORIGINALS:
                    convoyable_paths.append(chain[0])
                else:
                    convoyable_paths.append(chain[-1])
            else:
                unconvoyable_paths.append(path)
        return convoyable_paths, unconvoyable_paths     
        
    def comment_key_in_cache(self, comment_key):
        storage = self.storage
        if hasattr(storage, 'get_next_link'):
            # First check in the convoy project's storages
            return self.storage.get_next_link(comment_key) 
        elif hasattr(storage, 'hashed_files'):
            # Fallback to staticfiles default method
            # This _should_ allow the tag to be used with CachedFilesMixin, 
            # but that hasn't been tested or confirmed yet
            return self.storage.hashed_files.get(comment_key)
        return False
        
    def create_comment_key(self, paths):
        return u"+++".join([convoy_terminus(x, gzip=False).split("/")[-1] for x in paths])
        
    def tag_for_filename(self, file_name, context):
        if self.format == "css":
            return CARPOOL_CSS_TEMPLATE % convoy_from_context(file_name, context) 
        elif self.format == "js":
            return CARPOOL_JS_TEMPLATE % convoy_from_context(file_name, context)
        
    def render(self, context):
        node_text = self.nodelist.render(context)
        # if the line has content get just the path without whitespaces or quotes
        paths = [x.strip(' \'"\r') for x in node_text.split('\n') if bool(x.strip())]
        convoyable_paths, unconvoyable_paths = self.resolve_paths_to_combine(paths)
        compressed_file_name = None
        comment_key = self.create_comment_key(convoyable_paths)
        in_cache = self.comment_key_in_cache(comment_key) 
        
        # Part 1: compression work
        if CARPOOL_COMBILE_DURING_REQUEST: 
            if settings.DEBUG and not CARPOOL_COMBINE_DURING_DEBUG: 
                unconvoyable_paths = paths
            else:
                if in_cache:
                    compressed_file_name = in_cache
                else:
                    #Combine the if we can
                    compressed_file_name = concatenate_and_hash(convoyable_paths, comment_key, self.format)
        else:
            if in_cache:
                compressed_file_name = in_cache
            else:
                #TODO: create mechanisms for enqueuing this to be compressed after the request
                # celery, monkey patched close
                unconvoyable_paths = paths
        
        # Part 2: rendering work
        out = CARPOOL_START_COMMENT_TEMPLATE % comment_key if CARPOOL_START_COMMENT_TEMPLATE else ""
        if not compressed_file_name:
            #We couldn't compress for some reason, render all files individually
            unconvoyable_paths = paths
        else:
            out += self.tag_for_filename(compressed_file_name, context)
        # Part 2b: failsafe rendering work
        # Unconveyable paths is our fallback, anything that was uncompressable or 
        # failed compression gets added individually
        for path in unconvoyable_paths: 
            out += self.tag_for_filename(path, context)
        out += CARPOOL_END_COMMENT_TEMPLATE % comment_key if CARPOOL_END_COMMENT_TEMPLATE else ""

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
            <script type="text/javascript" src="/static/CACHE/js/1fc48d23e7b6.cmin.js' >
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