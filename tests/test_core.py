"""Tests for the core functionality of MacCleaner."""

import pytest
from unittest.mock import MagicMock, patch

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import human_readable_size


def test_human_readable_size():
    """Test the human_readable_size function."""
    assert human_readable_size(0) == "0B"
    assert human_readable_size(1024) == "1.00 KB"
    assert human_readable_size(1024 * 1024) == "1.00 MB"
    assert human_readable_size(1024 * 1024 * 1024) == "1.00 GB"
    assert human_readable_size(1024 * 1024 * 1024 * 1024) == "1.00 TB"


class MockCleaner(Cleaner):
    """Mock cleaner for testing."""
    
    def __init__(self):
        self.items = []
        self.cleaned_items = []
    
    @property
    def name(self):
        return "mock"
    
    @property
    def description(self):
        return "Mock cleaner for testing"
    
    def check_prerequisites(self):
        return True
    
    def find_cleanable_items(self, days_threshold):
        return self.items
    
    def clean_item(self, item, dry_run=True):
        if not dry_run:
            self.cleaned_items.append(item)
        return True


def test_cleaner_dry_run():
    """Test the cleaner with dry run mode."""
    cleaner = MockCleaner()
    cleaner.items = [{"id": "1", "name": "item1"}, {"id": "2", "name": "item2"}]
    
    # In dry run mode, no items should be cleaned
    result = cleaner.clean(30, dry_run=True)
    assert result is True
    assert len(cleaner.cleaned_items) == 0


def test_cleaner_actual_run():
    """Test the cleaner with actual run mode."""
    cleaner = MockCleaner()
    cleaner.items = [{"id": "1", "name": "item1"}, {"id": "2", "name": "item2"}]
    
    # In actual run mode, items should be cleaned
    result = cleaner.clean(30, dry_run=False)
    assert result is True
    assert len(cleaner.cleaned_items) == 2
    assert cleaner.cleaned_items[0]["id"] == "1"
    assert cleaner.cleaned_items[1]["id"] == "2"


def test_cleaner_no_items():
    """Test the cleaner with no items to clean."""
    cleaner = MockCleaner()
    cleaner.items = []
    
    # When no items are found, the cleaner should still return True
    result = cleaner.clean(30, dry_run=False)
    assert result is True
    assert len(cleaner.cleaned_items) == 0 