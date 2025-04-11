"""Python cleaner implementation for cleaning Python caches and virtual environments."""

import logging
import os
import shutil
import re
import time
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from pathlib import Path

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import run_command
from maccleaner.cleaners import CLEANER_REGISTRY

logger = logging.getLogger("maccleaner.cleaners.python")


class PythonCleaner(Cleaner):
    """Cleaner for Python caches, __pycache__ directories, and unused virtual environments."""

    def __init__(self):
        """Initialize the Python cleaner."""
        self.home_dir = os.path.expanduser("~")
        
        # Python cache directories
        self.pip_cache_dir = os.path.join(self.home_dir, ".cache/pip")
        
        # Virtual environment dirs to scan
        self.venv_possible_dirs = [
            self.home_dir,
            os.path.join(self.home_dir, "projects"),
            os.path.join(self.home_dir, "work"),
            os.path.join(self.home_dir, "dev"),
            "/tmp"
        ]
        
        # Common venv directory names
        self.venv_dir_names = {
            "venv", "env", ".venv", ".env", ".virtualenv", 
            "virtualenv", "pyenv", ".pyenv"
        }
        
        # Maximum depth to search for virtual environments and __pycache__
        self.max_depth = 8
        
        # Directories to exclude from scanning
        self.exclude_dirs = {
            "Library",
            "Movies",
            "Music",
            "Pictures",
            "Applications",
            ".Trash",
            "node_modules",
            "site-packages"  # Don't scan site-packages for __pycache__
        }

    @property
    def name(self) -> str:
        return "python"

    @property
    def description(self) -> str:
        return "Cleans Python caches, __pycache__ directories, and old virtual environments"

    def display_help(self) -> None:
        """Display detailed help information for the Python cleaner."""
        help_text = """
Python Cleaner Help
=================

The Python cleaner is a tool to clean Python-related resources, helping you
reclaim disk space. It can identify and remove:

1. Pip caches - Package cache files stored in ~/.cache/pip
2. __pycache__ directories - Compiled Python bytecode files
3. Virtual environments - Unused Python virtual environments

USAGE:
    maccleaner clean python [OPTIONS]

OPTIONS:
    --days DAYS     Number of days of inactivity before considering a resource unused
                    (default: 30)
    --dry-run       Only simulate cleaning without actually removing files
    -h, --help      Display this help message

EXAMPLES:
    # List all cleanable Python resources (simulation mode)
    maccleaner clean python --dry-run

    # Clean all unused Python resources older than 30 days
    maccleaner clean python

    # Clean unused Python resources older than 90 days
    maccleaner clean python --days 90

IMPORTANT NOTES:
    - The cleaner scans common directories for virtual environments (venv, .venv, etc.)
    - Active projects with recent access will have their virtual environments preserved
    - Virtual environments are identified by the presence of bin/python or Scripts/python.exe
    - Only substantial __pycache__ directories (>0.5MB) will be considered for removal
"""
        print(help_text)

    def check_prerequisites(self) -> bool:
        """Check if Python is installed and accessible."""
        logger.info("Checking Python installation...")
        
        python_check = run_command("python --version", timeout=10)
        if not python_check:
            # Try python3
            python_check = run_command("python3 --version", timeout=10)
            if not python_check:
                logger.error("Python is not installed or not available in PATH")
                return False
        
        logger.info(f"Python detected: {python_check.strip()}")
        
        # Check if pip is available
        pip_check = run_command("pip --version", timeout=10)
        if not pip_check:
            # Try pip3
            pip_check = run_command("pip3 --version", timeout=10)
            if not pip_check:
                logger.warning("pip is not installed or not available in PATH")
                # We won't return False here, as we can still clean __pycache__ without pip
        else:
            logger.info(f"pip detected: {pip_check.strip()}")
        
        return True

    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find Python caches, __pycache__ directories, and virtual environments.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
            
        Returns:
            List of Python caches and virtual environments with metadata
        """
        logger.info(f"Searching for Python caches and unused environments older than {days_threshold} days")
        
        cleanable_items = []
        
        # Find pip cache
        pip_cache_items = self._find_pip_cache(days_threshold)
        if pip_cache_items:
            logger.info(f"Found {len(pip_cache_items)} pip cache items to clean")
            cleanable_items.extend(pip_cache_items)
        
        # Find __pycache__ directories
        pycache_items = self._find_pycache_dirs(days_threshold)
        if pycache_items:
            logger.info(f"Found {len(pycache_items)} __pycache__ directories to clean")
            cleanable_items.extend(pycache_items)
        
        # Find unused virtual environments
        venv_items = self._find_virtual_envs(days_threshold)
        if venv_items:
            logger.info(f"Found {len(venv_items)} unused virtual environments to clean")
            cleanable_items.extend(venv_items)
        
        logger.info(f"Found total of {len(cleanable_items)} Python-related items to clean")
        return cleanable_items

    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific Python resource.
        
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
            size_mb = item.get("size_mb", 0)
            logger.debug(f"[DRY RUN] Would remove {item_type}: {path} ({size_mb:.2f} MB)")
            return True
        
        logger.info(f"Removing {item_type}: {path}")
        
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            logger.info(f"Successfully removed {path}")
            return True
        except (PermissionError, OSError) as e:
            logger.error(f"Error removing {path}: {e}")
            return False

    def item_to_str(self, item: Dict[str, Any]) -> str:
        """
        Convert a Python resource to a string representation.
        
        Args:
            item: The Python resource
            
        Returns:
            String representation of the resource
        """
        item_type = item["type"]
        path = item["path"]
        size_mb = item.get("size_mb", 0)
        age_days = item.get("age_days", 0)
        
        if item_type == "pip_cache":
            return f"Pip cache: {os.path.basename(path)} ({size_mb:.2f} MB, {age_days} days old)"
        elif item_type == "pycache":
            parent_dir = os.path.dirname(path)
            return f"__pycache__: {parent_dir} ({size_mb:.2f} MB, {age_days} days old)"
        elif item_type == "venv":
            last_access = item.get("last_access", "Unknown")
            return f"Virtual environment: {path} ({size_mb:.2f} MB, last access: {last_access})"
        else:
            return str(item)

    def _find_pip_cache(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find pip cache directories older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of pip cache directories to clean
        """
        if not os.path.exists(self.pip_cache_dir):
            logger.debug(f"Pip cache directory not found: {self.pip_cache_dir}")
            return []
            
        logger.debug(f"Checking pip cache in {self.pip_cache_dir}")
        cache_items = []
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        
        # Check wheels, http, and other subdirectories
        try:
            for cache_type in ["wheels", "http"]:
                cache_type_dir = os.path.join(self.pip_cache_dir, cache_type)
                
                if not os.path.exists(cache_type_dir):
                    continue
                
                # Get directory stats
                mtime = os.path.getmtime(cache_type_dir)
                mod_time = datetime.fromtimestamp(mtime)
                age_days = (datetime.now() - mod_time).days
                
                if age_days < days_threshold:
                    logger.debug(f"Pip {cache_type} cache is too recent ({age_days} days old), skipping")
                    continue
                
                # Get directory size
                size = self._get_directory_size(cache_type_dir)
                size_mb = size / (1024 * 1024)  # Convert to MB
                
                if size_mb < 5:  # Skip if cache is less than 5MB
                    logger.debug(f"Pip {cache_type} cache is small ({size_mb:.2f} MB), skipping")
                    continue
                
                logger.debug(f"Found pip {cache_type} cache: {cache_type_dir} ({size_mb:.2f} MB, {age_days} days old)")
                cache_items.append({
                    "type": "pip_cache",
                    "path": cache_type_dir,
                    "size_mb": size_mb,
                    "age_days": age_days,
                    "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                })
        except (PermissionError, OSError) as e:
            logger.warning(f"Error scanning pip cache directory: {e}")
            
        return cache_items

    def _find_pycache_dirs(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find __pycache__ directories older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of __pycache__ directories to clean
        """
        logger.debug(f"Looking for __pycache__ directories not accessed in {days_threshold} days")
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        pycache_dirs = []
        
        for scan_dir in self.venv_possible_dirs:
            if not os.path.exists(scan_dir):
                logger.debug(f"Scan directory does not exist: {scan_dir}")
                continue
                
            logger.debug(f"Scanning {scan_dir} for __pycache__ directories...")
            
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
                    
                    # Check for __pycache__ directory
                    if "__pycache__" in dirs:
                        pycache_path = os.path.join(root, "__pycache__")
                        
                        # Get directory stats
                        mtime = os.path.getmtime(pycache_path)
                        mod_time = datetime.fromtimestamp(mtime)
                        age_days = (datetime.now() - mod_time).days
                        
                        if age_days < days_threshold:
                            logger.debug(f"__pycache__ is too recent: {pycache_path} ({age_days} days old)")
                            continue
                        
                        # Get directory size
                        size = self._get_directory_size(pycache_path)
                        size_mb = size / (1024 * 1024)  # Convert to MB
                        
                        # Only consider directories of substantial size to avoid log spam
                        if size_mb < 0.5:  # Skip small __pycache__ dirs
                            continue
                        
                        logger.debug(f"Found old __pycache__: {pycache_path} ({size_mb:.2f} MB, {age_days} days old)")
                        pycache_dirs.append({
                            "type": "pycache",
                            "path": pycache_path,
                            "size_mb": size_mb,
                            "age_days": age_days,
                            "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                        })
            except (PermissionError, OSError) as e:
                logger.warning(f"Error scanning {scan_dir} for __pycache__: {e}")
                continue
        
        return pycache_dirs

    def _find_virtual_envs(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find unused virtual environments older than the threshold.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of virtual environments to clean
        """
        logger.debug(f"Looking for virtual environments not accessed in {days_threshold} days")
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        venv_dirs = []
        
        for scan_dir in self.venv_possible_dirs:
            if not os.path.exists(scan_dir):
                logger.debug(f"Scan directory does not exist: {scan_dir}")
                continue
                
            logger.debug(f"Scanning {scan_dir} for virtual environments...")
            
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
                    
                    # Check for common virtual environment directory names
                    for venv_name in self.venv_dir_names.intersection(set(dirs)):
                        venv_path = os.path.join(root, venv_name)
                        
                        # Verify it's actually a virtual environment
                        if not os.path.exists(os.path.join(venv_path, "bin", "python")) and \
                           not os.path.exists(os.path.join(venv_path, "Scripts", "python.exe")):
                            continue
                        
                        # Look for a parent requirements.txt or pyproject.toml
                        parent_dir = root
                        has_project_file = False
                        
                        for _ in range(2):  # Check current directory and one level up
                            if os.path.exists(os.path.join(parent_dir, "requirements.txt")) or \
                               os.path.exists(os.path.join(parent_dir, "pyproject.toml")) or \
                               os.path.exists(os.path.join(parent_dir, "setup.py")):
                                has_project_file = True
                                break
                            parent_dir = os.path.dirname(parent_dir)
                        
                        # Skip environments with active projects unless they're very old
                        if has_project_file:
                            # Get directory stats
                            atime = os.path.getatime(venv_path)
                            last_access = datetime.fromtimestamp(atime)
                            access_age_days = (datetime.now() - last_access).days
                            
                            # Skip if accessed within threshold * 3 (more conservative with active projects)
                            if access_age_days < days_threshold * 3:
                                logger.debug(f"Virtual environment has active project and was accessed recently: "
                                           f"{venv_path} ({access_age_days} days ago)")
                                continue
                        
                        # Get directory stats
                        atime = os.path.getatime(venv_path)
                        last_access = datetime.fromtimestamp(atime)
                        access_age_days = (datetime.now() - last_access).days
                        
                        # Skip if accessed within threshold
                        if access_age_days < days_threshold:
                            logger.debug(f"Virtual environment accessed recently: {venv_path} ({access_age_days} days ago)")
                            continue
                        
                        # Get directory size
                        size = self._get_directory_size(venv_path)
                        size_mb = size / (1024 * 1024)  # Convert to MB
                        
                        # Only consider directories of substantial size
                        if size_mb < 10:  # Skip small environments
                            continue
                        
                        logger.debug(f"Found unused virtual environment: {venv_path} "
                                    f"({size_mb:.2f} MB, last access: {last_access.strftime('%Y-%m-%d')})")
                        venv_dirs.append({
                            "type": "venv",
                            "path": venv_path,
                            "size_mb": size_mb,
                            "age_days": access_age_days,
                            "last_access": last_access.strftime('%Y-%m-%d %H:%M:%S'),
                            "has_project": has_project_file
                        })
            except (PermissionError, OSError) as e:
                logger.warning(f"Error scanning {scan_dir} for virtual environments: {e}")
                continue
        
        return venv_dirs

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
        Clean Python caches, __pycache__ directories, and virtual environments.
        
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
CLEANER_REGISTRY["python"] = PythonCleaner 