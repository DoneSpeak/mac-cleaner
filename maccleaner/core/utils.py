"""Utility functions for the MacCleaner application."""

import os
import logging
import subprocess
import time
import inspect
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union

logger = logging.getLogger("maccleaner.utils")


def run_command(command: str, cwd: Optional[str] = None, timeout: int = 30) -> Optional[str]:
    """
    Run a shell command and return the output.
    
    Args:
        command: The command to run
        cwd: The working directory to run the command in
        timeout: Timeout in seconds for the command (default: 30)
        
    Returns:
        The command output as a string, or None if the command failed
    """
    line = inspect.currentframe().f_lineno
    logger.debug(f"[Line {line}] Running command: {command} in directory: {cwd or os.getcwd()}")
    
    start_time = time.time()
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            shell=True,
            cwd=cwd,
            timeout=timeout
        )
        execution_time = time.time() - start_time
        logger.debug(f"[Line {line}] Command completed in {execution_time:.2f} seconds")
        return result.stdout.strip()
    except subprocess.TimeoutExpired as e:
        line = inspect.currentframe().f_lineno
        logger.error(f"[Line {line}] Command timed out after {timeout} seconds: {command}")
        return None
    except subprocess.CalledProcessError as e:
        line = inspect.currentframe().f_lineno
        logger.error(f"[Line {line}] Command failed: {command} in directory: {cwd or os.getcwd()}, error: {e.stderr}")
        return None
    except Exception as e:
        line = inspect.currentframe().f_lineno
        logger.error(f"[Line {line}] Unexpected error running command: {command}, error: {str(e)}")
        return None


def is_unused(path: str, days_threshold: int) -> bool:
    """
    Check if a file or directory hasn't been accessed for the threshold period.
    
    Args:
        path: Path to the file or directory
        days_threshold: Number of days to consider as threshold
        
    Returns:
        True if the file/directory is older than the threshold, False otherwise
    """
    try:
        # We use the most recent time among access, modification and creation time
        stat_info = os.stat(path)
        
        # Get the most recent time
        last_access_time = max(stat_info.st_atime, stat_info.st_mtime, stat_info.st_ctime)
        last_access_date = datetime.fromtimestamp(last_access_time)
        
        # Check if the last access time is older than the threshold
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        return last_access_date < threshold_date
    except Exception as e:
        logger.error(f"Error checking access time for {path}: {e}")
        # Be conservative - don't mark as unused if we can't check
        return False


def get_size(path: str) -> int:
    """
    Calculate the size of a file or directory in bytes.
    
    Args:
        path: Path to the file or directory
        
    Returns:
        Size in bytes
    """
    if os.path.isfile(path):
        return os.path.getsize(path)
    
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):  # Avoid broken symlinks
                total_size += os.path.getsize(fp)
    
    return total_size


def human_readable_size(size_bytes: int) -> str:
    """
    Convert size in bytes to human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human-readable size string (e.g., "4.2 MB")
    """
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}" 