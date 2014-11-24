#!/usr/bin/env python3
from distutils.core import setup

with open("README.rst", "r") as f:
    long_description = f.read()

setup(name="python3-openttd",
      version="0.1",
      description="OpenTTD administration client library",
      author="Jonas Wielicki",
      author_email="jonas@wielicki.name",
      url="https://github.com/horazont/python3-openttd",
      packages=["openttd"],
      classifiers=[
          "Development Status :: 3 - Alpha",
          "Intended Audience :: Developers",
          "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
          "Operating System :: OS Independent",
          "Programming Language :: Python :: 3 Only",
          "Programming Language :: Python :: 3.4",
          "Topic :: Games/Entertainment :: Simulation",
      ],
)
