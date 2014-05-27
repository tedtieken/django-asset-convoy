import os
from setuptools import setup

description = 'Asset packager for Django applications'
try:
    import pypandoc
    long_description = pypandoc.convert('README.md', 'rst')
    print long_description
except (IOError, ImportError):
    print "ioerror or importerror"
    long_description = description

setup(
    name='django-asset-convoy',
    version='0.1.0',
    author='Ted Tieken <ted.tieken@gmail.com>, Peter Conerly <pconerly@gmail.com>',
    author_email='ted.tieken@gmail.com',
    packages=['convoy'],
    scripts=[],
    url='',
    license='MIT',
    description=description,
    long_description=long_description,
    install_requires=[
        "Django >= 1.7.0",
        # TODO update this when either: Django 1.7 is released or we have django 1.6 support
        "django-s3-folder-storage >= 0.2",
        "cssmin >= 0.2.0",
        "rjsmin >= 1.0.9",
    ],
)
