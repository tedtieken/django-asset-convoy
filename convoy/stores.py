from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage, HashedFilesMixin, ManifestFilesMixin
from django.contrib.staticfiles.utils import matches_patterns
from django.core.files.base import ContentFile
from django.core.files import File
from django.utils.six.moves.urllib.parse import unquote

from s3_folder_storage.s3 import StaticStorage as S3FolderStaticStorage
from s3_folder_storage.s3 import FixedS3BotoStorage as S3BotoStorage

from collections import OrderedDict
from io import BytesIO
import copy
import gzip
import json

import cssmin
try:
    from _rjsmin import jsmin
except ImportError:
    try:
        from rjsmin import jsmin
    except ImportError:
        from jsmin import jsmin as _jsmin
        def jsmin(string, *args, **kwargs):
            return _jsmin(string)

CONVOY_USE_EXISTING_MIN_FILES = getattr(settings, "CONVOY_USE_EXISTING_MIN_FILES", False)
CONVOY_AWS_QUERYSTRING_AUTH = getattr(settings, 'CONVOY_AWS_QUERYSTRING_AUTH', True)
CONVOY_AWS_HEADERS = getattr(settings, 'CONVOY_AWS_HEADERS', {})
CONVOY_LOCAL_CACHE_ROOT = getattr(settings, 'CONVOY_LOCAL_CACHE_ROOT', getattr(settings, "STATIC_ROOT", ""))

class S3LocalCachedMixin(object):
    """
    Mixin that adds local caching to S3 storage backend
    """
    def __init__(self, *args, **kwargs):
        super(S3LocalCachedMixin, self).__init__(*args, **kwargs)
        self._local = StaticFilesStorage(location=CONVOY_LOCAL_CACHE_ROOT)

    def save(self, name, content, *args, **kwargs):
        if not hasattr(content, 'chunks'):
            content = ContentFile(content)              
        sname = self._save(name, content, *args, **kwargs)
        return sname
        
    def _save(self, name, content, *args, **kwargs):
        # some configurations of s3 backend mutate the content in place 
        # Esp when AWS_IS_GZIPPED = True
        # keep a pre-mutation copy for the local cache so we don't save garbage to disk
        orig_content = copy.copy(content)
        sname = super(S3LocalCachedMixin, self)._save(name, content, *args, **kwargs)
        if self._local.exists(name):
            self._local.delete(name)
        lname = self._local._save(name, orig_content, *args, **kwargs)
        return name        
        
    def delete(self, *args, **kwargs):
        if self._local.exists(*args, **kwargs):
            self._local.delete(*args, **kwargs)
        return super(S3LocalCachedMixin, self).delete(*args, **kwargs)
        
    def open(self, name, *args, **kwargs):
        if self._local.exists(name):
            #print "reading %s from cache" % name
            return self._local.open(name, *args, **kwargs)
        else:
            #print "reading %s from network" % name
            the_file = super(S3LocalCachedMixin, self).open(name, *args, **kwargs)
            #we had a cache miss, save it locally for the future
            self._local.save(name, the_file)
            if hasattr(the_file, "seek"):
                the_file.seek(0)
            return the_file
    
    def local_path(self, *args, **kwargs):
        return self._local.path(*args, **kwargs)

class ChainableHashedFilesMixin(HashedFilesMixin):
    _should_hash = True
    '''
    Over-rides behavior of HashedFilesMixin to be chainable in our pipeline
    '''
    def post_process(self, paths, dry_run=False, **options):
        # Do HashedFilesMixin's proprietary stuff
        if self._should_hash:
            print "starting hash super 1", len(paths)   
            super_class = super(HashedFilesMixin, self)
            if hasattr(super_class, 'post_process'):
                for name, hashed_name, processed in super_class.post_process(paths.copy(), dry_run, **options):
                    if hashed_name != name:
                        #Delete so we keep a chain
                        if paths.has_key(name):
                            del paths[name]
                        paths[hashed_name] = (self, hashed_name)               
                    yield name, hashed_name, processed
            print "leave hash super 1", len(paths)   

            #Then continue the chain
            print "Starting Hash super 2", len(paths)   
            super_class = super(ChainableHashedFilesMixin, self)
            if hasattr(super_class, 'post_process'):
                for name, hashed_name, processed in super_class.post_process(paths.copy(), dry_run, **options):
                    if hashed_name != name:
                        if paths.has_key(name):
                            del paths[name]
                        paths[hashed_name] = (self, hashed_name)                       
                    yield name, hashed_name, processed        
            print "leave Hash super 2", len(paths)   


class MinifyMixin(object):
    '''
    Adds a Minification step to the pipeline
    '''    
    min_patterns = ("*.css", "*.js")
    min_anti_pattern = ".min."
    _should_minify = True
    
    def _min_compress(self, original_file, file_type):
        if file_type == "css":
            return cssmin.cssmin(original_file.read())
        elif file_type == "js":
            return jsmin(original_file.read(), keep_bang_comments=True)
            #return _rjsmin.jsmin(str(original_file.read()), keep_bang_comments=True)
            #return uglipyjs.compile(original_file.read())
            #return slimit.minify(original_file.read())
        return original_file
        
    def post_process(self, paths, dry_run=False, **options):
        print "min enter super", len(paths)
        super_class = super(MinifyMixin, self)
        if hasattr(super_class, 'post_process'):
            for name, hashed_name, processed in super_class.post_process(paths.copy(), dry_run, **options):
                if hashed_name != name:
                    if paths.has_key(name):
                        del paths[name]
                    paths[hashed_name] = (self, hashed_name)
                yield name, hashed_name, processed
        print "min leave super", len(paths)   

        if not self._should_minify:
            return
        if dry_run:
            return
        hashed_files = OrderedDict()
        
        print "starting minify step"
        for path in paths:
            if path:
                if not matches_patterns(path, self.min_patterns):
                    continue
                if self.min_anti_pattern in str(path):
                    continue
                original_file = self.open(path)
                convoy_split_path = path.split(".")
                convoy_split_path.insert(-1, "cmin")
                convoy_min_path = ".".join(convoy_split_path)
                
                min_contents = False
                if CONVOY_USE_EXISTING_MIN_FILES:
                    #This works best if minification is FIRST OR SECOND in the pipeline
                    # if a minified file exists from the distribution, use it 
                    # we want all bugs in minified code to match the distributed bugs 1 to 1
                    split_path = path.split(".")
                    # Kludge for if there is a hash in the filename
                    # Tolerable because we falback to minifying it ourselves
                    # TODO: break this out into a has_hash or has_fingerprint method
                    #       that looks at the filesystem for the un-hashed file
                    # TODO: write a test that fails if django increases the hash length
                    if len(split_path[-2]) == 12 and len(split_path) > 2: 
                        split_path.pop(-2)
                    split_path.insert(-1, "min")
                    dist_min_path = ".".join(split_path)
                    if self.exists(dist_min_path):
                        print "Using existing minified file %s" % dist_min_path
                        #Copy the existing minified file into our name scheme
                        f = self.open(dist_min_path)
                        min_contents = f.read()
                        f.close()
                if not min_contents:
                    min_contents = self._min_compress(original_file, convoy_split_path[-1])
                
                if self.exists(convoy_min_path):
                    self.delete(convoy_min_path)
                saved_name = self.save(convoy_min_path, ContentFile(min_contents))
                hashed_files[self.hash_key(path)] = convoy_min_path
                yield path, convoy_min_path, True

        self.hashed_files.update(hashed_files)


class GZIPMixin(object):
    '''
    Adds a Gzipping step to the pipeline
    Based on GZIPMixin from from django-pipeline
    '''
    gzip_patterns = ("*.css", "*.js")
    _should_gzip = True

    def _gzip_compress(self, original_file):
        content = BytesIO()
        gzip_file = gzip.GzipFile(mode='wb', fileobj=content, mtime=0)
        gzip_file.write(original_file.read())
        gzip_file.close()
        content.seek(0)
        return File(content)

    def post_process(self, paths, dry_run=False, **options):
        print "gzip enter super", len(paths)           
        super_class = super(GZIPMixin, self)
        if hasattr(super_class, 'post_process'):
            for name, hashed_name, processed in super_class.post_process(paths.copy(), dry_run, **options):
                if hashed_name != name:
                    if paths.has_key(name):
                        del paths[name]
                    paths[hashed_name] = (self, hashed_name)                    
                yield name, hashed_name, processed
        print "gzip leave super", len(paths)

        if not self._should_gzip:
            return        
        if dry_run:
            return    
        hashed_files = OrderedDict()

        print "starting gzip step"
        for path in paths:
            if path:
                if not matches_patterns(path, self.gzip_patterns):
                    continue
                original_file = self.open(path)
                original_file.seek(0)
                gzipped_path = "{0}.gz".format(path)
                gzipped_file = self._gzip_compress(original_file)
                gzipped_file.seek(0)
                if self.exists(gzipped_path):
                    self.delete(gzipped_path)
                saved_name = self.save(gzipped_path, gzipped_file)                
                hashed_files[self.hash_key(path)] = gzipped_path
                yield path, gzipped_path, True
                
        self.hashed_files.update(hashed_files)


class ChainableManifestFilesMixin(ManifestFilesMixin):
    '''
    Over-rides behavior of ManifestFilesMixin to be chainable in our pipeline
    '''
    _should_manifest = True

    def post_process(self, paths, dry_run=False, **options):
        print "Starting manifest super", len(paths)           
        super_class = super(ChainableManifestFilesMixin, self)
        if hasattr(super_class, 'post_process'):
            for name, hashed_name, processed in super_class.post_process(paths.copy(), dry_run, **options):
                if hashed_name != name:
                    if paths.has_key(name):
                        del paths[name]
                    paths[hashed_name] = (self, hashed_name)                       
                yield name, hashed_name, processed
        print "leave manifest super", len(paths)   

        if not self._should_manifest:
            return
        if dry_run:
            return
        
        payload = {'paths': self.hashed_files, 'version': self.manifest_version}
        if self.exists(self.manifest_name):
            self.delete(self.manifest_name)
        contents = json.dumps(payload).encode('utf-8')
        self.save(self.manifest_name, ContentFile(contents))


class ConvoyBase(ChainableManifestFilesMixin, GZIPMixin, MinifyMixin, ChainableHashedFilesMixin):
    '''
    Sets up a storage for convoying assets
     - On collect-static the mixins chain off of post_process
     - Order is important: ChainableManifestFilesMixin must be first from the left
     - Order is important: MinifyMixin works best the far right or with directly right of 
                           ChainableHashedFilesMixin
     
     - Sets up storage methods to be invoked by the {% convoy %} template tags
    '''
    def _is_gzip_file(self, name):
        if name and (name[-3:] == ".gz" or ".gz." in name):
            return True
        return False
    
    def get_next_link(self, name):
        '''
        A reimplementation of stored_name that won't try to hash a file if there isn't a link
        needed so we can walk our chain: 
           base > base.fingerprint > base.fingerprint.min > base.fingerprint.min.gz
        
        returns None when it doesn't find an existing link
        '''
        hash_key = self.hash_key(name)
        cache_name = self.hashed_files.get(hash_key)
        return cache_name
        
    def get_full_chain(self, name):
        return self.get_chain(name, gzip=True)
        
    def get_chain(self, name, dry_mode=False, gzip=False):
        #TODO
        # Should there be some kind of checking on get_full_chain to see if the file actually exists?
        chain = []
        latest_link = name
        while latest_link is not None:
            #If we are allowing GZIP files, or if this isn't a gziped file append it
            if gzip or not self._is_gzip_file(latest_link): 
                chain.append(latest_link)
            latest_link = self.get_next_link(latest_link)            
        return chain
        
    def get_terminal_entry(self, name, dry_mode=False, gzip=False):
        if dry_mode:
            return name
        chain = self.get_chain(name, gzip=gzip)
        if chain:
            return chain[-1]
        else:
            return None
        
    def get_terminal_url(self, name, dry_mode=False, gzip=False):
        terminal_entry = self.get_terminal_entry(name, dry_mode, gzip)
        final_url = super(HashedFilesMixin, self).url(terminal_entry)
        return unquote(final_url)


class S3ConvoyMixin(object):
    '''
    Adds the ability to override S3 settings only for convoyed assets
    - remove auth-string, customize headers for static assets only
    - over-ride to content-encoding headers to serve gzipped assets correctly
    '''
    #TODO write a test that fails if our assumptions of S3BotoStorage change
    def __init__(self, *args, **kwargs):
        super(S3ConvoyMixin, self).__init__(*args, **kwargs)
        self.querystring_auth = CONVOY_AWS_QUERYSTRING_AUTH 
        self.headers = CONVOY_AWS_HEADERS
        
    def _save(self, name, content, *args, **kwargs):
        ''' 
        Check to see if we're uploading a gzip file, if so mark it as such for 
        the s3 uplaod
        '''
        #TODO: check if there is a hash, if there isn't mark the file as private
        #      this will make it impossible to shoot ourselves in the foot by accidentally serving
        #      non fingerprinted files
        #      ?? is this a good idea?
        
        self._orig_headers = self.headers.copy()
        self._orig_gzip = self.gzip
        if self._is_gzip_file(name):
            self.headers.update({
                    'Content-Encoding': 'gzip',
                    #http://gtmetrix.com/specify-a-vary-accept-encoding-header.html 
                    'Vary': "Accept-Encoding", 
                })
            #Don't let s3 storage gzip it a second time
            self.gzip = False
        sname = super(S3ConvoyMixin, self)._save(name, content, *args, **kwargs)
        self.headers = self._orig_headers
        self.gzip = self._orig_gzip
        return sname
    

class ConvoyStorage(ConvoyBase, StaticFilesStorage):
    pass

class S3ConvoyStorage(S3ConvoyMixin, ConvoyBase, S3BotoStorage):
    pass

class CachedS3ConvoyStorage(S3ConvoyMixin, ConvoyBase, S3LocalCachedMixin, S3BotoStorage):
    pass

class S3FolderConvoyStorage(S3ConvoyMixin, ConvoyBase, S3FolderStaticStorage):
    pass

class CachedS3FolderConvoyStorage(S3ConvoyMixin, ConvoyBase, S3LocalCachedMixin, S3FolderStaticStorage):
    pass
          
