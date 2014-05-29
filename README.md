NB:  This package is experimental pre-alpha software.  The convoy features are more mature than the carpool features. 

Rationale:
---------

`django-asset-convoy` makes static asset best practices nearly effortless without changing your current workflow.  Your files are processed for you when you run collectstatic, and the template tags to access your processed files are easy to use.

Static asset best practices = Faster page loads = happier customers. 

* fingerprint based cachebusting which enables far-future cache exipry headers (cached files load instantly)
* minification (smaller files load faster)
* gzipping that works on S3 (compressed files load faster)
* concatenation (fewer http requests means less latency and faster page loads)

Everything but concatenation is done automatically during the post_process step of django's `python manage.py collectstatic` command.  This means that when Heroku runs collectstatic automatically for you, your assets get post-processed automatically too!  

The  `convoy` template tag is called exactly the same way the staticfiles `static` template tag is called.

The `carpool` template tag that does concatenation is extremely simple (see below).

You get automatic static asset management best practices for about five minutes of one-time configuration.  

NB: convoy's post processing makes the collectstatic command take about twice as long to run.  If you have a lot of unchanged static assets, this can make pushing small changes to Heroku somewhat painful -- ```heroku config:set DISABLE_COLLECTSTATIC=1``` may come in handy if that is the case.

Speed:
---------
With convoy, your pages load faster.  Sometimes a lot faster.  

In initial tests with heroku and s3, using `convoy` and `carpool` sped up DocumentReady times from ~1500 milliseconds average to 546 milliseconds average.  (Google's homepage by hit DocumentReady in 341ms average).  Method: Middle 8 of 10 page loads measured without caching by chrome devtools.  GTmetrix performance reports went from 91%/78% to 99%/98%.  

More tests pending.



What:
---------

django-asset-convoy has a few parts:  

*  static asset storages that automatically process your static assets when you run collectstatic  (fingerprinting/cache-busting with a hash, minifing, and gziping)
*  caching s3 storages that keep a copy on the local filesystem as well as saving on s3 (meaning in-request concatenation goes a lot faster)
*  `convoy` template tag that resolves a resource to its processed counterpartd 
*  `carpool` template tag that concatenates css and js files so they can be served by a single http request.
* A GzipHttpOnlyMiddleware that sidesteps the BREACH security vulnerability on secure HTTPS pages while allowing gzip performance improvements on HTTP pages


Requirements:
---------

    #django >= 1.7
    pip install https://www.djangoproject.com/download/1.7b3/tarball/
    pip install django-s3-folder-storage
    
    pip install cssmin
    pip install rjsmin #recommended
    #or pip install jsmin
  
Optional, but speeds up your pages even more: `django-htmlmin`


Configuration:
---------

    #settings.py
    INSTALLED_APPS = (
        ...
        'convoy',
        ...
    )
    
##### Option 1: Using the filesystem:

    #settings.py
    STATICFILES_STORAGE = 'convoy.stores.ConvoyStorage'  
    
    #Set STATIC_ROOT, STATIC_URL, etc, as normal  


##### Option 2: Using s3-folder-storage    

    #settings.py
    
    #one of these
    STATICFILES_STORAGE = 'convoy.stores.S3FolderConvoyStorage'
    STATICFILES_STORAGE = 'convoy.stores.CachedS3FolderConvoyStorage'

    #Set the following to their appropriate variables
    AWS_STORAGE_BUCKET_NAME = 'my-bucket'
    AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
    AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
    DEFAULT_FILE_STORAGE = 's3_folder_storage.s3.DefaultStorage'
    DEFAULT_S3_PATH = "media"
    STATIC_S3_PATH = "static"
    MEDIA_ROOT = '/%s/' % DEFAULT_S3_PATH
    STATIC_ROOT = "/%s/" % STATIC_S3_PATH
    MEDIA_URL = 'http://%s.s3.amazonaws.com/media/' % AWS_STORAGE_BUCKET_NAME
    STATIC_URL = 'http://%s.s3.amazonaws.com/static/' % AWS_STORAGE_BUCKET_NAME
    ADMIN_MEDIA_PREFIX = STATIC_URL + 'admin/'

Backends are provided for s3 without s3-folder-storage, not recomended.

##### Suggested configuration:

    #settings.py
    CONVOY_AWS_HEADERS = {
        #Cache processed assets for a full year 
        'Cache-Control': 'max-age=%s' % (60 * 60 * 24 * 365),
    }


##### Configuring the HTTP Only Gzip Middleware:

    #settings.py
    MIDDLEWARE_CLASSES = (
        'convoy.middleware.GzipHttpOnlyMiddleware',
        ...
    )



Usage: automatic asset pipeline during collectstatic:
------------
When you run `python manage.py collectstatic` convoy will automatically fingerprint (hash), minify the static files that can be minified, and gzip the css and js.  

Then in your template `{% load convoytags %}` will get you two new tags `convoy` and `carpool` whose usage is as follows:



Using the `convoy` template tag
------------
The `convoy` template tag works just like the `static` template tag provided by `django.contrib.staticfiles`
    
    Usage::

        {% convoy path [as varname] %}

    Examples::

        {% convoy "myapp/css/base.css" %}
        {% convoy variable_with_path %}
        {% convoy "myapp/css/base.css" as admin_base_css %}
        {% convoy variable_with_path as varname %}   

A sample use in a template would be:

    mypage.html
    {% load convoytags %}
    <link rel="stylesheet" href="{% convoy "myapp/css/base.css" %}">    

Would render:

    <!-- If gzip isn't supported by the request, or isn't enabled -->
    <link rel="stylesheet" href="/STATIC_ROOT/myapp/css/base.25b23dfca187.cmin.css" >
    
    <!-- or, if gzip is enabled -->
    <link rel="stylesheet" href="/STATIC_ROOT/myapp/css/base.25b23dfca187.cmin.css.gz" >



Using the `carpool` template tag
------------
The `carpool` template tag is a concatenator, it works similarly to the `compress` tag in django-compressor.  

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
        
        If concatenation and pipelining is successful:
            <!-- myapp/css/base.css+++myapp/css/second.css+++myapp/css/third.css -->
            <link rel="stylesheet" href="/static/CARPOOL/css/fb12a26e32dc.cmin.css' ">
            <!-- myapp/css/base.css+++myapp/css/second.css+++myapp/css/third.css -->
            
        If not, falls back to:
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
            <script type="text/javascript" src="/static/CARPOOL/js/1fc48d23e7b6.cmin.js' >
            <!-- myapp/css/base.js+++myapp/css/second.js+++myapp/css/third.js -->


Optional configuration:
---------
    
##### Settings you might want to change and their defaults:

` CONVOY_USE_EXISTING_MIN_FILES = True` Attempts to get the distributed min that matches a given filename e.g. if you have bootstrap.css, convoy would look for bootstrap.min.css if bootstrap.min.css is found, convoy will use bootstrap's minified version instead of minifiying the files itself
    
` CONVOY_GZIP_IN_TEMPLATE = True` When True: checks if the request says it accepts gzip, and if so links to the gzip file from the template, this is useful for serving gziped files from AWS When False: returns the processed but not gziped version of the file

` CONVOY_AWS_HEADERS = {}` AWS headers for processed assets because convoyed assets go through a fingerprinting step, you can safely set far-future headers (so long as you don't link to the unprocessed assets in your templates)
    
` CONVOY_LOCAL_CACHE_ROOT = STATIC_ROOT` If using a cached s3 storage, where do we store the cached files?
    
` CARPOOL_CACHE_PATH_FRAGMENT = "CARPOOL" ` Where should we the combined files? They will be stored at this path below STATIC_ROOT
   
` CARPOOL_COMBINE_ORIGINALS = False ` When set to True, concatenates the original, unprocessed, files instead of the pre-processed files.   

` CARPOOL_COMBINE_DURING_REQUEST = True ` Whether we should attempt to combine files during the request response cycle.  Currently serves as a way to turn off concatenation behavior In future will be part of the toggles to enable post-request processing

` CARPOOL_CSS_TEMPLATE = u'<link rel="stylesheet" href="%s" >\n' `  The unicode string to use when rendering a css asset path into an HTML tag. 

` CARPOOL_JS_TEMPLATE = u'<script type="text/javascript" src="%s" ></script>\n' ` The unicode string to use when rendering a Javascript asset path into an HTML tag.

` CARPOOL_START_COMMENT_TEMPLATE = u"\n<!-- %s -->\n" ` The HTML comment placed before carpool CSS or JS tags are rendered.  Can be set to a falsy value, if you don't want the comment to be added.

` CARPOOL_END_COMMENT_TEMPLATE = CARPOOL_START_COMMENT_TEMPLATE ` The HTML comment placed after carpool CSS or JS tags are rendered.  Can be set to a falsy value, if you don't want the comment to be added.


##### Settings for when DEBUG=True

` CONVOY_DURING_DEBUG = False` When True and DEBUG=True, `convoy` template tag returns processed file urls for each asset path (e.g. 'myfile.css' becomes 'myfile.fb12a26e32dc.cmin.css').  When CONVOY_DURING_DEBUG = False and DEBUG = True, `convoy` template tag returns the url to the original, unprocessed, file (e.g. 'myfile.css' stays 'myfile.css')

NB:  Using CONVOY_DURING_DEBUG requires additional setup.  You must 

* run collectstatic locally `$ python manage.py collectstatic` 
* configure an explicit static serving url in your urls.py `url(r'^static/(?P<path>.*)$', 'django.views.static.serve',{'document_root': settings.STATIC_ROOT})`
* run runserver with the `--nostatic` option `$ python manage.py runserver --nostatic` 

` CARPOOL_COMBINE_DURING_DEBUG = False` When True and DEBUG = True, `carpool` template tag will concatenates files.  To use this setting, you must set CONVOY_DURING_DEBUG to True.  When CARPOOL_COMBINE_DURING_DEBUG = False and DEBUG = True, `carpool` template tag renders each asset path into individual `<link rel='stylesheet' href="..." >` or `<script type="text/javascript" src="..."></script>` tags without concatenating them.  


##### Settings unlikely going to need:

`CONVOY_CONSERVATIVE_MSIE_GZIP = False` If set to True, will never attempt to serve gziped files to MSIE identified browsers. You are unlikely to need this unless you're writing your own subclasses that gzip more than just js and css files 
    
`CONVOY_AWS_QUERYSTRING_AUTH = False` Convoy is known to break if you set this to True -- don't.  We have a special file here so you can still use querystring  auth in your media files if you want to.


### Development setup

Requires pandoc [https://github.com/jgm/pandoc/releases](https://github.com/jgm/pandoc/releases) for registering on pypi.

If you want to include convoy locally, use `pip install -e /path/to/convoy/`

