#!/usr/bin/env python
# -*- coding: utf-8 -*-

from selecta import __version__
from setuptools import setup


options = dict(
    name='python-selecta',
    version=__version__,
    url='http://github.com/ntamas/python-selecta',

    description='Python port of @garybernhardt/selecta',
    license='MIT',

    author='Tamas Nepusz',
    author_email='ntamas@gmail.com',

    package_dir={'selecta': 'selecta'},
    packages=['selecta'],

    entry_points={
        "console_scripts": [
            'selecta = selecta.__main__:main'
        ]
    },

    # TODO
    # test_suite="selecta.test.suite",

    platforms='ALL',
    classifiers=[
        # TODO
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python'
    ]
)

setup(**options)
