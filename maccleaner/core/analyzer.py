"""
Analyzer base class and interfaces.

This module defines the base classes and interfaces for all analyzer implementations,
following the SOLID principles.
"""

import abc
import logging
import traceback
from typing import Dict, List, Optional, Any, Union

# Set up logger
logger = logging.getLogger("maccleaner.core")


class AnalyzerError(Exception):
    """Base exception for analyzer-related errors."""
    pass


class PrerequisiteError(AnalyzerError):
    """Exception raised when an analyzer's prerequisites are not met."""
    pass


class Analyzer(abc.ABC):
    """Abstract base class for all analyzers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Get the name of the analyzer."""
        pass

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Get a description of what this analyzer does."""
        pass

    @abc.abstractmethod
    def check_prerequisites(self) -> bool:
        """
        Check if all prerequisites for this analyzer are met.
        
        Returns:
            bool: True if prerequisites are met, False otherwise
        
        This method should log detailed error messages explaining why
        prerequisites weren't met and what the user can do to fix the issue.
        """
        pass

    @abc.abstractmethod
    def analyze(self, target: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze disk usage for the specified target.
        
        Args:
            target: Optional target to analyze (e.g., application path).
                   If None, analyze all applicable targets.
            
        Returns:
            Dict with analysis results
        """
        pass

    def format_size(self, size_bytes: int) -> str:
        """
        Format size in bytes to a human-readable string.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Human-readable size string (e.g., "1.23 MB")
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB" 