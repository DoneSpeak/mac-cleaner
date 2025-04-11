"""
Cleaner base class and interfaces.

This module defines the base classes and interfaces for all cleaner implementations,
following the SOLID principles:
- Single Responsibility: Each cleaner is responsible for one tech stack
- Open/Closed: New cleaners can be added without modifying existing code
- Liskov Substitution: Any cleaner can be used in place of the base class
- Interface Segregation: Cleaners only need to implement what they need
- Dependency Inversion: High-level modules depend on abstractions
"""

import abc
import logging
import traceback
from typing import Dict, List, Optional, Any, Union

# Set up logger
logger = logging.getLogger("maccleaner.core")


class CleanerError(Exception):
    """Base exception for cleaner-related errors."""
    pass


class PrerequisiteError(CleanerError):
    """Exception raised when a cleaner's prerequisites are not met."""
    pass


class Cleaner(abc.ABC):
    """Abstract base class for all cleaners."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Get the name of the cleaner."""
        pass

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Get a description of what this cleaner does."""
        pass

    @abc.abstractmethod
    def check_prerequisites(self) -> bool:
        """
        Check if all prerequisites for this cleaner are met.
        
        Returns:
            bool: True if prerequisites are met, False otherwise
        
        This method should log detailed error messages explaining why
        prerequisites weren't met and what the user can do to fix the issue.
        """
        pass

    @abc.abstractmethod
    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find items that can be cleaned based on the age threshold.
        
        Args:
            days_threshold: Number of days of inactivity before considering an item unused
            
        Returns:
            List of items that can be cleaned with their metadata
        """
        pass

    @abc.abstractmethod
    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific item.
        
        Args:
            item: The item to clean
            dry_run: If True, only simulate the cleaning
            
        Returns:
            bool: True if cleaning was successful or simulated, False otherwise
        """
        pass

    def clean(self, days_threshold: int, dry_run: bool = False) -> bool:
        """
        Main method to run the cleaner.
        
        This is a template method that defines the cleaning workflow.
        Subclasses should not override this method but implement the abstract methods.
        
        Args:
            days_threshold: Number of days of inactivity before considering an item unused
            dry_run: If True, only simulate the cleaning
            
        Returns:
            bool: True if cleaning was successful, False otherwise
        """
        logger.info(f"Running {self.name} cleaner (threshold: {days_threshold} days, dry-run: {dry_run})")
        
        # Check prerequisites
        try:
            if not self.check_prerequisites():
                logger.error(f"Prerequisites for {self.name} cleaner not met")
                return False
        except Exception as e:
            logger.error(f"Error checking prerequisites for {self.name} cleaner: {e}")
            logger.debug(traceback.format_exc())
            return False
        
        # Find items to clean
        try:
            cleanable_items = self.find_cleanable_items(days_threshold)
        except Exception as e:
            logger.error(f"Error finding items to clean for {self.name} cleaner: {e}")
            logger.debug(traceback.format_exc())
            return False
        
        if not cleanable_items:
            logger.info(f"No unused items found for {self.name} cleaner")
            return True
        
        logger.info(f"Found {len(cleanable_items)} items to clean for {self.name}")
        
        # If dry run, just report what would be cleaned
        if dry_run:
            logger.info("DRY RUN: No items will be deleted")
            for item in cleanable_items:
                self._log_item(item, "Would clean")
            return True
        
        # Actually clean items
        success_count = 0
        for item in cleanable_items:
            try:
                if self.clean_item(item, dry_run=False):
                    success_count += 1
                    self._log_item(item, "Cleaned")
                else:
                    self._log_item(item, "Failed to clean")
            except Exception as e:
                logger.error(f"Error cleaning item: {e}")
                logger.debug(traceback.format_exc())
        
        logger.info(f"Successfully cleaned {success_count}/{len(cleanable_items)} items")
        
        return success_count > 0 or len(cleanable_items) == 0
    
    def _log_item(self, item: Dict[str, Any], prefix: str = "Item") -> None:
        """
        Log information about an item in a consistent format.
        
        Args:
            item: The item to log
            prefix: Prefix for the log message
        """
        # Each cleaner can customize how items are displayed by implementing an item_to_str method
        if hasattr(self, "item_to_str") and callable(getattr(self, "item_to_str")):
            item_str = self.item_to_str(item)
        else:
            # Default representation
            item_str = str(item)
        
        logger.info(f"{prefix}: {item_str}") 