"""Homebrew cleaner implementation for cleaning homebrew caches and old versions."""

import json
import logging
import os
import subprocess
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import run_command
from maccleaner.cleaners import CLEANER_REGISTRY

logger = logging.getLogger("maccleaner.cleaners.brew")


class HomebrewCleaner(Cleaner):
    """Cleaner for Homebrew caches and old versions."""

    def __init__(self):
        """Initialize the Homebrew cleaner."""
        self.home_dir = os.path.expanduser("~")
        
        # Homebrew directories
        self.homebrew_cache_dir = None
        self.homebrew_cellar_dir = None

    @property
    def name(self) -> str:
        return "brew"

    @property
    def description(self) -> str:
        return "Cleans Homebrew caches, downloads, and outdated package versions"

    def display_help(self) -> None:
        """Display detailed help information for the Homebrew cleaner."""
        help_text = """
Homebrew Cleaner Help
=====================

The Homebrew cleaner is a tool to clean unused Homebrew resources, helping you
reclaim disk space. It can clean:

1. Outdated packages - Upgrades packages that are not at the latest version
2. Old downloads - Removes old downloaded packages from Homebrew cache
3. Abandoned kegs - Removes old versions of installed formulae

USAGE:
    maccleaner clean brew [OPTIONS]

OPTIONS:
    --days DAYS     Number of days of inactivity before considering a resource unused
                    (default: 30)
    --dry-run       Only simulate cleaning without actually removing files
    -h, --help      Display this help message

EXAMPLES:
    # List all cleanable Homebrew resources (simulation mode)
    maccleaner clean brew --dry-run

    # Clean all unused Homebrew resources older than 30 days
    maccleaner clean brew

    # Clean unused Homebrew resources older than 90 days
    maccleaner clean brew --days 90

IMPORTANT NOTES:
    - The cleaner will automatically detect your Homebrew installation and its directories
    - Cleaning outdated packages will perform 'brew upgrade' on those packages
    - Old downloads are only removed if they are substantial in size (>1MB)
    - Abandoned kegs are old versions of formulae that are not currently linked
    - Protected resources will not be removed, even if specified
"""
        print(help_text)

    def clean(self, days_threshold: int = 30, dry_run: bool = True, args: Optional[List[str]] = None) -> bool:
        """
        Clean unused Homebrew resources.
        
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
        if not self.check_prerequisites():
            logger.error("Prerequisites not met, cannot clean Homebrew resources")
            return False
            
        try:
            cleanable_items = self.find_cleanable_items(days_threshold)
            
            if not cleanable_items:
                logger.info("No unused Homebrew resources found to clean")
                return True
                
            logger.info(f"Found {len(cleanable_items)} Homebrew resources to clean")
            
            if dry_run:
                logger.info("Running in dry-run mode, no files will be actually removed")
                
            # Group items by type for better display
            outdated_items = [item for item in cleanable_items if item["type"] == "outdated"]
            download_items = [item for item in cleanable_items if item["type"] == "download"]
            keg_items = [item for item in cleanable_items if item["type"] == "keg"]
            
            total_mb = 0
            success_count = 0
            
            # Process outdated packages
            if outdated_items:
                logger.info(f"Processing {len(outdated_items)} outdated packages:")
                for item in outdated_items:
                    item_str = self.item_to_str(item)
                    logger.info(f"  {item_str}")
                    
                    if self.clean_item(item, dry_run):
                        success_count += 1
            
            # Process old downloads
            if download_items:
                download_size_mb = sum(item.get("size_mb", 0) for item in download_items)
                total_mb += download_size_mb
                logger.info(f"Processing {len(download_items)} old downloads ({download_size_mb:.2f} MB):")
                
                for item in download_items:
                    item_str = self.item_to_str(item)
                    logger.info(f"  {item_str}")
                    
                    if self.clean_item(item, dry_run):
                        success_count += 1
            
            # Process abandoned kegs
            if keg_items:
                keg_size_mb = sum(item.get("size_mb", 0) for item in keg_items)
                total_mb += keg_size_mb
                logger.info(f"Processing {len(keg_items)} abandoned kegs ({keg_size_mb:.2f} MB):")
                
                for item in keg_items:
                    item_str = self.item_to_str(item)
                    logger.info(f"  {item_str}")
                    
                    if self.clean_item(item, dry_run):
                        success_count += 1
            
            logger.info(f"Homebrew cleaning {'simulation ' if dry_run else ''}completed")
            if not dry_run:
                logger.info(f"Successfully cleaned {success_count}/{len(cleanable_items)} items")
                logger.info(f"Recovered approximately {total_mb:.2f} MB of disk space")
            
            return True
        except Exception as e:
            logger.error(f"Error cleaning Homebrew resources: {e}")
            logger.debug("Exception details:", exc_info=True)
            return False

    def check_prerequisites(self) -> bool:
        """Check if Homebrew is installed and accessible."""
        logger.info("Checking Homebrew installation...")
        
        # Check if brew is installed
        brew_check = run_command("brew --version", timeout=10)
        if not brew_check:
            logger.error("Homebrew is not installed or not available in PATH")
            return False
        
        logger.info(f"Homebrew detected: {brew_check.split()[0]} {brew_check.split()[1]}")
        
        # Get Homebrew cache directory
        cache_cmd = "brew --cache"
        cache_dir = run_command(cache_cmd, timeout=10)
        if not cache_dir:
            logger.error("Could not determine Homebrew cache directory")
            return False
        
        self.homebrew_cache_dir = cache_dir.strip()
        logger.info(f"Homebrew cache directory: {self.homebrew_cache_dir}")
        
        # Get Homebrew cellar directory
        cellar_cmd = "brew --cellar"
        cellar_dir = run_command(cellar_cmd, timeout=10)
        if not cellar_dir:
            logger.error("Could not determine Homebrew cellar directory")
            return False
            
        self.homebrew_cellar_dir = cellar_dir.strip()
        logger.info(f"Homebrew cellar directory: {self.homebrew_cellar_dir}")
        
        return True

    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find Homebrew caches and old versions that can be cleaned.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
            
        Returns:
            List of Homebrew caches and old versions with metadata
        """
        logger.info(f"Searching for unused Homebrew resources older than {days_threshold} days")
        
        cleanable_items = []
        
        # Find outdated packages
        outdated_items = self._find_outdated_packages()
        if outdated_items:
            logger.info(f"Found {len(outdated_items)} outdated Homebrew packages")
            cleanable_items.extend(outdated_items)
        
        # Find old downloads in Homebrew cache
        download_items = self._find_old_downloads(days_threshold)
        if download_items:
            logger.info(f"Found {len(download_items)} old downloads in Homebrew cache")
            cleanable_items.extend(download_items)
        
        # Find abandoned kegs (old versions)
        keg_items = self._find_abandoned_kegs(days_threshold)
        if keg_items:
            logger.info(f"Found {len(keg_items)} abandoned Homebrew kegs")
            cleanable_items.extend(keg_items)
        
        logger.info(f"Found total of {len(cleanable_items)} Homebrew items to clean")
        return cleanable_items

    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific Homebrew resource.
        
        Args:
            item: The resource to clean
            dry_run: If True, only simulate cleaning
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        item_type = item["type"]
        
        if dry_run:
            if item_type == "outdated":
                logger.debug(f"[DRY RUN] Would upgrade outdated package: {item['name']} "
                            f"(current: {item['installed_version']}, latest: {item['latest_version']})")
            elif item_type == "download":
                logger.debug(f"[DRY RUN] Would remove download: {item['path']} ({item['size_mb']:.2f} MB)")
            elif item_type == "keg":
                logger.debug(f"[DRY RUN] Would remove old keg: {item['formula']} {item['version']} "
                            f"({item['size_mb']:.2f} MB)")
            return True
        
        if item_type == "outdated":
            return self._upgrade_formula(item["name"])
        elif item_type == "download":
            return self._remove_download(item["path"])
        elif item_type == "keg":
            return self._remove_keg(item["formula"], item["version"])
        else:
            logger.error(f"Unknown Homebrew resource type: {item_type}")
            return False

    def item_to_str(self, item: Dict[str, Any]) -> str:
        """
        Convert a Homebrew resource to a string representation.
        
        Args:
            item: The Homebrew resource
            
        Returns:
            String representation of the resource
        """
        item_type = item["type"]
        
        if item_type == "outdated":
            return (f"Outdated package: {item['name']} "
                   f"(current: {item['installed_version']}, latest: {item['latest_version']})")
        elif item_type == "download":
            size_mb = item.get("size_mb", 0)
            age_days = item.get("age_days", 0)
            return f"Download: {os.path.basename(item['path'])} ({size_mb:.2f} MB, {age_days} days old)"
        elif item_type == "keg":
            size_mb = item.get("size_mb", 0)
            return f"Old keg: {item['formula']} {item['version']} ({size_mb:.2f} MB)"
        else:
            return str(item)

    def _find_outdated_packages(self) -> List[Dict[str, Any]]:
        """
        Find outdated packages that can be upgraded.
        
        Returns:
            List of outdated packages with metadata
        """
        logger.debug("Looking for outdated Homebrew packages")
        
        # Get outdated packages in JSON format
        cmd = "brew outdated --json=v2"
        output = run_command(cmd, timeout=30)
        
        if not output:
            logger.warning("No outdated packages found or brew command failed")
            return []
        
        try:
            outdated_data = json.loads(output)
            formulae = outdated_data.get("formulae", [])
            casks = outdated_data.get("casks", [])
            
            outdated_items = []
            
            # Process outdated formulae
            for formula in formulae:
                name = formula.get("name", "")
                installed_versions = formula.get("installed_versions", [])
                current_version = installed_versions[0] if installed_versions else "Unknown"
                latest_version = formula.get("current_version", "Unknown")
                
                logger.debug(f"Found outdated formula: {name} (current: {current_version}, latest: {latest_version})")
                outdated_items.append({
                    "type": "outdated",
                    "name": name,
                    "installed_version": current_version,
                    "latest_version": latest_version,
                    "is_formula": True
                })
            
            # Process outdated casks
            for cask in casks:
                name = cask.get("name", "")
                installed_version = cask.get("installed_versions", ["Unknown"])[0]
                latest_version = cask.get("current_version", "Unknown")
                
                logger.debug(f"Found outdated cask: {name} (current: {installed_version}, latest: {latest_version})")
                outdated_items.append({
                    "type": "outdated",
                    "name": name,
                    "installed_version": installed_version,
                    "latest_version": latest_version,
                    "is_formula": False
                })
            
            return outdated_items
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing brew outdated output: {e}")
            return []

    def _find_old_downloads(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find old downloads in Homebrew cache.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of old downloads with metadata
        """
        if not self.homebrew_cache_dir or not os.path.exists(self.homebrew_cache_dir):
            logger.warning(f"Homebrew cache directory not found: {self.homebrew_cache_dir}")
            return []
            
        logger.debug(f"Looking for old downloads in {self.homebrew_cache_dir}")
        download_items = []
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        
        # Find .bottle files and other downloads
        try:
            for filename in os.listdir(self.homebrew_cache_dir):
                file_path = os.path.join(self.homebrew_cache_dir, filename)
                
                if not os.path.isfile(file_path):
                    continue
                
                # Get file stats
                mtime = os.path.getmtime(file_path)
                mod_time = datetime.fromtimestamp(mtime)
                age_days = (datetime.now() - mod_time).days
                
                if age_days < days_threshold:
                    continue
                
                # Get file size
                size = os.path.getsize(file_path)
                size_mb = size / (1024 * 1024)  # Convert to MB
                
                # Only consider files of substantial size
                if size_mb < 1:  # Skip files smaller than 1MB
                    continue
                
                logger.debug(f"Found old download: {filename} ({size_mb:.2f} MB, {age_days} days old)")
                download_items.append({
                    "type": "download",
                    "path": file_path,
                    "size_mb": size_mb,
                    "age_days": age_days,
                    "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                })
        except (PermissionError, OSError) as e:
            logger.warning(f"Error scanning Homebrew cache directory: {e}")
            
        return download_items

    def _find_abandoned_kegs(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find abandoned kegs (old versions) in Homebrew cellar.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of abandoned kegs with metadata
        """
        if not self.homebrew_cellar_dir or not os.path.exists(self.homebrew_cellar_dir):
            logger.warning(f"Homebrew cellar directory not found: {self.homebrew_cellar_dir}")
            return []
            
        logger.debug(f"Looking for abandoned kegs in {self.homebrew_cellar_dir}")
        keg_items = []
        
        # Get list of installed formulae
        try:
            # Check each formula directory
            for formula in os.listdir(self.homebrew_cellar_dir):
                formula_dir = os.path.join(self.homebrew_cellar_dir, formula)
                
                if not os.path.isdir(formula_dir):
                    continue
                
                # Get list of versions for this formula
                versions = os.listdir(formula_dir)
                
                # Skip if there's only one version
                if len(versions) <= 1:
                    continue
                
                # Find linked version (current version)
                linked_version = None
                cmd = f"brew info --json=v2 {formula}"
                output = run_command(cmd, timeout=15)
                
                if output:
                    try:
                        info_data = json.loads(output)
                        formulae = info_data.get("formulae", [])
                        if formulae:
                            linked_keg = formulae[0].get("linked_keg")
                            if linked_keg:
                                linked_version = linked_keg
                    except (json.JSONDecodeError, IndexError):
                        pass
                
                # Process each version
                for version in versions:
                    version_dir = os.path.join(formula_dir, version)
                    
                    # Skip the linked version
                    if version == linked_version:
                        continue
                    
                    # Get directory stats
                    mtime = os.path.getmtime(version_dir)
                    mod_time = datetime.fromtimestamp(mtime)
                    age_days = (datetime.now() - mod_time).days
                    
                    # Skip if not old enough
                    if age_days < days_threshold:
                        continue
                    
                    # Get directory size
                    size = self._get_directory_size(version_dir)
                    size_mb = size / (1024 * 1024)  # Convert to MB
                    
                    # Only consider directories of substantial size
                    if size_mb < 5:  # Skip small kegs
                        continue
                    
                    logger.debug(f"Found abandoned keg: {formula} {version} ({size_mb:.2f} MB, {age_days} days old)")
                    keg_items.append({
                        "type": "keg",
                        "formula": formula,
                        "version": version,
                        "path": version_dir,
                        "size_mb": size_mb,
                        "age_days": age_days,
                        "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                    })
        except (PermissionError, OSError) as e:
            logger.warning(f"Error scanning Homebrew cellar directory: {e}")
            
        return keg_items

    def _upgrade_formula(self, formula: str) -> bool:
        """
        Upgrade a Homebrew formula or cask.
        
        Args:
            formula: The formula or cask to upgrade
            
        Returns:
            True if upgrade was successful, False otherwise
        """
        logger.info(f"Upgrading {formula}")
        
        # Check if it's a cask
        cmd = f"brew info --json=v2 {formula}"
        output = run_command(cmd, timeout=15)
        is_cask = False
        
        if output:
            try:
                info_data = json.loads(output)
                if info_data.get("casks"):
                    is_cask = True
            except json.JSONDecodeError:
                pass
        
        # Run appropriate upgrade command
        upgrade_cmd = f"brew upgrade {'--cask ' if is_cask else ''}{formula}"
        result = run_command(upgrade_cmd, timeout=300)  # Allow up to 5 minutes for upgrade
        
        if result is None:
            logger.error(f"Failed to upgrade {formula}")
            return False
            
        logger.info(f"Successfully upgraded {formula}")
        return True

    def _remove_download(self, path: str) -> bool:
        """
        Remove a download file from Homebrew cache.
        
        Args:
            path: Path to the download file
            
        Returns:
            True if removal was successful, False otherwise
        """
        if not os.path.exists(path):
            logger.warning(f"Download file not found: {path}")
            return False
            
        logger.info(f"Removing download: {path}")
        
        try:
            os.remove(path)
            logger.info(f"Successfully removed {path}")
            return True
        except (PermissionError, OSError) as e:
            logger.error(f"Error removing {path}: {e}")
            return False

    def _remove_keg(self, formula: str, version: str) -> bool:
        """
        Remove a specific version of a Homebrew formula.
        
        Args:
            formula: The formula name
            version: The version to remove
            
        Returns:
            True if removal was successful, False otherwise
        """
        logger.info(f"Removing old keg: {formula} {version}")
        
        # Run brew cleanup with specific version
        cmd = f"brew cleanup {formula} --prune={version}"
        result = run_command(cmd, timeout=60)
        
        if result is None:
            logger.error(f"Failed to remove keg: {formula} {version}")
            return False
            
        logger.info(f"Successfully removed keg: {formula} {version}")
        return True

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


# Register this cleaner
CLEANER_REGISTRY["brew"] = HomebrewCleaner 