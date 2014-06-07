import os
from os import path
import unittest
import sys
import tempfile

PROJECT_PATH = path.dirname(path.dirname(path.abspath(__file__)))
print PROJECT_PATH
sys.path.append(PROJECT_PATH)

TEMP_DIR = tempfile.mkdtemp(prefix='django_')
os.environ['DJANGO_TEST_TEMP_DIR'] = TEMP_DIR

def findtests():
    suite = unittest.defaultTestLoader.discover('tests', '*.py', PROJECT_PATH)
    print suite
    unittest.TextTestRunner().run(suite)



if __name__ == '__main__':
    suite = findtests()
