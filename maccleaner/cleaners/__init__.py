"""Cleaner implementations for various tech stacks."""

from typing import Dict, Type

from maccleaner.core.cleaner import Cleaner

# This will be populated by each cleaner module
CLEANER_REGISTRY: Dict[str, Type[Cleaner]] = {}

# Import all cleaner modules to ensure they register themselves
from . import maven
from . import docker
from . import git
from . import k8s
from . import npm
from . import xcode
from . import brew
from . import python
from . import simulator 