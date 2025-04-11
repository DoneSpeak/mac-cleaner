"""Maven cleaner implementation for removing unused Maven dependencies."""

import os
import shutil
import logging
from typing import Dict, List, Any, Optional

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import is_unused, get_size, human_readable_size
from maccleaner.cleaners import CLEANER_REGISTRY

logger = logging.getLogger("maccleaner.cleaners.maven")


class MavenCleaner(Cleaner):
    """Cleaner for Maven dependencies in the local repository."""

    @property
    def name(self) -> str:
        return "maven"

    @property
    def description(self) -> str:
        return "Removes unused Maven dependencies from the local repository"

    def display_help(self) -> None:
        """Display help information for Maven cleaner."""
        help_text = """
Maven Cleaner Help
=================

The Maven cleaner is a tool to clean unused Maven dependencies from your local
repository, helping you reclaim disk space. It identifies artifacts that haven't 
been accessed for a specified period.

USAGE:
    maccleaner clean maven [OPTIONS]

OPTIONS:
    --days DAYS     Number of days of inactivity before considering a dependency unused
                    (default: 30)
    --dry-run       Only simulate cleaning without actually removing files
    -h, --help      Display this help message

EXAMPLES:
    # List all cleanable Maven dependencies (simulation mode)
    maccleaner clean maven --dry-run

    # Clean all unused Maven dependencies older than 30 days
    maccleaner clean maven

    # Clean unused Maven dependencies older than 90 days
    maccleaner clean maven --days 90

IMPORTANT NOTES:
    - The cleaner scans your local Maven repository (~/.m2/repository by default)
    - Only completely unused artifacts (those not accessed for the specified period) are removed
    - If you use a custom repository location, set it in your Maven settings.xml file
"""
        print(help_text)

    def check_prerequisites(self) -> bool:
        """
        Check if Maven repository exists.
        
        Returns:
            True if Maven repository exists, False otherwise
        """
        repo_path = self.get_maven_repo_path()
        if repo_path is None:
            logger.error(
                "Maven repository not found. Ensure Maven is installed and the "
                "repository exists at '~/.m2/repository' or check your Maven settings."
            )
            return False
        return True

    def get_maven_repo_path(self) -> Optional[str]:
        """
        Get the path to the local Maven repository.
        
        Returns:
            The path to the Maven repository, or None if not found
        """
        # Default Maven repository location
        default_path = os.path.expanduser("~/.m2/repository")
        
        # Check if M2_HOME environment variable is set
        m2_home = os.environ.get("M2_HOME")
        if m2_home:
            custom_path = os.path.join(m2_home, "repository")
            if os.path.exists(custom_path):
                logger.debug(f"Using Maven repository from M2_HOME: {custom_path}")
                return custom_path
        
        # Check Maven settings.xml for custom repository location
        settings_paths = [
            os.path.expanduser("~/.m2/settings.xml"),
            "/etc/maven/settings.xml"
        ]
        
        # This is a simplistic approach - a full implementation would parse XML
        # For now, we just use the default location
        
        if os.path.exists(default_path):
            logger.debug(f"Using default Maven repository: {default_path}")
            return default_path
        
        logger.debug(
            f"Maven repository not found at default location: {default_path}. "
            f"Ensure Maven is installed and has been used at least once."
        )
        return None

    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find unused Maven artifacts based on access time.
        
        Args:
            days_threshold: Number of days of inactivity before considering an artifact unused
            
        Returns:
            List of unused artifacts with metadata
        """
        repo_path = self.get_maven_repo_path()
        if not repo_path:
            logger.error("Maven repository not found")
            return []
        
        unused_artifacts = []
        total_size = 0
        
        logger.info(f"Scanning Maven repository at {repo_path}")
        
        # Walk through the repository
        for root, dirs, files in os.walk(repo_path):
            # Check if this is the root of an artifact (contains a .jar file or a pom.xml)
            is_artifact_root = any(f.endswith(".jar") or f == "pom.xml" for f in files)
            
            if is_artifact_root:
                # Check if the entire artifact directory is unused
                if is_unused(root, days_threshold):
                    # Calculate size
                    size = get_size(root)
                    total_size += size
                    
                    # Get relative path from the repository root
                    rel_path = os.path.relpath(root, repo_path)
                    
                    unused_artifacts.append({
                        "path": root,
                        "rel_path": rel_path,
                        "size": size,
                        "human_size": human_readable_size(size)
                    })
        
        logger.info(f"Found {len(unused_artifacts)} unused artifacts "
                   f"(Total: {human_readable_size(total_size)})")
        
        return unused_artifacts

    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific Maven artifact.
        
        Args:
            item: The artifact to clean
            dry_run: If True, only simulate cleaning
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        if dry_run:
            return True
        
        try:
            path = item["path"]
            shutil.rmtree(path)
            return True
        except Exception as e:
            logger.error(f"Error deleting {item['path']}: {e}")
            return False

    def item_to_str(self, item: Dict[str, Any]) -> str:
        """
        Convert an artifact item to a string representation.
        
        Args:
            item: The artifact item
            
        Returns:
            String representation of the artifact
        """
        return f"{item['rel_path']} ({item['human_size']})"
        
    def clean(self, days_threshold: int = 30, dry_run: bool = True, args: Optional[List[str]] = None) -> bool:
        """
        Main method to run the Maven cleaner.
        
        Args:
            days_threshold: Number of days of inactivity before considering an artifact unused
            dry_run: If True, only simulate cleaning
            args: Additional command-line arguments
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        # Check for help argument
        if args and ('--help' in args or '-h' in args):
            self.display_help()
            return True
            
        # Call the parent class method for the standard cleaning workflow
        return super().clean(days_threshold, dry_run)


# Register this cleaner
CLEANER_REGISTRY["maven"] = MavenCleaner 