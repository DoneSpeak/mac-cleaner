"""Xcode cleaner implementation for cleaning Xcode caches and derived data."""

import logging
import os
import shutil
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import run_command
from maccleaner.cleaners import CLEANER_REGISTRY

logger = logging.getLogger("maccleaner.cleaners.xcode")


class XcodeCleaner(Cleaner):
    """Cleaner for Xcode derived data, caches, and archives."""

    def __init__(self):
        """Initialize the Xcode cleaner."""
        self.home_dir = os.path.expanduser("~")
        self.library_dir = os.path.join(self.home_dir, "Library")
        
        # Xcode specific directories
        self.derived_data_dir = os.path.join(self.library_dir, "Developer/Xcode/DerivedData")
        self.archives_dir = os.path.join(self.library_dir, "Developer/Xcode/Archives")
        self.ios_device_support_dir = os.path.join(self.library_dir, "Developer/Xcode/iOS DeviceSupport")
        self.watchos_device_support_dir = os.path.join(self.library_dir, "Developer/Xcode/watchOS DeviceSupport")
        self.device_logs_dir = os.path.join(self.library_dir, "Developer/Xcode/iOS Device Logs")
        self.previews_dir = os.path.join(self.library_dir, "Developer/Xcode/UserData/Previews")
        
        # Xcode caches
        self.xcode_cache_dir = os.path.join(self.library_dir, "Caches/com.apple.dt.Xcode")

    @property
    def name(self) -> str:
        return "xcode"

    @property
    def description(self) -> str:
        return "Cleans Xcode derived data, caches, old archives, and device support files"

    def display_help(self) -> None:
        """Display detailed help information for the Xcode cleaner."""
        help_text = """
Xcode Cleaner Help
=================

The Xcode cleaner is a tool to clean Xcode-related resources, helping you
reclaim disk space. It can identify and remove:

1. Derived Data - Build products and intermediate build files
2. Archives - Old application archives
3. Device Support Files - Files for specific iOS/watchOS versions
4. Xcode Caches - Various caches used by Xcode

USAGE:
    maccleaner clean xcode [OPTIONS]

OPTIONS:
    --days DAYS     Number of days of inactivity before considering a resource unused
                    (default: 30)
    --dry-run       Only simulate cleaning without actually removing files
    -h, --help      Display this help message

EXAMPLES:
    # List all cleanable Xcode resources (simulation mode)
    maccleaner clean xcode --dry-run

    # Clean all unused Xcode resources older than 30 days
    maccleaner clean xcode

    # Clean unused Xcode resources older than 90 days
    maccleaner clean xcode --days 90

IMPORTANT NOTES:
    - The cleaner scans Xcode's standard directories in ~/Library/Developer/Xcode/
    - Derived data for recently modified projects will be preserved
    - Only archives older than the specified threshold will be removed
    - Cleaning will free up substantial disk space if you use Xcode regularly
"""
        print(help_text)

    def check_prerequisites(self) -> bool:
        """Check if Xcode is installed and if macOS is detected."""
        logger.info("Checking if running on macOS with Xcode installed...")
        
        if not os.path.exists("/Applications/Xcode.app"):
            logger.info("Xcode.app not found in /Applications")
            # Check alternative locations
            if not os.path.exists(self.derived_data_dir):
                logger.error("Xcode does not appear to be installed (DerivedData directory not found)")
                return False
        
        # Check if it's actually macOS
        platform_check = run_command("uname", timeout=5)
        if platform_check and platform_check.strip() != "Darwin":
            logger.error(f"Not running on macOS (detected: {platform_check.strip()})")
            return False
            
        logger.info("Xcode detected on macOS")
        return True

    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find Xcode derived data, archives and caches older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
            
        Returns:
            List of Xcode resources with metadata
        """
        logger.info(f"Searching for Xcode related files older than {days_threshold} days")
        
        cleanable_items = []
        
        # Find old derived data
        derived_data_items = self._find_derived_data(days_threshold)
        if derived_data_items:
            logger.info(f"Found {len(derived_data_items)} derived data directories to clean")
            cleanable_items.extend(derived_data_items)
        
        # Find old archives
        archive_items = self._find_archives(days_threshold)
        if archive_items:
            logger.info(f"Found {len(archive_items)} old Xcode archives to clean")
            cleanable_items.extend(archive_items)
        
        # Find old device support files
        device_support_items = self._find_device_support(days_threshold)
        if device_support_items:
            logger.info(f"Found {len(device_support_items)} old device support directories to clean")
            cleanable_items.extend(device_support_items)
        
        # Check for Xcode caches
        cache_items = self._find_caches(days_threshold)
        if cache_items:
            logger.info(f"Found {len(cache_items)} Xcode cache directories to clean")
            cleanable_items.extend(cache_items)
        
        logger.info(f"Found total of {len(cleanable_items)} Xcode-related items to clean")
        return cleanable_items

    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific Xcode resource.
        
        Args:
            item: The resource to clean
            dry_run: If True, only simulate cleaning
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        item_type = item["type"]
        path = item["path"]
        
        if not os.path.exists(path):
            logger.warning(f"Path does not exist: {path}")
            return False
        
        if dry_run:
            logger.debug(f"[DRY RUN] Would remove {item_type}: {path}")
            return True
        
        logger.info(f"Removing {item_type}: {path}")
        
        try:
            shutil.rmtree(path)
            logger.info(f"Successfully removed {path}")
            return True
        except (PermissionError, OSError) as e:
            logger.error(f"Error removing {path}: {e}")
            return False

    def item_to_str(self, item: Dict[str, Any]) -> str:
        """
        Convert an Xcode resource to a string representation.
        
        Args:
            item: The Xcode resource
            
        Returns:
            String representation of the resource
        """
        item_type = item["type"]
        path = item["path"]
        size_mb = item.get("size_mb", 0)
        age_days = item.get("age_days", 0)
        
        if item_type == "derived_data":
            project_name = os.path.basename(path)
            return f"Derived Data: {project_name} ({size_mb:.2f} MB, {age_days} days old)"
        elif item_type == "archive":
            archive_name = os.path.basename(path)
            return f"Archive: {archive_name} ({size_mb:.2f} MB, {age_days} days old)"
        elif item_type == "device_support":
            ios_version = os.path.basename(path)
            return f"Device Support: {ios_version} ({size_mb:.2f} MB, {age_days} days old)"
        elif item_type == "cache":
            return f"Xcode Cache: {path} ({size_mb:.2f} MB, {age_days} days old)"
        else:
            return str(item)

    def _find_derived_data(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find derived data directories older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of derived data directories to clean
        """
        if not os.path.exists(self.derived_data_dir):
            logger.debug(f"Derived data directory not found: {self.derived_data_dir}")
            return []
            
        derived_data_items = []
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        
        try:
            for item in os.listdir(self.derived_data_dir):
                item_path = os.path.join(self.derived_data_dir, item)
                
                if not os.path.isdir(item_path):
                    continue
                
                # Get directory stats
                mtime = os.path.getmtime(item_path)
                mod_time = datetime.fromtimestamp(mtime)
                age_days = (datetime.now() - mod_time).days
                
                if age_days < days_threshold:
                    logger.debug(f"Derived data is too recent: {item} ({age_days} days old)")
                    continue
                
                size = self._get_directory_size(item_path)
                size_mb = size / (1024 * 1024)  # Convert to MB
                
                logger.debug(f"Found old derived data: {item} ({size_mb:.2f} MB, {age_days} days old)")
                derived_data_items.append({
                    "type": "derived_data",
                    "path": item_path,
                    "size_mb": size_mb,
                    "age_days": age_days,
                    "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "project": item
                })
        except (PermissionError, OSError) as e:
            logger.warning(f"Error scanning derived data directory: {e}")
            
        return derived_data_items

    def _find_archives(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find Xcode archives older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of archives to clean
        """
        if not os.path.exists(self.archives_dir):
            logger.debug(f"Archives directory not found: {self.archives_dir}")
            return []
            
        archive_items = []
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        
        try:
            # First level are date directories (YYYY-MM-DD)
            for date_dir in os.listdir(self.archives_dir):
                date_path = os.path.join(self.archives_dir, date_dir)
                
                if not os.path.isdir(date_path):
                    continue
                
                # Skip if the date directory itself is newer than threshold
                try:
                    date_obj = datetime.strptime(date_dir, "%Y-%m-%d")
                    if (datetime.now() - date_obj).days < days_threshold:
                        logger.debug(f"Archive date directory is too recent: {date_dir}")
                        continue
                except ValueError:
                    # If the directory name doesn't match the expected format, use mtime
                    mtime = os.path.getmtime(date_path)
                    if (datetime.now() - datetime.fromtimestamp(mtime)).days < days_threshold:
                        continue
                
                # Check each archive in the date directory
                for archive in os.listdir(date_path):
                    if not archive.endswith(".xcarchive"):
                        continue
                        
                    archive_path = os.path.join(date_path, archive)
                    
                    # Get archive stats
                    mtime = os.path.getmtime(archive_path)
                    mod_time = datetime.fromtimestamp(mtime)
                    age_days = (datetime.now() - mod_time).days
                    
                    if age_days < days_threshold:
                        logger.debug(f"Archive is too recent: {archive} ({age_days} days old)")
                        continue
                    
                    size = self._get_directory_size(archive_path)
                    size_mb = size / (1024 * 1024)  # Convert to MB
                    
                    logger.debug(f"Found old archive: {archive} ({size_mb:.2f} MB, {age_days} days old)")
                    archive_items.append({
                        "type": "archive",
                        "path": archive_path,
                        "size_mb": size_mb,
                        "age_days": age_days,
                        "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S'),
                        "archive_name": archive
                    })
        except (PermissionError, OSError) as e:
            logger.warning(f"Error scanning archives directory: {e}")
            
        return archive_items

    def _find_device_support(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find iOS and watchOS device support directories older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of device support directories to clean
        """
        device_support_items = []
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        
        # Check iOS device support
        if os.path.exists(self.ios_device_support_dir):
            try:
                for item in os.listdir(self.ios_device_support_dir):
                    item_path = os.path.join(self.ios_device_support_dir, item)
                    
                    if not os.path.isdir(item_path):
                        continue
                    
                    # Get directory stats
                    mtime = os.path.getmtime(item_path)
                    mod_time = datetime.fromtimestamp(mtime)
                    age_days = (datetime.now() - mod_time).days
                    
                    if age_days < days_threshold:
                        logger.debug(f"iOS device support is too recent: {item} ({age_days} days old)")
                        continue
                    
                    size = self._get_directory_size(item_path)
                    size_mb = size / (1024 * 1024)  # Convert to MB
                    
                    logger.debug(f"Found old iOS device support: {item} ({size_mb:.2f} MB, {age_days} days old)")
                    device_support_items.append({
                        "type": "device_support",
                        "path": item_path,
                        "size_mb": size_mb,
                        "age_days": age_days,
                        "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S'),
                        "ios_version": item
                    })
            except (PermissionError, OSError) as e:
                logger.warning(f"Error scanning iOS device support directory: {e}")
        
        # Check watchOS device support
        if os.path.exists(self.watchos_device_support_dir):
            try:
                for item in os.listdir(self.watchos_device_support_dir):
                    item_path = os.path.join(self.watchos_device_support_dir, item)
                    
                    if not os.path.isdir(item_path):
                        continue
                    
                    # Get directory stats
                    mtime = os.path.getmtime(item_path)
                    mod_time = datetime.fromtimestamp(mtime)
                    age_days = (datetime.now() - mod_time).days
                    
                    if age_days < days_threshold:
                        logger.debug(f"watchOS device support is too recent: {item} ({age_days} days old)")
                        continue
                    
                    size = self._get_directory_size(item_path)
                    size_mb = size / (1024 * 1024)  # Convert to MB
                    
                    logger.debug(f"Found old watchOS device support: {item} ({size_mb:.2f} MB, {age_days} days old)")
                    device_support_items.append({
                        "type": "device_support",
                        "path": item_path,
                        "size_mb": size_mb,
                        "age_days": age_days,
                        "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S'),
                        "watchos_version": item
                    })
            except (PermissionError, OSError) as e:
                logger.warning(f"Error scanning watchOS device support directory: {e}")
                
        return device_support_items

    def _find_caches(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find Xcode cache directories older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of cache directories to clean
        """
        if not os.path.exists(self.xcode_cache_dir):
            logger.debug(f"Xcode cache directory not found: {self.xcode_cache_dir}")
            return []
            
        cache_items = []
        
        # Check the main Xcode cache
        if os.path.exists(self.xcode_cache_dir):
            mtime = os.path.getmtime(self.xcode_cache_dir)
            mod_time = datetime.fromtimestamp(mtime)
            age_days = (datetime.now() - mod_time).days
            
            size = self._get_directory_size(self.xcode_cache_dir)
            size_mb = size / (1024 * 1024)  # Convert to MB
            
            if age_days >= days_threshold and size_mb > 50:  # Only if it's substantial size
                logger.debug(f"Found Xcode cache: ({size_mb:.2f} MB, {age_days} days old)")
                cache_items.append({
                    "type": "cache",
                    "path": self.xcode_cache_dir,
                    "size_mb": size_mb,
                    "age_days": age_days,
                    "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                })
                
        # Check for old previews cache
        if os.path.exists(self.previews_dir):
            mtime = os.path.getmtime(self.previews_dir)
            mod_time = datetime.fromtimestamp(mtime)
            age_days = (datetime.now() - mod_time).days
            
            size = self._get_directory_size(self.previews_dir)
            size_mb = size / (1024 * 1024)  # Convert to MB
            
            if age_days >= days_threshold and size_mb > 10:  # Only if it's substantial size
                logger.debug(f"Found Xcode previews cache: ({size_mb:.2f} MB, {age_days} days old)")
                cache_items.append({
                    "type": "cache",
                    "path": self.previews_dir,
                    "size_mb": size_mb,
                    "age_days": age_days,
                    "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                })
                
        # Check for device logs
        if os.path.exists(self.device_logs_dir):
            mtime = os.path.getmtime(self.device_logs_dir)
            mod_time = datetime.fromtimestamp(mtime)
            age_days = (datetime.now() - mod_time).days
            
            size = self._get_directory_size(self.device_logs_dir)
            size_mb = size / (1024 * 1024)  # Convert to MB
            
            if age_days >= days_threshold and size_mb > 5:  # Only if it's substantial size
                logger.debug(f"Found device logs: ({size_mb:.2f} MB, {age_days} days old)")
                cache_items.append({
                    "type": "cache",
                    "path": self.device_logs_dir,
                    "size_mb": size_mb,
                    "age_days": age_days,
                    "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                })
                
        return cache_items

    def _get_directory_size(self, path: str) -> int:
        """
        Get the size of a directory in bytes.
        
        Args:
            path: Directory path
            
        Returns:
            Size in bytes
        """
        total_size = 0
        
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total_size += os.path.getsize(fp)
                    except (FileNotFoundError, PermissionError):
                        pass
        except (PermissionError, OSError):
            pass
            
        return total_size

    def clean(self, days_threshold: int = 30, dry_run: bool = True, args: Optional[List[str]] = None) -> bool:
        """
        Clean Xcode derived data, caches and archives.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
            dry_run: If True, only simulate cleaning
            args: Additional command line arguments
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        # Check for help argument
        if args and ('--help' in args or '-h' in args):
            self.display_help()
            return True
            
        # Continue with regular cleaning process
        return super().clean(days_threshold, dry_run)


# Register this cleaner
CLEANER_REGISTRY["xcode"] = XcodeCleaner 