"""Docker cleaner implementation for removing unused Docker images and volumes."""

import os
import json
import logging
import inspect
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import run_command
from maccleaner.cleaners import CLEANER_REGISTRY

logger = logging.getLogger("maccleaner.cleaners.docker")


class DockerCleaner(Cleaner):
    """Cleaner for Docker resources (images and volumes)."""

    def __init__(self, command_timeout: int = 30):
        """
        Initialize the Docker cleaner.
        
        Args:
            command_timeout: Default timeout for Docker commands in seconds
        """
        self.command_timeout = command_timeout

    @property
    def name(self) -> str:
        return "docker"

    @property
    def description(self) -> str:
        return "Removes unused Docker images and volumes"

    def display_help(self) -> None:
        """Display help information for Docker cleaner."""
        help_text = """
Docker Cleaner Help
==================

The Docker cleaner is a tool to clean unused Docker resources, helping you
reclaim disk space. It can identify and remove:

1. Unused Docker images - Images not being used by any container for a specified period
2. Unused Docker volumes - Volumes not mounted by any container for a specified period

USAGE:
    maccleaner clean docker [OPTIONS]

OPTIONS:
    --days DAYS     Number of days of inactivity before considering a resource unused
                    (default: 30)
    --dry-run       Only simulate cleaning without actually removing files
    -h, --help      Display this help message

EXAMPLES:
    # List all cleanable Docker resources (simulation mode)
    maccleaner clean docker --dry-run

    # Clean all unused Docker resources older than 30 days
    maccleaner clean docker

    # Clean unused Docker resources older than 90 days
    maccleaner clean docker --days 90

IMPORTANT NOTES:
    - The cleaner will only remove resources that haven't been used for the specified period
    - Images being used by running containers will not be removed
    - Volumes being used by running containers will not be removed
    - System will attempt to check when resources were last used
    - Docker daemon must be running for this cleaner to work
"""
        print(help_text)
        
    def clean(self, days_threshold: int = 30, dry_run: bool = True, args: Optional[List[str]] = None) -> bool:
        """
        Main method to run the Docker cleaner.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
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

    def check_prerequisites(self) -> bool:
        """Check if Docker is installed and accessible."""
        line = inspect.currentframe().f_lineno
        
        # First check if Docker CLI is available
        docker_check = run_command("docker --version", timeout=5)
        if docker_check is None:
            logger.error(f"[Line {line}] Docker is not installed or not available in PATH")
            return False
        
        # Then verify Docker daemon is responsive
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Docker version detected: {docker_check}")
        logger.info(f"[Line {line}] Checking if Docker daemon is responsive...")
        
        # Use a simple, quick command to test daemon responsiveness
        daemon_check = run_command("docker info --format '{{.ServerVersion}}'", timeout=10)
        if daemon_check is None:
            logger.error(f"[Line {line}] Docker daemon is not responding. Make sure Docker service is running.")
            return False
            
        logger.info(f"[Line {line}] Docker daemon is responsive, server version: {daemon_check}")
        return True

    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find unused Docker resources based on usage time.
        
        Args:
            days_threshold: Number of days of inactivity before considering a resource unused
            
        Returns:
            List of unused resources with metadata
        """
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Searching for unused Docker resources older than {days_threshold} days")
        
        # Get both unused images and volumes
        unused_images = self._get_unused_images(days_threshold)
        unused_volumes = self._get_unused_volumes(days_threshold)
        
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Found {len(unused_images)} unused images and {len(unused_volumes)} unused volumes")
        
        # Combine them into a single list with a type field
        cleanable_items = []
        
        for image in unused_images:
            image["type"] = "image"
            cleanable_items.append(image)
            
        for volume in unused_volumes:
            volume["type"] = "volume"
            cleanable_items.append(volume)
            
        return cleanable_items

    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific Docker resource.
        
        Args:
            item: The resource to clean
            dry_run: If True, only simulate cleaning
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        line = inspect.currentframe().f_lineno
        if dry_run:
            logger.debug(f"[Line {line}] Dry run mode - not actually deleting {item['type']}: {item.get('name', item.get('id', 'unknown'))}")
            return True
        
        if item["type"] == "image":
            line = inspect.currentframe().f_lineno
            logger.info(f"[Line {line}] Removing Docker image {item['id']} ({item['name']})")
            result = self._safe_docker_command(f"docker rmi {item['id']}", fallback_value=None, timeout=45)
            if result is None:
                logger.error(f"[Line {line}] Failed to remove Docker image {item['id']} ({item['name']})")
                return False
            return True
        elif item["type"] == "volume":
            line = inspect.currentframe().f_lineno
            logger.info(f"[Line {line}] Removing Docker volume {item['name']}")
            result = self._safe_docker_command(f"docker volume rm {item['name']}", fallback_value=None, timeout=30)
            if result is None:
                logger.error(f"[Line {line}] Failed to remove Docker volume {item['name']}")
                return False
            return True
        else:
            line = inspect.currentframe().f_lineno
            logger.error(f"[Line {line}] Unknown Docker resource type: {item['type']}")
            return False

    def item_to_str(self, item: Dict[str, Any]) -> str:
        """
        Convert a Docker resource to a string representation.
        
        Args:
            item: The Docker resource
            
        Returns:
            String representation of the resource
        """
        if item["type"] == "image":
            return f"Image: {item['name']} (unused for {item['days_unused']} days)"
        elif item["type"] == "volume":
            return f"Volume: {item['name']} (unused for {item['days_unused']} days)"
        else:
            return str(item)

    def _safe_docker_command(self, command: str, fallback_value: Any = None, timeout: Optional[int] = None) -> Any:
        """
        Execute a Docker command with improved error handling and timeouts.
        
        Args:
            command: Docker command to execute
            fallback_value: Value to return if command fails
            timeout: Command timeout in seconds (overrides default)
            
        Returns:
            Command output or fallback value on failure
        """
        line = inspect.currentframe().f_lineno
        actual_timeout = timeout if timeout is not None else self.command_timeout
        result = run_command(command, timeout=actual_timeout)
        
        if result is None:
            logger.warning(f"[Line {line}] Docker command failed or timed out after {actual_timeout}s: {command}")
            return fallback_value
            
        return result
        
        
    def _get_unused_images(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Get list of Docker images not used in the specified period.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of unused Docker images
        """
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Checking for unused Docker images")
        
        # Get all images with creation date
        logger.debug(f"[Line {line}] Getting list of Docker images - this may take a moment...")
        cmd_output = self._safe_docker_command(
            "docker images --format '{{.ID}}|{{.Repository}}|{{.Tag}}|{{.CreatedAt}}'", 
            fallback_value="",
            timeout=60
        )
        
        if not cmd_output:
            logger.warning(f"[Line {line}] No Docker images found or command failed")
            return []
        
        line = inspect.currentframe().f_lineno
        images = cmd_output.splitlines()
        logger.info(f"[Line {line}] Found {len(images)} Docker images to analyze")
        
        # Parse output
        unused_images = []
        
        # Get list of running containers to avoid removing their images
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Checking for images used by running containers")
        running_cmd = self._safe_docker_command("docker ps -q", fallback_value="", timeout=15)
        running_containers = running_cmd.split() if running_cmd else []
        
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Found {len(running_containers)} running containers")
        
        # Get images used by running containers
        used_images = []
        for container_idx, container in enumerate(running_containers):
            if container_idx % 5 == 0 and container_idx > 0:
                logger.debug(f"[Line {line}] Processed {container_idx}/{len(running_containers)} containers")
                
            img_output = self._safe_docker_command(
                f"docker inspect --format='{{{{.Image}}}}' {container}",
                fallback_value="",
                timeout=10
            )
            if img_output:
                image_id = img_output.split(':')[1] if ':' in img_output else img_output
                used_images.append(image_id)
                logger.debug(f"[Line {line}] Container {container} uses image {image_id}")
        
        # Get history of container usage to find last used date
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Checking container history for image usage")
        history_output = self._safe_docker_command(
            "docker ps -a --format '{{.Image}}|{{.CreatedAt}}'", 
            fallback_value="",
            timeout=60
        )
        image_last_used = {}
        
        if history_output:
            history_lines = history_output.splitlines()
            logger.debug(f"[Line {line}] Processing {len(history_lines)} container history records")
            
            for i, line_content in enumerate(history_lines):
                if i % 50 == 0 and i > 0:
                    logger.debug(f"[Line {line}] Processed {i}/{len(history_lines)} container history records")
                    
                if '|' in line_content:
                    image, created_at = line_content.split('|', 1)
                    try:
                        # Parse the created date
                        created_date = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S %z')
                        # Update the last used date if newer
                        if image not in image_last_used or created_date > image_last_used[image]:
                            image_last_used[image] = created_date
                    except ValueError as e:
                        logger.debug(f"[Line {line}] Failed to parse date '{created_at}' for image {image}: {e}")
                        # If date parsing fails, skip this entry
                        continue
        
        # Process the images
        line = inspect.currentframe().f_lineno
        threshold_date = datetime.now().astimezone() - timedelta(days=days_threshold)
        logger.debug(f"[Line {line}] Looking for images unused since {threshold_date.strftime('%Y-%m-%d')}")
        
        image_count = 0
        # Process images in batches for better logging
        for i, line_content in enumerate(images):
            if i % 20 == 0 and i > 0:
                logger.debug(f"[Line {line}] Processed {i}/{len(images)} images, found {len(unused_images)} unused")
                
            parts = line_content.split('|')
            if len(parts) != 4:
                logger.debug(f"[Line {line}] Skipping invalid image data: {line_content}")
                continue
            
            image_id, repository, tag, created_at = parts
            image_count += 1
            
            # Skip images without repository or tag (dangling)
            if repository == "<none>" or tag == "<none>":
                logger.debug(f"[Line {line}] Skipping dangling image {image_id}")
                continue
            
            # Skip images used by running containers
            if image_id in used_images:
                logger.debug(f"[Line {line}] Skipping image {image_id} ({repository}:{tag}) used by running container")
                continue
            
            # Check when the image was last used
            full_name = f"{repository}:{tag}"
            
            try:
                # Parse the created date for comparison
                created_date = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S %z')
                
                # Use the last used date if available, otherwise use created date
                last_used_date = image_last_used.get(full_name, created_date)
                
                # Check if the image is older than the threshold
                if last_used_date < threshold_date:
                    days_unused = (datetime.now().astimezone() - last_used_date).days
                    logger.debug(f"[Line {line}] Found unused image {image_id} ({full_name}), last used {days_unused} days ago")
                    
                    unused_images.append({
                        "id": image_id,
                        "name": full_name,
                        "created": created_date.strftime('%Y-%m-%d'),
                        "last_used": last_used_date.strftime('%Y-%m-%d'),
                        "days_unused": days_unused
                    })
            except (ValueError, TypeError) as e:
                logger.debug(f"[Line {line}] Failed to process image {image_id} ({repository}:{tag}): {e}")
                # If date parsing fails, skip this image
                continue
        
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Processed {image_count} images, found {len(unused_images)} unused")
        return unused_images

    def _get_unused_volumes(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Get list of Docker volumes not used in the specified period.
        
        Args:
            days_threshold: Number of days of inactivity
            
        Returns:
            List of unused Docker volumes
        """
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Checking for unused Docker volumes")
        
        # List all volumes in JSON format to parse easily
        logger.debug(f"[Line {line}] Getting list of Docker volumes - this may take a moment...")
        cmd_output = self._safe_docker_command("docker volume ls -q", fallback_value="", timeout=30)
        if not cmd_output:
            logger.warning(f"[Line {line}] No Docker volumes found or command failed")
            return []
        
        line = inspect.currentframe().f_lineno
        volumes = cmd_output.splitlines()
        logger.info(f"[Line {line}] Found {len(volumes)} Docker volumes to analyze")
        
        # Get list of running containers
        line = inspect.currentframe().f_lineno
        logger.debug(f"[Line {line}] Checking for volumes used by running containers")
        running_cmd = self._safe_docker_command("docker ps -q", fallback_value="", timeout=15)
        running_containers = running_cmd.split() if running_cmd else []
        
        # Get volumes used by running containers
        used_volumes = []
        for container_idx, container in enumerate(running_containers):
            if container_idx % 5 == 0 and container_idx > 0:
                logger.debug(f"[Line {line}] Processed {container_idx}/{len(running_containers)} containers")
                
            vol_output = self._safe_docker_command(
                f"docker inspect --format='{{{{json .Mounts}}}}' {container}", 
                fallback_value="[]",
                timeout=10
            )
            if vol_output and vol_output != "[]":
                try:
                    mounts = json.loads(vol_output)
                    for mount in mounts:
                        if mount.get('Type') == 'volume':
                            vol_name = mount.get('Name', '')
                            used_volumes.append(vol_name)
                            logger.debug(f"[Line {line}] Container {container} uses volume {vol_name}")
                except json.JSONDecodeError as e:
                    logger.debug(f"[Line {line}] Failed to parse mounts for container {container}: {e}")
                    continue
        
        # Check each volume
        line = inspect.currentframe().f_lineno
        unused_volumes = []
        volume_count = 0
        
        logger.info(f"[Line {line}] Analyzing {len(volumes)} volumes, {len(used_volumes)} are currently in use")
        
        for volume_idx, volume in enumerate(volumes):
            if volume_idx % 10 == 0 and volume_idx > 0:
                logger.debug(f"[Line {line}] Processed {volume_idx}/{len(volumes)} volumes, found {len(unused_volumes)} unused")
                
            volume_count += 1
            
            # Skip volumes used by running containers
            if volume in used_volumes:
                logger.debug(f"[Line {line}] Skipping volume {volume} used by running container")
                continue
                
            # Get volume details
            line = inspect.currentframe().f_lineno
            logger.debug(f"[Line {line}] Inspecting volume {volume}")
            inspect_output = self._safe_docker_command(
                f"docker volume inspect {volume}", 
                fallback_value="[]",
                timeout=15
            )
            if not inspect_output or inspect_output == "[]":
                logger.warning(f"[Line {line}] Failed to inspect volume {volume}")
                continue
                
            try:
                volume_info = json.loads(inspect_output)
                if not volume_info or len(volume_info) == 0:
                    logger.warning(f"[Line {line}] Empty inspection result for volume {volume}")
                    continue
                    
                volume_info = volume_info[0]  # Get the first (and only) volume
                
                # Check the creation time if available
                created_at = None
                
                # This is a bit tricky because Docker doesn't provide creation time for volumes directly
                # We'll use a heuristic based on label or mountpoint's modification time
                
                # Try to get creation time from labels (if previously set)
                labels = volume_info.get('Labels', {}) or {}
                if labels and 'created_at' in labels:
                    try:
                        created_at = datetime.fromisoformat(labels['created_at'])
                        logger.debug(f"[Line {line}] Volume {volume} creation time from label: {created_at}")
                    except (ValueError, TypeError) as e:
                        logger.debug(f"[Line {line}] Failed to parse label date for volume {volume}: {e}")
                        created_at = None
                
                # If no timestamp from labels, try to get it from the mountpoint
                if not created_at and 'Mountpoint' in volume_info:
                    mountpoint = volume_info['Mountpoint']
                    try:
                        # Get modification time of the mountpoint
                        if os.path.exists(mountpoint):
                            mtime = os.path.getmtime(mountpoint)
                            created_at = datetime.fromtimestamp(mtime)
                            logger.debug(f"[Line {line}] Volume {volume} creation time from mountpoint: {created_at}")
                    except (OSError, PermissionError) as e:
                        logger.debug(f"[Line {line}] Failed to get mountpoint time for volume {volume}: {e}")
                        created_at = None
                
                # If we couldn't determine when the volume was created, skip it
                if not created_at:
                    logger.debug(f"[Line {line}] Skipping volume {volume} - could not determine creation time")
                    continue
                    
                # Check if the volume is older than the threshold
                line = inspect.currentframe().f_lineno
                threshold_date = datetime.now() - timedelta(days=days_threshold)
                
                if created_at < threshold_date:
                    days_unused = (datetime.now() - created_at).days
                    logger.debug(f"[Line {line}] Found unused volume {volume}, unused for {days_unused} days")
                    
                    unused_volumes.append({
                        "name": volume,
                        "driver": volume_info.get('Driver', 'local'),
                        "created": created_at.strftime('%Y-%m-%d'),
                        "days_unused": days_unused
                    })
                    
            except (json.JSONDecodeError, IndexError, KeyError) as e:
                logger.warning(f"[Line {line}] Failed to process volume {volume}: {e}")
                continue
        
        line = inspect.currentframe().f_lineno
        logger.info(f"[Line {line}] Processed {volume_count} volumes, found {len(unused_volumes)} unused")
        return unused_volumes


# Register this cleaner
CLEANER_REGISTRY["docker"] = DockerCleaner 