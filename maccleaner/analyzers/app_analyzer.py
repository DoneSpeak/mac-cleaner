"""Application disk usage analyzer implementation."""

import json
import logging
import os
import plistlib
import re
import shutil
import subprocess
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from maccleaner.core.analyzer import Analyzer
from maccleaner.core.utils import run_command
from maccleaner.analyzers import ANALYZER_REGISTRY

logger = logging.getLogger("maccleaner.analyzers.app_analyzer")


class AppDiskAnalyzer(Analyzer):
    """Analyzer for application disk usage statistics."""

    def __init__(self):
        """Initialize the application disk usage analyzer."""
        self.home_dir = os.path.expanduser("~")
        self.applications_dir = "/Applications"
        self.user_applications_dir = os.path.join(self.home_dir, "Applications")
        self.library_dir = os.path.join(self.home_dir, "Library")
        
        # Common data directories
        self.app_support_dir = os.path.join(self.library_dir, "Application Support")
        self.caches_dir = os.path.join(self.library_dir, "Caches")
        self.containers_dir = os.path.join(self.library_dir, "Containers")
        self.preferences_dir = os.path.join(self.library_dir, "Preferences")
        self.logs_dir = os.path.join(self.library_dir, "Logs")
        self.saved_app_state_dir = os.path.join(self.library_dir, "Saved Application State")
        
        # Mapping between app bundle IDs and app paths
        self.bundle_id_to_path = {}
        
        # Data types and their descriptions
        self.data_types = {
            "app": "Application bundle",
            "cache": "Cache files",
            "support": "Application support files",
            "preferences": "Preference files",
            "logs": "Log files",
            "containers": "App containers",
            "saved_state": "Saved application state",
            "crashes": "Crash reports"
        }

    @property
    def name(self) -> str:
        return "app_analyzer"

    @property
    def description(self) -> str:
        return "Analyzes disk usage for applications and their associated data"

    def check_prerequisites(self) -> bool:
        """Check if running on macOS and have necessary permissions."""
        logger.info("Checking if running on macOS...")
        
        # Check if it's macOS
        platform_check = run_command("uname", timeout=5)
        if platform_check and platform_check.strip() != "Darwin":
            logger.error(f"Not running on macOS (detected: {platform_check.strip()})")
            return False
        
        # Check if Applications directory exists and is accessible
        if not os.path.exists(self.applications_dir):
            logger.error(f"Cannot access Applications directory: {self.applications_dir}")
            return False
            
        logger.info("Running on macOS with access to Applications directory")
        return True

    def analyze(self, target: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze disk usage for applications.
        
        Args:
            target: Optional target to analyze.
                   Can be a full path to an application or just an application name.
                   If just a name is provided, it will search in /Applications directory.
                   If None, analyze all applications.
            
        Returns:
            Dictionary with analysis results
        """
        logger.info(f"Analyzing disk usage for {'all applications' if target is None else target}")
        
        if not self.check_prerequisites():
            logger.error("Prerequisites not met, cannot perform analysis")
            return {
                "success": False,
                "error": "Prerequisites not met",
                "apps": []
            }
        
        try:
            # 如果target不为None，只对单个应用进行分析，不构建完整映射表
            if target is not None:
                logger.debug(f"Target specified: {target}")
                # 如果target是一个完整路径
                if os.path.exists(target) and target.endswith(".app"):
                    logger.debug(f"Target is a valid application path: {target}")
                    app_path = target
                else:
                    # 如果target只是应用名称，尝试在Applications目录中查找
                    logger.debug(f"Target is not a full path, searching for application: {target}")
                    app_path = self._find_app_by_name(target)
                    if not app_path:
                        logger.error(f"Could not find application: {target}")
                        return {
                            "success": False,
                            "error": f"Could not find application: {target}",
                            "apps": []
                        }
                
                logger.debug(f"Analyzing single application: {app_path}")
                try:
                    app_info = self._analyze_single_app(app_path)
                    if app_info:
                        logger.debug(f"Successfully analyzed application, total size: {app_info['total_size_formatted']}")
                        return {
                            "success": True,
                            "apps": [app_info],
                            "total_size": app_info["total_size"],
                            "total_size_formatted": self.format_size(app_info["total_size"])
                        }
                    else:
                        logger.error(f"Failed to analyze application: {app_path}")
                        return {
                            "success": False,
                            "error": f"Could not analyze application: {app_path}",
                            "apps": []
                        }
                except Exception as e:
                    logger.error(f"Exception analyzing {app_path}: {str(e)}")
                    logger.debug("Exception details:", exc_info=True)
                    return {
                        "success": False,
                        "error": f"Error analyzing {app_path}: {str(e)}",
                        "apps": []
                    }
            
            # 如果target为None，分析所有应用，此时才构建完整的bundle ID映射表
            logger.debug("Analyzing all applications")
            
            # 构建bundle ID映射表，因为需要分析所有应用
            logger.debug("Building bundle ID to application path mapping")
            self._build_bundle_id_mapping()
            
            apps_info = []
            total_size = 0
            errors_count = 0
            apps_count = 0
            
            # 收集所有要分析的应用路径
            all_apps = []
            
            # 首先收集/Applications中的应用
            try:
                app_entries = os.listdir(self.applications_dir)
                logger.debug(f"Found {len(app_entries)} entries in {self.applications_dir}")
                for app_name in app_entries:
                    if app_name.endswith(".app"):
                        all_apps.append(os.path.join(self.applications_dir, app_name))
            except (PermissionError, FileNotFoundError) as e:
                logger.error(f"Error accessing directory {self.applications_dir}: {e}")
            
            # 然后收集~/Applications中的应用
            if os.path.exists(self.user_applications_dir):
                try:
                    user_app_entries = os.listdir(self.user_applications_dir)
                    logger.debug(f"Found {len(user_app_entries)} entries in {self.user_applications_dir}")
                    for app_name in user_app_entries:
                        if app_name.endswith(".app"):
                            all_apps.append(os.path.join(self.user_applications_dir, app_name))
                except (PermissionError, FileNotFoundError) as e:
                    logger.error(f"Error accessing directory {self.user_applications_dir}: {e}")
            
            # 分析所有收集到的应用
            total_apps = len(all_apps)
            logger.debug(f"Going to analyze {total_apps} applications in total")
            
            for i, app_path in enumerate(all_apps):
                apps_count += 1
                app_name = os.path.basename(app_path).replace(".app", "")
                logger.debug(f"Analyzing application {i+1}/{total_apps}: {app_path}")
                
                try:
                    # 设定每个应用分析的超时时间（30秒）
                    import threading
                    import time
                    
                    app_result = [None]
                    app_error = [None]
                    
                    def analyze_with_timeout():
                        try:
                            app_result[0] = self._analyze_single_app(app_path)
                        except Exception as e:
                            app_error[0] = e
                    
                    app_thread = threading.Thread(target=analyze_with_timeout)
                    app_thread.daemon = True
                    app_thread.start()
                    app_thread.join(30)  # 等待最多30秒
                    
                    if app_thread.is_alive():
                        # 分析超时
                        logger.error(f"Timeout analyzing application: {app_path}, skipping")
                        errors_count += 1
                        continue
                    
                    if app_error[0]:
                        # 分析出错
                        logger.error(f"Error analyzing {app_path}: {app_error[0]}")
                        errors_count += 1
                        continue
                    
                    app_info = app_result[0]
                    if app_info:
                        logger.debug(f"Successfully analyzed {app_path}, size: {app_info['total_size_formatted']}")
                        apps_info.append(app_info)
                        total_size += app_info["total_size"]
                    else:
                        logger.warning(f"Failed to analyze {app_path}")
                        errors_count += 1
                except Exception as e:
                    logger.error(f"Exception analyzing {app_path}: {str(e)}")
                    logger.debug("Exception details:", exc_info=True)
                    errors_count += 1
                    continue
            
            # 按大小排序应用信息
            apps_info.sort(key=lambda x: x["total_size"], reverse=True)
            
            logger.debug(f"Analysis complete. Analyzed {apps_count} applications, {len(apps_info)} successful, {errors_count} errors.")
            logger.debug(f"Total size of all analyzed applications: {self.format_size(total_size)}")
            
            return {
                "success": True,
                "apps": apps_info,
                "total_size": total_size,
                "total_size_formatted": self.format_size(total_size),
                "errors_count": errors_count,
                "apps_count": apps_count
            }
        except Exception as e:
            logger.error(f"Unexpected exception during analysis: {str(e)}")
            logger.debug("Exception details:", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "apps": []
            }

    def _build_bundle_id_mapping(self) -> None:
        """Build a mapping of bundle IDs to application paths."""
        logger.debug("Building bundle ID to application path mapping")
        
        # Map bundle IDs for applications in /Applications
        try:
            app_list = os.listdir(self.applications_dir)
            logger.debug(f"Found {len(app_list)} entries in {self.applications_dir}")
        except (PermissionError, OSError) as e:
            logger.error(f"Error listing applications in {self.applications_dir}: {e}")
            app_list = []
            
        for app_name in app_list:
            if app_name.endswith(".app"):
                app_path = os.path.join(self.applications_dir, app_name)
                try:
                    bundle_id = self._get_bundle_id(app_path)
                    if bundle_id:
                        self.bundle_id_to_path[bundle_id] = app_path
                except Exception as e:
                    logger.error(f"Failed to get bundle ID for {app_path}: {e}")
                    continue
        
        # Map bundle IDs for applications in ~/Applications if it exists
        if os.path.exists(self.user_applications_dir):
            try:
                user_app_list = os.listdir(self.user_applications_dir)
                logger.debug(f"Found {len(user_app_list)} entries in {self.user_applications_dir}")
            except (PermissionError, OSError) as e:
                logger.error(f"Error listing applications in {self.user_applications_dir}: {e}")
                user_app_list = []
                
            for app_name in user_app_list:
                if app_name.endswith(".app"):
                    app_path = os.path.join(self.user_applications_dir, app_name)
                    try:
                        bundle_id = self._get_bundle_id(app_path)
                        if bundle_id:
                            self.bundle_id_to_path[bundle_id] = app_path
                    except Exception as e:
                        logger.error(f"Failed to get bundle ID for {app_path}: {e}")
                        continue
                        
        logger.debug(f"Mapped {len(self.bundle_id_to_path)} applications to bundle IDs")

    def _get_bundle_id(self, app_path: str) -> Optional[str]:
        """
        Get the bundle ID for an application.
        
        Args:
            app_path: Path to the application bundle
            
        Returns:
            Bundle ID or None if not found
        """
        logger.debug(f"Getting bundle ID for {app_path}")
        plist_path = os.path.join(app_path, "Contents", "Info.plist")
        logger.debug(f"Looking for Info.plist at: {plist_path}")
        
        if not os.path.exists(plist_path):
            logger.warning(f"Info.plist not found at {plist_path}")
            return None
        
        # 为每个plist文件解析设置5秒超时
        import threading
        import time
        
        result = [None]
        error = [None]
        
        def load_plist_with_timeout():
            try:
                with open(plist_path, 'rb') as f:
                    try:
                        plist_data = plistlib.load(f)
                        bundle_id = plist_data.get('CFBundleIdentifier')
                        if bundle_id:
                            logger.debug(f"Found bundle ID: {bundle_id}")
                            result[0] = bundle_id
                        else:
                            logger.warning(f"No CFBundleIdentifier found in {plist_path}")
                    except Exception as e:
                        logger.error(f"Error parsing Info.plist at {plist_path}: {e}")
                        error[0] = e
            except (PermissionError, OSError) as e:
                logger.error(f"Error reading Info.plist for {app_path}: {e}")
                error[0] = e
        
        # 用线程实现5秒超时
        plist_thread = threading.Thread(target=load_plist_with_timeout)
        plist_thread.daemon = True  # 将线程设为守护线程，使主线程退出时该线程也退出
        plist_thread.start()
        plist_thread.join(5)  # 等待最多5秒
        
        if plist_thread.is_alive():
            logger.error(f"Timeout reading Info.plist for {app_path}, parsing took too long")
            # 生成一个基于应用名称的假bundle ID
            app_name = os.path.basename(app_path).replace(".app", "")
            generated_id = f"com.timeout.{app_name.lower().replace(' ', '')}"
            logger.debug(f"Generated fallback bundle ID due to timeout: {generated_id}")
            return generated_id
        
        if result[0]:
            return result[0]
        
        # 如果正常解析失败，尝试备选方法
        try:
            logger.debug(f"Trying alternative method to extract bundle ID from {plist_path}")
            
            # 备选方法1: 使用plutil命令行工具，设置超时
            cmd = f"plutil -convert json -o - '{plist_path}' 2>/dev/null"
            plutil_result = run_command(cmd, timeout=2)
            
            if plutil_result:
                try:
                    json_data = json.loads(plutil_result)
                    bundle_id = json_data.get('CFBundleIdentifier')
                    if bundle_id:
                        logger.debug(f"Found bundle ID via plutil: {bundle_id}")
                        return bundle_id
                except json.JSONDecodeError:
                    pass
            
            # 备选方法2: 使用grep，设置超时
            cmd = f"grep -A1 CFBundleIdentifier '{plist_path}' 2>/dev/null"
            grep_result = run_command(cmd, timeout=2)
            
            if grep_result:
                match = re.search(r'<string>(.*?)</string>', grep_result)
                if match:
                    bundle_id = match.group(1)
                    logger.debug(f"Found bundle ID via grep: {bundle_id}")
                    return bundle_id
        except Exception as alt_e:
            logger.debug(f"Alternative methods failed: {alt_e}")
        
        # 生成一个基于应用名称的假bundle ID
        app_name = os.path.basename(app_path).replace(".app", "")
        if ' ' in app_name:
            generated_id = f"com.apple.{app_name.lower().replace(' ', '')}"
        else:
            generated_id = f"com.unknown.{app_name.lower().replace(' ', '')}"
            
        logger.debug(f"Generated fallback bundle ID: {generated_id}")
        return generated_id

    def _analyze_single_app(self, app_path: str) -> Optional[Dict[str, Any]]:
        """
        Analyze disk usage for a single application.
        
        Args:
            app_path: Path to the application bundle
            
        Returns:
            Dict with analysis results for the application
        """
        logger.debug(f"Starting analysis of application: {app_path}")
        
        if not os.path.exists(app_path):
            logger.warning(f"Application does not exist: {app_path}")
            return None
            
        app_name = os.path.basename(app_path).replace(".app", "")
        logger.debug(f"Application name: {app_name}")
        
        # Get bundle ID
        bundle_id = self._get_bundle_id(app_path)
        if not bundle_id:
            logger.warning(f"Could not determine bundle ID for {app_path}")
            # Try to guess a bundle ID from the app name
            bundle_id = f"com.unknown.{app_name.lower().replace(' ', '')}"
            logger.debug(f"Using generated bundle ID: {bundle_id}")
        
        # Initialize result with application bundle size
        try:
            app_bundle_size = self._get_directory_size(app_path)
            logger.debug(f"Application bundle size: {self.format_size(app_bundle_size)}")
        except Exception as e:
            logger.error(f"Error getting size of {app_path}: {e}")
            app_bundle_size = 0
        
        result = {
            "name": app_name,
            "bundle_id": bundle_id,
            "path": app_path,
            "sizes": {
                "app": app_bundle_size
            },
            "sizes_formatted": {
                "app": self.format_size(app_bundle_size)
            },
            "total_size": app_bundle_size,
            "locations": {
                "app": app_path
            }
        }
        
        logger.debug(f"Finding associated data for {app_name} (bundle ID: {bundle_id})")
        
        # Find and measure all associated data
        try:
            logger.debug("Looking for application support files...")
            self._find_app_support_files(bundle_id, result)
            
            logger.debug("Looking for cache files...")
            self._find_cache_files(bundle_id, result)
            
            logger.debug("Looking for preferences...")
            self._find_preferences(bundle_id, result)
            
            logger.debug("Looking for logs...")
            self._find_logs(bundle_id, result)
            
            logger.debug("Looking for containers...")
            self._find_containers(bundle_id, result)
            
            logger.debug("Looking for saved application state...")
            self._find_saved_state(bundle_id, result)
        except Exception as e:
            logger.error(f"Error finding associated data for {app_name}: {e}")
            logger.debug("Exception details:", exc_info=True)
        
        # Add total size
        result["total_size_formatted"] = self.format_size(result["total_size"])
        logger.debug(f"Total size for {app_name}: {result['total_size_formatted']}")
        
        # Add data type percentages
        total_size = result["total_size"]
        if total_size > 0:
            result["percentages"] = {}
            for data_type, size in result["sizes"].items():
                result["percentages"][data_type] = round((size / total_size) * 100, 1)
        
        logger.debug(f"Analysis of {app_name} complete")
        return result

    def _find_app_support_files(self, bundle_id: str, result: Dict[str, Any]) -> None:
        """
        Find and measure Application Support files.
        
        Args:
            bundle_id: Application bundle ID
            result: Result dictionary to update
        """
        # Look in ~/Library/Application Support/
        support_path = os.path.join(self.app_support_dir, bundle_id)
        alt_support_path = os.path.join(self.app_support_dir, result["name"])
        
        if os.path.exists(support_path):
            size = self._get_directory_size(support_path)
            result["sizes"]["support"] = size
            result["sizes_formatted"]["support"] = self.format_size(size)
            result["total_size"] += size
            result["locations"]["support"] = support_path
        elif os.path.exists(alt_support_path):
            size = self._get_directory_size(alt_support_path)
            result["sizes"]["support"] = size
            result["sizes_formatted"]["support"] = self.format_size(size)
            result["total_size"] += size
            result["locations"]["support"] = alt_support_path

    def _find_cache_files(self, bundle_id: str, result: Dict[str, Any]) -> None:
        """
        Find and measure cache files.
        
        Args:
            bundle_id: Application bundle ID
            result: Result dictionary to update
        """
        # Look in ~/Library/Caches/
        cache_path = os.path.join(self.caches_dir, bundle_id)
        alt_cache_path = os.path.join(self.caches_dir, result["name"])
        
        total_cache_size = 0
        cache_locations = []
        
        if os.path.exists(cache_path):
            size = self._get_directory_size(cache_path)
            total_cache_size += size
            cache_locations.append(cache_path)
        
        if os.path.exists(alt_cache_path):
            size = self._get_directory_size(alt_cache_path)
            total_cache_size += size
            cache_locations.append(alt_cache_path)
        
        # Look for other cache directories with this bundle ID as prefix
        for dirname in os.listdir(self.caches_dir):
            if dirname.startswith(f"{bundle_id}."):
                cache_path = os.path.join(self.caches_dir, dirname)
                if os.path.isdir(cache_path):
                    size = self._get_directory_size(cache_path)
                    total_cache_size += size
                    cache_locations.append(cache_path)
        
        if total_cache_size > 0:
            result["sizes"]["cache"] = total_cache_size
            result["sizes_formatted"]["cache"] = self.format_size(total_cache_size)
            result["total_size"] += total_cache_size
            result["locations"]["cache"] = cache_locations

    def _find_preferences(self, bundle_id: str, result: Dict[str, Any]) -> None:
        """
        Find and measure preference files.
        
        Args:
            bundle_id: Application bundle ID
            result: Result dictionary to update
        """
        # Look in ~/Library/Preferences/
        pref_paths = []
        
        # Look for the primary plist
        primary_pref_path = os.path.join(self.preferences_dir, f"{bundle_id}.plist")
        if os.path.exists(primary_pref_path):
            pref_paths.append(primary_pref_path)
        
        # Look for preference files with this bundle ID as prefix
        for filename in os.listdir(self.preferences_dir):
            if filename.startswith(f"{bundle_id}.") and filename.endswith(".plist"):
                pref_path = os.path.join(self.preferences_dir, filename)
                if pref_path != primary_pref_path:  # Don't double-count
                    pref_paths.append(pref_path)
        
        total_pref_size = 0
        for path in pref_paths:
            try:
                total_pref_size += os.path.getsize(path)
            except (FileNotFoundError, PermissionError):
                pass
        
        if total_pref_size > 0:
            result["sizes"]["preferences"] = total_pref_size
            result["sizes_formatted"]["preferences"] = self.format_size(total_pref_size)
            result["total_size"] += total_pref_size
            result["locations"]["preferences"] = pref_paths

    def _find_logs(self, bundle_id: str, result: Dict[str, Any]) -> None:
        """
        Find and measure log files.
        
        Args:
            bundle_id: Application bundle ID
            result: Result dictionary to update
        """
        # Look in ~/Library/Logs/
        logs_path = os.path.join(self.logs_dir, bundle_id)
        alt_logs_path = os.path.join(self.logs_dir, result["name"])
        
        total_logs_size = 0
        log_locations = []
        
        if os.path.exists(logs_path):
            size = self._get_directory_size(logs_path)
            total_logs_size += size
            log_locations.append(logs_path)
        
        if os.path.exists(alt_logs_path):
            size = self._get_directory_size(alt_logs_path)
            total_logs_size += size
            log_locations.append(alt_logs_path)
        
        # Look for crash logs
        crash_logs_dir = os.path.join(self.library_dir, "Logs", "DiagnosticReports")
        if os.path.exists(crash_logs_dir):
            crash_size = 0
            crash_paths = []
            
            for filename in os.listdir(crash_logs_dir):
                if filename.startswith(f"{result['name']}_"):
                    crash_path = os.path.join(crash_logs_dir, filename)
                    try:
                        size = os.path.getsize(crash_path)
                        crash_size += size
                        crash_paths.append(crash_path)
                    except (FileNotFoundError, PermissionError):
                        pass
            
            if crash_size > 0:
                result["sizes"]["crashes"] = crash_size
                result["sizes_formatted"]["crashes"] = self.format_size(crash_size)
                result["total_size"] += crash_size
                result["locations"]["crashes"] = crash_paths
        
        if total_logs_size > 0:
            result["sizes"]["logs"] = total_logs_size
            result["sizes_formatted"]["logs"] = self.format_size(total_logs_size)
            result["total_size"] += total_logs_size
            result["locations"]["logs"] = log_locations

    def _find_containers(self, bundle_id: str, result: Dict[str, Any]) -> None:
        """
        Find and measure app containers.
        
        Args:
            bundle_id: Application bundle ID
            result: Result dictionary to update
        """
        # Look in ~/Library/Containers/
        if not os.path.exists(self.containers_dir):
            return
            
        container_path = os.path.join(self.containers_dir, bundle_id)
        container_locations = []
        total_container_size = 0
        
        if os.path.exists(container_path):
            size = self._get_directory_size(container_path)
            total_container_size += size
            container_locations.append(container_path)
        
        # Look for other containers with this bundle ID as prefix
        for dirname in os.listdir(self.containers_dir):
            if dirname.startswith(f"{bundle_id}."):
                path = os.path.join(self.containers_dir, dirname)
                if os.path.isdir(path) and path != container_path:  # Don't double-count
                    size = self._get_directory_size(path)
                    total_container_size += size
                    container_locations.append(path)
        
        if total_container_size > 0:
            result["sizes"]["containers"] = total_container_size
            result["sizes_formatted"]["containers"] = self.format_size(total_container_size)
            result["total_size"] += total_container_size
            result["locations"]["containers"] = container_locations

    def _find_saved_state(self, bundle_id: str, result: Dict[str, Any]) -> None:
        """
        Find and measure saved application state.
        
        Args:
            bundle_id: Application bundle ID
            result: Result dictionary to update
        """
        # Look in ~/Library/Saved Application State/
        if not os.path.exists(self.saved_app_state_dir):
            return
            
        saved_state_path = os.path.join(self.saved_app_state_dir, f"{bundle_id}.savedState")
        
        if os.path.exists(saved_state_path):
            size = self._get_directory_size(saved_state_path)
            result["sizes"]["saved_state"] = size
            result["sizes_formatted"]["saved_state"] = self.format_size(size)
            result["total_size"] += size
            result["locations"]["saved_state"] = saved_state_path

    def _get_directory_size(self, path: str) -> int:
        """
        Get the size of a directory or file in bytes.
        
        Args:
            path: Path to the directory or file
            
        Returns:
            Size in bytes
        """
        logger.debug(f"Calculating size of: {path}")
        
        if not os.path.exists(path):
            logger.warning(f"Path does not exist: {path}")
            return 0
            
        if os.path.isfile(path):
            try:
                size = os.path.getsize(path)
                logger.debug(f"File size for {path}: {self.format_size(size)}")
                return size
            except (FileNotFoundError, PermissionError, OSError) as e:
                logger.error(f"Error getting file size for {path}: {e}")
                return 0
        
        total_size = 0
        try:
            file_count = 0
            dir_count = 0
            
            for dirpath, dirnames, filenames in os.walk(path):
                dir_count += len(dirnames)
                file_count += len(filenames)
                
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        file_size = os.path.getsize(fp)
                        total_size += file_size
                    except (FileNotFoundError, PermissionError, OSError) as e:
                        logger.debug(f"Error getting size of {fp}: {e}")
                        pass
            
            logger.debug(f"Scanned {dir_count} directories and {file_count} files in {path}")
            logger.debug(f"Total size for {path}: {self.format_size(total_size)}")
            
        except (PermissionError, OSError) as e:
            logger.error(f"Error walking directory {path}: {e}")
            
        return total_size

    def generate_report(self, analysis_result: Dict[str, Any], output_format: str = "txt") -> str:
        """
        Generate a formatted report from analysis results.
        
        Args:
            analysis_result: The result from the analyze method
            output_format: Output format (txt, json, or csv)
            
        Returns:
            Formatted report string
        """
        logger.debug(f"Generating report in {output_format} format")
        
        if output_format == "csv":
            return self.generate_csv_report(analysis_result)
        elif output_format == "json":
            try:
                return json.dumps(analysis_result, indent=2)
            except TypeError as e:
                logger.error(f"Failed to serialize result to JSON: {e}")
                return f"Error generating JSON report: {e}"
        else:  # Default to txt
            return self._generate_txt_report(analysis_result)
            
    def _generate_txt_report(self, analysis_result: Dict[str, Any]) -> str:
        """
        Generate a human-readable text report from analysis results.
        
        Args:
            analysis_result: The result from the analyze method
            
        Returns:
            Formatted text report string
        """
        logger.debug("Generating human-readable text report")
        
        if not analysis_result.get("success", False):
            error_msg = f"Analysis failed: {analysis_result.get('error', 'Unknown error')}"
            logger.error(error_msg)
            return error_msg
        
        try:
            report = []
            report.append("=== Application Disk Usage Analysis ===")
            
            app_count = analysis_result.get("app_count", 0)
            total_size = analysis_result.get("total_size_formatted", "0 B")
            
            report.append(f"Total apps analyzed: {app_count}")
            report.append(f"Total disk usage: {total_size}")
            report.append("")
            
            # Sort apps by total size (descending)
            apps = sorted(analysis_result.get("apps", []), 
                         key=lambda x: x.get("total_size", 0), 
                         reverse=True)
            
            logger.debug(f"Formatting report for {len(apps)} applications")
            
            for i, app in enumerate(apps, 1):
                app_name = app.get("name", "Unknown")
                app_size = app.get("total_size_formatted", "0 B")
                
                report.append(f"{i}. {app_name} - {app_size}")
                report.append(f"   Bundle ID: {app.get('bundle_id', 'Unknown')}")
                report.append(f"   Location: {app.get('path', 'Unknown')}")
                report.append("   Disk usage by type:")
                
                # Sort data types by size (descending)
                try:
                    data_types = sorted(app.get("sizes", {}).items(), 
                                       key=lambda x: x[1], 
                                       reverse=True)
                    
                    for data_type, size in data_types:
                        percentage = app.get("percentages", {}).get(data_type, 0)
                        description = self.data_types.get(data_type, data_type.capitalize())
                        size_formatted = app.get("sizes_formatted", {}).get(data_type, "0 B")
                        report.append(f"     - {description}: {size_formatted} ({percentage}%)")
                except Exception as e:
                    logger.error(f"Error formatting data types for {app_name}: {e}")
                    report.append(f"     - Error formatting data types: {e}")
                
                report.append("")
            
            logger.debug("Report generation complete")
            return "\n".join(report)
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            logger.debug("Exception details:", exc_info=True)
            return f"Error generating report: {e}"

    def generate_csv_report(self, analysis_result: Dict[str, Any]) -> str:
        """
        Generate a CSV report from analysis results.
        
        Args:
            analysis_result: The result from the analyze method
            
        Returns:
            CSV formatted report string
        """
        logger.debug("Generating CSV report")
        
        if not analysis_result.get("success", False):
            error_msg = f"Analysis failed: {analysis_result.get('error', 'Unknown error')}"
            logger.error(error_msg)
            return error_msg
        
        try:
            import csv
            import io
            
            # Use StringIO to build CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header row
            writer.writerow([
                "Rank", "Name", "Bundle ID", "Location", "Total Size (MB)", 
                "App Bundle Size (MB)", "App Bundle %", 
                "Cache Size (MB)", "Cache %",
                "App Support Size (MB)", "App Support %",
                "Preferences Size (KB)", "Preferences %",
                "Logs Size (MB)", "Logs %",
                "Containers Size (MB)", "Containers %",
                "Saved State Size (KB)", "Saved State %",
                "Crash Reports Size (KB)", "Crash Reports %"
            ])
            
            # Sort apps by total size (descending)
            apps = sorted(analysis_result.get("apps", []), 
                         key=lambda x: x.get("total_size", 0), 
                         reverse=True)
            
            logger.debug(f"Formatting CSV for {len(apps)} applications")
            
            for i, app in enumerate(apps, 1):
                app_name = app.get("name", "Unknown")
                app_size_bytes = app.get("total_size", 0)
                app_size_mb = app_size_bytes / (1024 * 1024)  # Convert to MB
                bundle_id = app.get('bundle_id', 'Unknown')
                path = app.get('path', 'Unknown')
                
                # Get individual sizes and percentages
                sizes = app.get("sizes", {})
                percentages = app.get("percentages", {})
                
                # Convert all sizes to appropriate units for better readability
                app_bundle_mb = sizes.get("app", 0) / (1024 * 1024)
                cache_mb = sizes.get("cache", 0) / (1024 * 1024)
                support_mb = sizes.get("support", 0) / (1024 * 1024)
                pref_kb = sizes.get("preferences", 0) / 1024
                logs_mb = sizes.get("logs", 0) / (1024 * 1024)
                containers_mb = sizes.get("containers", 0) / (1024 * 1024)
                saved_state_kb = sizes.get("saved_state", 0) / 1024
                crash_kb = sizes.get("crashes", 0) / 1024
                
                # Format percentages as actual percentages with % symbol
                app_bundle_pct = f"{percentages.get('app', 0):.1f}%"
                cache_pct = f"{percentages.get('cache', 0):.1f}%"
                support_pct = f"{percentages.get('support', 0):.1f}%"
                pref_pct = f"{percentages.get('preferences', 0):.1f}%"
                logs_pct = f"{percentages.get('logs', 0):.1f}%"
                containers_pct = f"{percentages.get('containers', 0):.1f}%"
                saved_state_pct = f"{percentages.get('saved_state', 0):.1f}%"
                crash_pct = f"{percentages.get('crashes', 0):.1f}%"
                
                # Prepare row data with properly formatted values
                row = [
                    i,
                    app_name,
                    bundle_id,
                    path,
                    f"{app_size_mb:.2f}",
                    # App bundle
                    f"{app_bundle_mb:.2f}",
                    app_bundle_pct,
                    # Cache
                    f"{cache_mb:.2f}",
                    cache_pct,
                    # Application support
                    f"{support_mb:.2f}",
                    support_pct,
                    # Preferences
                    f"{pref_kb:.2f}",
                    pref_pct,
                    # Logs
                    f"{logs_mb:.2f}",
                    logs_pct,
                    # Containers
                    f"{containers_mb:.2f}",
                    containers_pct,
                    # Saved application state
                    f"{saved_state_kb:.2f}",
                    saved_state_pct,
                    # Crash reports
                    f"{crash_kb:.2f}",
                    crash_pct,
                ]
                
                writer.writerow(row)
            
            csv_content = output.getvalue()
            output.close()
            
            logger.debug("CSV report generation complete")
            return csv_content
        except Exception as e:
            logger.error(f"Error generating CSV report: {e}")
            logger.debug("Exception details:", exc_info=True)
            return f"Error generating CSV report: {e}"

    def _find_app_by_name(self, app_name: str) -> Optional[str]:
        """
        Find an application by name in the Applications directories, ignoring case.
        
        Args:
            app_name: The name of the application to find
            
        Returns:
            Full path to the application or None if not found
        """
        logger.debug(f"Searching for application by name: '{app_name}'")
        
        # If the app name already has .app extension, use it as is, otherwise add it
        if not app_name.lower().endswith(".app"):
            app_name_with_ext = f"{app_name}.app"
            logger.debug(f"Added .app extension, looking for: '{app_name_with_ext}'")
        else:
            app_name_with_ext = app_name
            app_name = app_name[:-4]  # Remove .app suffix for comparison
            logger.debug(f"App name already has .app extension, base name: '{app_name}'")
        
        # First try exact match
        exact_path = os.path.join(self.applications_dir, app_name_with_ext)
        logger.debug(f"Checking for exact match at: {exact_path}")
        if os.path.exists(exact_path):
            logger.debug(f"Found exact match at: {exact_path}")
            return exact_path
        
        # Then try case-insensitive search in /Applications
        logger.debug(f"Exact match not found. Trying case-insensitive search in: {self.applications_dir}")
        try:
            entries = os.listdir(self.applications_dir)
            logger.debug(f"Found {len(entries)} entries in {self.applications_dir}")
        except (PermissionError, FileNotFoundError) as e:
            logger.error(f"Error accessing directory {self.applications_dir}: {e}")
            entries = []
            
        for entry in entries:
            logger.debug(f"Checking entry: {entry}")
            if entry.lower() == app_name_with_ext.lower() or entry.lower() == app_name.lower() + ".app":
                match_path = os.path.join(self.applications_dir, entry)
                logger.debug(f"Found case-insensitive match: {match_path}")
                return match_path
            
        # If not found, try in ~/Applications
        if os.path.exists(self.user_applications_dir):
            logger.debug(f"App not found in {self.applications_dir}, checking {self.user_applications_dir}")
            exact_path = os.path.join(self.user_applications_dir, app_name_with_ext)
            logger.debug(f"Checking for exact match at: {exact_path}")
            if os.path.exists(exact_path):
                logger.debug(f"Found exact match at: {exact_path}")
                return exact_path
                
            try:
                entries = os.listdir(self.user_applications_dir)
                logger.debug(f"Found {len(entries)} entries in {self.user_applications_dir}")
            except (PermissionError, FileNotFoundError) as e:
                logger.error(f"Error accessing directory {self.user_applications_dir}: {e}")
                entries = []
                
            for entry in entries:
                logger.debug(f"Checking entry: {entry}")
                if entry.lower() == app_name_with_ext.lower() or entry.lower() == app_name.lower() + ".app":
                    match_path = os.path.join(self.user_applications_dir, entry)
                    logger.debug(f"Found case-insensitive match: {match_path}")
                    return match_path
        else:
            logger.debug(f"User applications directory does not exist: {self.user_applications_dir}")
        
        # Not found
        logger.debug(f"Application '{app_name}' not found in any applications directory")
        return None


# Register this analyzer
ANALYZER_REGISTRY["app_analyzer"] = AppDiskAnalyzer 