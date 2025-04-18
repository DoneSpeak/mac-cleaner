"""iOS Simulator cleaner implementation for cleaning old simulator devices and runtimes."""

import json
import logging
import os
import plistlib
import shutil
import subprocess
import time
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from pathlib import Path

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import run_command
from maccleaner.cleaners import CLEANER_REGISTRY

logger = logging.getLogger("maccleaner.cleaners.simulator")


class IOSSimulatorCleaner(Cleaner):
    """Cleaner for iOS simulator devices, runtimes, and caches."""

    def __init__(self):
        """Initialize the iOS simulator cleaner."""
        self.home_dir = os.path.expanduser("~")
        self.library_dir = os.path.join(self.home_dir, "Library")
        
        # Simulator directories
        self.simulator_dir = os.path.join(self.library_dir, "Developer/CoreSimulator")
        self.devices_dir = os.path.join(self.simulator_dir, "Devices")
        self.device_sets_dir = os.path.join(self.simulator_dir, "Device Sets")
        
        # Simulator cache directories
        self.simulator_cache_dir = os.path.join(self.library_dir, "Caches/com.apple.CoreSimulator")
        
        # Simulator logs directories
        self.sim_logs_dir = os.path.join(self.library_dir, "Logs/CoreSimulator")
        
        # Simulator runtime cache
        self.sim_runtime_cache_dir = os.path.join(
            self.library_dir, "Developer/CoreSimulator/Caches/dyld"
        )

    @property
    def name(self) -> str:
        return "simulator"

    @property
    def description(self) -> str:
        return "Cleans unused iOS simulator devices, old runtimes, and caches"

    def display_help(self) -> None:
        """Display detailed help information for the iOS Simulator cleaner."""
        help_text = """
iOS Simulator Cleaner Help
=========================

The iOS Simulator cleaner is a tool to clean unused simulator resources, helping you
reclaim disk space. It can identify and remove:

1. Unused simulator devices - Simulator devices that haven't been used in a while
2. Simulator caches - Cache directories used by the iOS simulator
3. Simulator logs - Old log files generated by the simulator

USAGE:
    maccleaner clean simulator [OPTIONS]

OPTIONS:
    --days DAYS     Number of days of inactivity before considering a resource unused
                    (default: 30)
    --dry-run       Only simulate cleaning without actually removing files
    -h, --help      Display this help message

EXAMPLES:
    # List all cleanable simulator resources (simulation mode)
    maccleaner clean simulator --dry-run

    # Clean all unused simulator resources older than 30 days
    maccleaner clean simulator

    # Clean unused simulator resources older than 90 days
    maccleaner clean simulator --days 90

IMPORTANT NOTES:
    - The cleaner will not remove booted (currently running) simulator devices
    - Device directories of substantial size (>50MB) will be prioritized for cleaning
    - Cache directories that are too small to be worth cleaning will be skipped
    - For iOS devices, the cleaner uses 'xcrun simctl erase' to safely clean devices
"""
        print(help_text)

    def check_prerequisites(self) -> bool:
        """Check if Xcode and the iOS simulator are installed."""
        logger.info("Checking if Xcode and iOS simulator are installed...")
        
        # Check if simctl is available (part of Xcode's command line tools)
        simctl_check = run_command("xcrun simctl list", timeout=10)
        if not simctl_check:
            logger.error("iOS simulator not found, ensure Xcode is installed")
            return False
        
        # Check if we are on macOS
        platform_check = run_command("uname", timeout=5)
        if platform_check and platform_check.strip() != "Darwin":
            logger.error(f"Not running on macOS (detected: {platform_check.strip()})")
            return False
        
        # Check if the simulator directory exists
        if not os.path.exists(self.simulator_dir):
            logger.error(f"iOS simulator directory not found: {self.simulator_dir}")
            return False
            
        logger.info("iOS simulator detected")
        return True

    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find unused iOS simulator devices, old runtimes, and caches.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
            
        Returns:
            List of simulator resources with metadata
        """
        logger.info(f"Searching for unused iOS simulator resources older than {days_threshold} days")
        
        cleanable_items = []
        
        # Find unused simulator devices
        device_items = self._find_unused_devices(days_threshold)
        if device_items:
            logger.info(f"Found {len(device_items)} unused simulator devices to clean")
            cleanable_items.extend(device_items)
        
        # Find simulator caches
        cache_items = self._find_simulator_caches(days_threshold)
        if cache_items:
            logger.info(f"Found {len(cache_items)} simulator cache directories to clean")
            cleanable_items.extend(cache_items)
        
        # Find old simulator logs
        log_items = self._find_simulator_logs(days_threshold)
        if log_items:
            logger.info(f"Found {len(log_items)} old simulator log directories to clean")
            cleanable_items.extend(log_items)
        
        logger.info(f"Found total of {len(cleanable_items)} iOS simulator resources to clean")
        return cleanable_items

    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific iOS simulator resource.
        
        Args:
            item: The resource to clean
            dry_run: If True, only simulate cleaning
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        item_type = item["type"]
        
        if dry_run:
            size_mb = item.get("size_mb", 0)
            if item_type == "device":
                logger.debug(f"[DRY RUN] Would erase simulator device: {item['name']} "
                            f"({item['udid']}, {size_mb:.2f} MB)")
            elif item_type in ["cache", "log"]:
                logger.debug(f"[DRY RUN] Would remove {item_type}: {item['path']} ({size_mb:.2f} MB)")
            return True
        
        if item_type == "device":
            return self._erase_simulator_device(item["udid"])
        elif item_type in ["cache", "log"]:
            return self._remove_directory(item["path"])
        else:
            logger.error(f"Unknown simulator resource type: {item_type}")
            return False

    def item_to_str(self, item: Dict[str, Any]) -> str:
        """
        Convert an iOS simulator resource to a string representation.
        
        Args:
            item: The simulator resource
            
        Returns:
            String representation of the resource
        """
        item_type = item["type"]
        size_mb = item.get("size_mb", 0)
        age_days = item.get("age_days", 0)
        
        if item_type == "device":
            return f"Simulator device: {item['name']} ({item['runtime']}, {size_mb:.2f} MB, {age_days} days old)"
        elif item_type == "cache":
            return f"Simulator cache: {os.path.basename(item['path'])} ({size_mb:.2f} MB, {age_days} days old)"
        elif item_type == "log":
            return f"Simulator log: {os.path.basename(item['path'])} ({size_mb:.2f} MB, {age_days} days old)"
        else:
            return str(item)

    def _find_unused_devices(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find unused iOS simulator devices.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of unused simulator devices with metadata
        """
        logger.debug("Looking for unused iOS simulator devices")
        
        # Get list of devices using simctl
        cmd = "xcrun simctl list devices -j"
        output = run_command(cmd, timeout=20)
        
        if not output:
            logger.warning("No simulator devices found or simctl command failed")
            return []
        
        try:
            # Parse JSON output
            devices_data = json.loads(output)
            device_items = []
            threshold_date = datetime.now() - timedelta(days=days_threshold)
            
            # Process each runtime's devices
            for runtime, devices in devices_data.get("devices", {}).items():
                for device in devices:
                    udid = device.get("udid", "")
                    state = device.get("state", "")
                    is_available = device.get("isAvailable", False)
                    name = device.get("name", "")
                    
                    # Skip devices that are in active use
                    if state == "Booted":
                        logger.debug(f"Skipping booted device: {name} ({udid})")
                        continue
                    
                    # Get device directory
                    device_dir = os.path.join(self.devices_dir, udid)
                    if not os.path.exists(device_dir):
                        logger.debug(f"Device directory not found for {name} ({udid})")
                        continue
                    
                    # Check last modified time
                    mtime = os.path.getmtime(device_dir)
                    mod_time = datetime.fromtimestamp(mtime)
                    age_days = (datetime.now() - mod_time).days
                    
                    if age_days < days_threshold:
                        logger.debug(f"Device is too recent: {name} ({age_days} days old)")
                        continue
                    
                    # Check last access time (more important for simulators)
                    atime = os.path.getatime(device_dir)
                    access_time = datetime.fromtimestamp(atime)
                    access_age_days = (datetime.now() - access_time).days
                    
                    if access_age_days < days_threshold:
                        logger.debug(f"Device was accessed recently: {name} ({access_age_days} days ago)")
                        continue
                    
                    # Get directory size
                    size = self._get_directory_size(device_dir)
                    size_mb = size / (1024 * 1024)  # Convert to MB
                    
                    # Only consider devices of substantial size
                    if size_mb < 50:  # Skip small devices
                        continue
                    
                    runtime_name = runtime.replace("com.apple.CoreSimulator.SimRuntime.", "")
                    logger.debug(f"Found unused device: {name} ({runtime_name}, {size_mb:.2f} MB, {age_days} days old)")
                    device_items.append({
                        "type": "device",
                        "udid": udid,
                        "name": name,
                        "runtime": runtime_name,
                        "state": state,
                        "path": device_dir,
                        "size_mb": size_mb,
                        "age_days": age_days,
                        "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S'),
                        "last_access": access_time.strftime('%Y-%m-%d %H:%M:%S')
                    })
            
            return device_items
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing simctl output: {e}")
            return []

    def _find_simulator_caches(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find old iOS simulator cache directories.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of simulator cache directories with metadata
        """
        logger.debug("Looking for old iOS simulator caches")
        cache_items = []
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        
        # Check main simulator cache directory
        cache_dirs = [
            self.simulator_cache_dir,
            self.sim_runtime_cache_dir
        ]
        
        for cache_dir in cache_dirs:
            if not os.path.exists(cache_dir):
                logger.debug(f"Cache directory not found: {cache_dir}")
                continue
            
            try:
                # Check if the cache is old enough
                mtime = os.path.getmtime(cache_dir)
                mod_time = datetime.fromtimestamp(mtime)
                age_days = (datetime.now() - mod_time).days
                
                if age_days < days_threshold:
                    logger.debug(f"Cache is too recent: {cache_dir} ({age_days} days old)")
                    continue
                
                # Get directory size
                size = self._get_directory_size(cache_dir)
                size_mb = size / (1024 * 1024)  # Convert to MB
                
                # Only consider caches of substantial size
                if size_mb < 20:  # Skip small caches
                    continue
                
                logger.debug(f"Found old simulator cache: {cache_dir} ({size_mb:.2f} MB, {age_days} days old)")
                cache_items.append({
                    "type": "cache",
                    "path": cache_dir,
                    "size_mb": size_mb,
                    "age_days": age_days,
                    "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                })
                
                # For dyld cache, also look for specific OS version cache subdirectories
                if cache_dir == self.sim_runtime_cache_dir:
                    for item in os.listdir(cache_dir):
                        item_path = os.path.join(cache_dir, item)
                        
                        if not os.path.isdir(item_path):
                            continue
                        
                        # Check if the cache is old enough
                        mtime = os.path.getmtime(item_path)
                        mod_time = datetime.fromtimestamp(mtime)
                        age_days = (datetime.now() - mod_time).days
                        
                        if age_days < days_threshold:
                            continue
                        
                        # Get directory size
                        size = self._get_directory_size(item_path)
                        size_mb = size / (1024 * 1024)  # Convert to MB
                        
                        # Only consider caches of substantial size
                        if size_mb < 20:  # Skip small caches
                            continue
                        
                        logger.debug(f"Found old runtime cache: {item_path} ({size_mb:.2f} MB, {age_days} days old)")
                        cache_items.append({
                            "type": "cache",
                            "path": item_path,
                            "size_mb": size_mb,
                            "age_days": age_days,
                            "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                        })
            except (PermissionError, OSError) as e:
                logger.warning(f"Error scanning cache directory {cache_dir}: {e}")
                continue
        
        return cache_items

    def _find_simulator_logs(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find old iOS simulator log directories.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of simulator log directories with metadata
        """
        logger.debug("Looking for old iOS simulator logs")
        log_items = []
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        
        if not os.path.exists(self.sim_logs_dir):
            logger.debug(f"Simulator logs directory not found: {self.sim_logs_dir}")
            return []
        
        try:
            # Check device-specific log directories
            for item in os.listdir(self.sim_logs_dir):
                item_path = os.path.join(self.sim_logs_dir, item)
                
                if not os.path.isdir(item_path):
                    continue
                
                # Check if the logs are old enough
                mtime = os.path.getmtime(item_path)
                mod_time = datetime.fromtimestamp(mtime)
                age_days = (datetime.now() - mod_time).days
                
                if age_days < days_threshold:
                    logger.debug(f"Logs are too recent: {item_path} ({age_days} days old)")
                    continue
                
                # Get directory size
                size = self._get_directory_size(item_path)
                size_mb = size / (1024 * 1024)  # Convert to MB
                
                # Only consider logs of substantial size
                if size_mb < 5:  # Skip small log directories
                    continue
                
                logger.debug(f"Found old simulator logs: {item_path} ({size_mb:.2f} MB, {age_days} days old)")
                log_items.append({
                    "type": "log",
                    "path": item_path,
                    "size_mb": size_mb,
                    "age_days": age_days,
                    "last_modified": mod_time.strftime('%Y-%m-%d %H:%M:%S')
                })
        except (PermissionError, OSError) as e:
            logger.warning(f"Error scanning logs directory: {e}")
        
        return log_items

    def _erase_simulator_device(self, udid: str) -> bool:
        """
        Erase a simulator device using simctl.
        
        Args:
            udid: The device UDID
            
        Returns:
            True if erase was successful, False otherwise
        """
        logger.info(f"Erasing simulator device: {udid}")
        
        # Use simctl to erase the device
        cmd = f"xcrun simctl erase {udid}"
        result = run_command(cmd, timeout=60)
        
        if result is None:
            logger.error(f"Failed to erase simulator device: {udid}")
            return False
            
        logger.info(f"Successfully erased simulator device: {udid}")
        return True

    def _remove_directory(self, path: str) -> bool:
        """
        Remove a directory.
        
        Args:
            path: Directory path
            
        Returns:
            True if removal was successful, False otherwise
        """
        if not os.path.exists(path):
            logger.warning(f"Directory not found: {path}")
            return False
            
        logger.info(f"Removing directory: {path}")
        
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
        Clean unused iOS simulator resources.
        
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
CLEANER_REGISTRY["simulator"] = IOSSimulatorCleaner 