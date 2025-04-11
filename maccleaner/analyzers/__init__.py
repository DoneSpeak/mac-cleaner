"""Analyzers for application disk usage statistics."""

from typing import Dict, Type

from maccleaner.core.analyzer import Analyzer

# This will be populated by each analyzer module
ANALYZER_REGISTRY: Dict[str, Type[Analyzer]] = {}

# Import all analyzer modules to ensure they register themselves
from . import app_analyzer 