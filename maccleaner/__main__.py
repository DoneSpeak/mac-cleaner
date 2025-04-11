#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main entry point for running MacCleaner as a module.
Example: python -m maccleaner
"""

import sys
from maccleaner.cli import main

if __name__ == "__main__":
    sys.exit(main()) 