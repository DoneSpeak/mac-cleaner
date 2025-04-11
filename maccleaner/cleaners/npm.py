"""NPM cleaner implementation for cleaning npm caches and node_modules."""

import json
import logging
import os
import shutil
import subprocess
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import run_command
from maccleaner.cleaners import CLEANER_REGISTRY

logger = logging.getLogger("maccleaner.cleaners.npm")


class NPMCleaner(Cleaner):
    """Cleaner for NPM caches and node_modules directories."""

    def __init__(self):
        """Initialize the NPM cleaner."""
        self.home_dir = os.path.expanduser("~")
        self.npm_cache_dir = os.path.join(self.home_dir, ".npm")
        
        # Default directory to scan for node_modules
        self.current_dir = os.getcwd()
        
        # Default project directories to scan for node_modules
        self.scan_dirs = []  # Will be set in clean() method based on args
        
        # Directories to exclude from scanning
        self.exclude_dirs = {
            "node_modules",  # Don't recurse into node_modules
            "Library",
            "Movies",
            "Music",
            "Pictures",
            "Applications",
            ".Trash",
            "node_modules/.cache"
        }
        
        # Maximum depth to search for node_modules
        self.max_depth = 8

    @property
    def name(self) -> str:
        return "npm"

    @property
    def description(self) -> str:
        return "Cleans npm caches and unused node_modules directories"

    def display_help(self) -> None:
        """Display detailed help information for the NPM cleaner."""
        help_text = """
NPM Cleaner Help
===============

The NPM cleaner is a tool to clean npm-related resources, helping you
reclaim disk space. It can identify and remove:

1. NPM cache - Package cache files stored in ~/.npm directory
2. node_modules directories - Unused node_modules directories in the current directory

USAGE:
    maccleaner clean npm [OPTIONS]

OPTIONS:
    --days DAYS     Number of days of inactivity before considering a resource unused
                    (default: 30)
    --dry-run       Only simulate cleaning without actually removing files
    --repo PATH     Specify a target directory to scan for node_modules instead of
                    the current directory
    -h, --help      Display this help message

EXAMPLES:
    # List all cleanable npm resources (simulation mode)
    maccleaner clean npm --dry-run

    # Clean all unused npm resources older than 30 days
    maccleaner clean npm

    # Clean unused npm resources older than 90 days
    maccleaner clean npm --days 90

    # Clean unused npm resources in a specific repository
    maccleaner clean npm --repo /path/to/your/project

IMPORTANT NOTES:
    - By default, the cleaner only scans ~/.npm cache and the current directory
    - When --repo is specified, the current directory is not scanned
    - Active projects (with recent access) will not have their node_modules removed
    - The cleaner checks for orphaned node_modules (no package.json in parent)
    - Only substantial node_modules directories (>5MB) will be considered for removal
"""
        print(help_text)

    def check_prerequisites(self) -> bool:
        """Check if npm is installed and accessible."""
        logger.info("Checking npm installation...")
        
        npm_check = run_command("npm --version", timeout=10)
        if not npm_check:
            logger.error("npm is not installed or not available in PATH")
            return False
        
        logger.info(f"npm detected: version {npm_check.strip()}")
        return True

    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find npm caches and unused node_modules directories.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
            
        Returns:
            List of npm caches and node_modules directories with metadata
        """
        logger.info(f"Searching for npm caches and node_modules older than {days_threshold} days")
        
        cleanable_items = []
        
        # Check npm cache
        npm_cache_items = self._find_npm_cache_items(days_threshold)
        if npm_cache_items:
            logger.info(f"Found {len(npm_cache_items)} npm cache items to clean")
            cleanable_items.extend(npm_cache_items)
        
        # Find unused node_modules directories
        node_modules_dirs = self._find_node_modules_dirs(days_threshold)
        if node_modules_dirs:
            logger.info(f"Found {len(node_modules_dirs)} unused node_modules directories to clean")
            cleanable_items.extend(node_modules_dirs)
        
        logger.info(f"Found total of {len(cleanable_items)} npm-related items to clean")
        return cleanable_items

    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific npm-related resource.
        
        Args:
            item: The resource to clean
            dry_run: If True, only simulate cleaning
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        item_type = item["type"]
        path = item["path"]
        
        if dry_run:
            logger.debug(f"[DRY RUN] Would clean {item_type}: {path}")
            return True
        
        if item_type == "npm_cache":
            return self._clean_npm_cache(dry_run)
        elif item_type == "node_modules":
            return self._clean_node_modules(path)
        else:
            logger.error(f"Unknown npm resource type: {item_type}")
            return False

    def item_to_str(self, item: Dict[str, Any]) -> str:
        """
        Convert an npm resource to a string representation.
        
        Args:
            item: The npm resource
            
        Returns:
            String representation of the resource
        """
        item_type = item["type"]
        path = item["path"]
        size_mb = item.get("size_mb", 0)
        age_days = item.get("age_days", 0)
        
        if item_type == "npm_cache":
            return f"NPM Cache: {path} ({size_mb:.2f} MB, {age_days} days old)"
        elif item_type == "node_modules":
            last_access = item.get("last_access", "Unknown")
            return f"node_modules: {path} ({size_mb:.2f} MB, last access: {last_access})"
        else:
            return str(item)

    def _find_npm_cache_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find npm cache items older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of npm cache items to clean
        """
        if not os.path.exists(self.npm_cache_dir):
            logger.debug(f"NPM cache directory not found: {self.npm_cache_dir}")
            return []
        
        # Check cache stats
        cache_size = self._get_directory_size(self.npm_cache_dir)
        cache_size_mb = cache_size / (1024 * 1024)  # Convert to MB
        
        if cache_size_mb < 10:  # Skip if cache is less than 10MB
            logger.debug(f"NPM cache is small ({cache_size_mb:.2f} MB), skipping")
            return []
        
        # Get cache last modified time
        cache_mtime = os.path.getmtime(self.npm_cache_dir)
        cache_time = datetime.fromtimestamp(cache_mtime)
        age_days = (datetime.now() - cache_time).days
        
        if age_days < days_threshold:
            logger.debug(f"NPM cache is too recent ({age_days} days old), skipping")
            return []
        
        logger.debug(f"Found NPM cache: {self.npm_cache_dir} ({cache_size_mb:.2f} MB, {age_days} days old)")
        return [{
            "type": "npm_cache",
            "path": self.npm_cache_dir,
            "size_mb": cache_size_mb,
            "age_days": age_days,
            "last_modified": cache_time.strftime('%Y-%m-%d %H:%M:%S')
        }]

    def _find_node_modules_dirs(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find node_modules directories older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of node_modules directories to clean
        """
        logger.debug(f"Looking for node_modules directories not accessed in {days_threshold} days")
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        node_modules_dirs = []
        
        for scan_dir in self.scan_dirs:
            if not os.path.exists(scan_dir):
                logger.debug(f"Scan directory does not exist: {scan_dir}")
                continue
                
            logger.debug(f"Scanning {scan_dir} for node_modules directories...")
            
            try:
                for root, dirs, _ in os.walk(scan_dir, topdown=True):
                    # Skip excluded directories
                    dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
                    
                    # Calculate current depth
                    depth = root.count(os.sep) - scan_dir.count(os.sep)
                    if depth > self.max_depth:
                        # Skip deeper directories
                        dirs[:] = []
                        continue
                    
                    # Check if node_modules exists in this directory
                    node_modules_path = os.path.join(root, "node_modules")
                    if os.path.isdir(node_modules_path):
                        # Check if there's a package.json in parent directory
                        parent_package_json = os.path.join(root, "package.json")
                        if not os.path.isfile(parent_package_json):
                            logger.debug(f"Found orphaned node_modules: {node_modules_path}")
                            
                            # Get directory size and last access time
                            size = self._get_directory_size(node_modules_path)
                            size_mb = size / (1024 * 1024)  # Convert to MB
                            
                            # Only consider directories of substantial size
                            if size_mb < 5:  # Skip small node_modules
                                continue
                            
                            atime = os.path.getatime(node_modules_path)
                            last_access = datetime.fromtimestamp(atime)
                            
                            # Only include directories not accessed since threshold
                            if last_access < threshold_date:
                                logger.debug(f"Found unused node_modules: {node_modules_path} "
                                            f"({size_mb:.2f} MB, last access: {last_access.strftime('%Y-%m-%d')})")
                                
                                node_modules_dirs.append({
                                    "type": "node_modules",
                                    "path": node_modules_path,
                                    "size_mb": size_mb,
                                    "last_access": last_access.strftime('%Y-%m-%d %H:%M:%S'),
                                    "age_days": (datetime.now() - last_access).days
                                })
            except (PermissionError, OSError) as e:
                logger.warning(f"Error scanning {scan_dir}: {e}")
                continue
        
        return node_modules_dirs

    def _clean_npm_cache(self, force: bool = False) -> bool:
        """
        Clean npm cache using npm cache clean command.
        
        Args:
            force: Whether to force the clean operation
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        logger.info("Cleaning npm cache")
        
        # Use npm's built-in cache clean command
        force_flag = "--force" if force else ""
        cmd = f"npm cache clean {force_flag}"
        
        result = run_command(cmd, timeout=60)
        if result is None:
            logger.error("Failed to clean npm cache")
            return False
            
        logger.info("Successfully cleaned npm cache")
        return True

    def _clean_node_modules(self, path: str) -> bool:
        """
        Clean a node_modules directory by removing it.
        
        Args:
            path: Path to the node_modules directory
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        if not os.path.exists(path):
            logger.warning(f"node_modules directory not found: {path}")
            return False
            
        logger.info(f"Removing node_modules directory: {path}")
        
        try:
            shutil.rmtree(path)
            logger.info(f"Successfully removed {path}")
            return True
        except (PermissionError, OSError) as e:
            logger.error(f"Error removing {path}: {e}")
            return False

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
        Clean npm caches and unused node_modules directories.
        
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
        
        # Initialize default scan dirs with current directory
        self.scan_dirs = [self.current_dir]
        
        # Check for repo argument
        if args:
            repo_index = -1
            for i, arg in enumerate(args):
                if arg == '--repo' and i < len(args) - 1:
                    repo_index = i
                    break
            
            if repo_index >= 0:
                repo_path = args[repo_index + 1]
                if os.path.isdir(repo_path):
                    logger.info(f"Using target repository: {repo_path}")
                    # Replace current directory with specified repo
                    self.scan_dirs = [repo_path]
                else:
                    logger.error(f"Specified repository path does not exist: {repo_path}")
                    return False
        
        logger.info(f"Will scan the following directories for node_modules: {self.scan_dirs}")
        
        # Continue with regular cleaning process
        return super().clean(days_threshold, dry_run)


# Register this cleaner
CLEANER_REGISTRY["npm"] = NPMCleaner 