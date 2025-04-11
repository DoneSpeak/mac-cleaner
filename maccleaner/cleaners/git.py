"""Git cleaner implementation for removing unused Git branches and stale repositories."""

import os
import logging
import inspect
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.utils import run_command
from maccleaner.cleaners import CLEANER_REGISTRY

logger = logging.getLogger("maccleaner.cleaners.git")


class GitCleaner(Cleaner):
    """Cleaner for Git branches and repositories."""

    def __init__(self, target_repos: List[str] = None, clean_unmerged: bool = False):
        """
        Initialize the Git cleaner.
        
        Args:
            target_repos: Optional list of specific repository paths to clean
            clean_unmerged: If True, allows deletion of unmerged branches
        """
        self.target_repos = target_repos
        self.clean_unmerged = clean_unmerged

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Removes unused Git branches from local repositories"

    def display_help(self) -> None:
        """Display help information for Git cleaner."""
        display_cleaner_help("git")

    def clean(self, days_threshold: int = 30, dry_run: bool = True, args: Optional[List[str]] = None) -> bool:
        """
        Main method to run the Git cleaner.
        
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
        """Check if Git is installed and accessible."""
        line = inspect.currentframe().f_lineno
        git_check = run_command("git --version")
        if git_check is None:
            logger.error(f"[Line {line}] Git is not installed or not available in PATH")
            return False
            
        # If specific repos are provided, check if they exist and are git repos
        if self.target_repos:
            valid_repos = []
            for repo_path in self.target_repos:
                line = inspect.currentframe().f_lineno
                if not os.path.isdir(repo_path):
                    logger.error(f"[Line {line}] Repository path does not exist: {repo_path}")
                    continue
                    
                line = inspect.currentframe().f_lineno
                if not self._is_git_repo(repo_path):
                    logger.error(f"[Line {line}] Not a valid Git repository: {repo_path}")
                    continue
                    
                valid_repos.append(repo_path)
                
            line = inspect.currentframe().f_lineno
            if not valid_repos:
                logger.error(f"[Line {line}] None of the specified repository paths are valid")
                return False
                
            # Update target_repos to only include valid ones
            self.target_repos = valid_repos
            
        return True

    def find_cleanable_items(self, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Find unused Git branches and stale repositories.
        
        Args:
            days_threshold: Number of days of inactivity before considering a branch/repo unused
            
        Returns:
            List of unused branches with metadata
        """
        # If specific repos are provided, use them; otherwise find stale repos
        if self.target_repos:
            # Use the specified repositories
            stale_repos = []
            for repo_path in self.target_repos:
                stale_repos.append({
                    "path": repo_path,
                    "name": os.path.basename(repo_path),
                    "last_modified": datetime.now().strftime('%Y-%m-%d'),  # Not actually stale
                    "days_inactive": 0  # Not relevant for specified repos
                })
        else:
            # Find stale repositories first
            stale_repos = self._find_stale_repos(days_threshold)
        
        # For each repo, find unused branches
        cleanable_items = []
        
        for repo in stale_repos:
            # Mark the repo as a repo item rather than a branch
            repo_item = repo.copy()
            repo_item["type"] = "repo"
            repo_item["has_branches"] = False
            
            # Only add the repo itself as a cleanable item if we're not using target_repos
            if not self.target_repos:
                cleanable_items.append(repo_item)
            
            # Now find unused branches in this repo
            unused_branches = self._get_unused_branches(repo["path"], days_threshold)
            
            if unused_branches:
                # Update the repo item to indicate it has branches
                repo_item["has_branches"] = True
                
                # Add each branch as a separate item, with a reference to its repo
                for branch in unused_branches:
                    branch["type"] = "branch"
                    branch["repo_path"] = repo["path"]
                    branch["repo_name"] = repo["name"]
                    cleanable_items.append(branch)
        
        return cleanable_items

    def clean_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Clean a specific Git resource (branch or repo).
        
        Args:
            item: The Git resource to clean
            dry_run: If True, only simulate cleaning
            
        Returns:
            True if cleaning was successful, False otherwise
        """
        line_no = inspect.currentframe().f_lineno
        if dry_run:
            return True
        
        if item["type"] == "branch":
            # Check if we should delete the branch
            if item.get("is_merged", False):
                # For merged branches, always safe to delete
                line_no = inspect.currentframe().f_lineno
                result = run_command(
                    f"git branch -d {item['name']}", 
                    cwd=item["repo_path"]
                )
                if result is None:
                    logger.error(f"[Line {line_no}] Failed to delete branch {item['name']} in {item['repo_path']}")
                    return False
                return True
            elif self.clean_unmerged:
                # For unmerged branches, only delete if clean_unmerged is enabled
                line_no = inspect.currentframe().f_lineno
                logger.warning(f"[Line {line_no}] Forcing deletion of unmerged branch: {item['name']} in {item['repo_path']}")
                result = run_command(
                    f"git branch -D {item['name']}", 
                    cwd=item["repo_path"]
                )
                if result is None:
                    logger.error(f"[Line {line_no}] Failed to force delete branch {item['name']} in {item['repo_path']}")
                    return False
                return True
            else:
                # Skip unmerged branches when clean_unmerged is disabled
                line_no = inspect.currentframe().f_lineno
                logger.info(f"[Line {line_no}] Skipping unmerged branch: {item['name']} (use --clean-unmerged to delete)")
                return False
        else:
            # We don't actually delete repositories, just report them
            line_no = inspect.currentframe().f_lineno
            logger.info(f"[Line {line_no}] Stale repository: {item['path']} (not deleting)")
            return True

    def item_to_str(self, item: Dict[str, Any]) -> str:
        """
        Convert a Git resource to a string representation.
        
        Args:
            item: The Git resource
            
        Returns:
            String representation of the resource
        """
        if item["type"] == "branch":
            merge_status = "merged" if item.get("is_merged", False) else "not merged"
            return (f"Branch: {item['name']} in {item['repo_name']} "
                   f"(inactive for {item['days_inactive']} days, {merge_status})")
        else:
            branch_info = "has unused branches" if item.get("has_branches", False) else "no unused branches"
            return (f"Repository: {item['name']} ({item['path']}) "
                   f"(inactive for {item['days_inactive']} days, {branch_info})")

    def _is_git_repo(self, path: str) -> bool:
        """
        Check if the given path is a Git repository.
        
        Args:
            path: Path to check
            
        Returns:
            True if the path is a Git repo, False otherwise
        """
        git_dir = os.path.join(path, '.git')
        return os.path.isdir(git_dir)

    def _find_git_repos(self, start_dir: str, max_depth: int = 5) -> List[str]:
        """
        Find Git repositories under the start directory up to a maximum depth.
        
        Args:
            start_dir: Directory to start searching from
            max_depth: Maximum depth to search
            
        Returns:
            List of paths to Git repositories
        """
        repos = []
        line_no = inspect.currentframe().f_lineno
        
        if max_depth <= 0:
            return repos
        
        try:
            # Check if the start directory itself is a Git repo
            if self._is_git_repo(start_dir):
                repos.append(start_dir)
                return repos  # Don't look for nested repos
            
            # Look for Git repos in subdirectories
            for item in os.listdir(start_dir):
                item_path = os.path.join(start_dir, item)
                
                # Skip hidden directories
                if item.startswith('.'):
                    continue
                    
                # Skip non-directories
                if not os.path.isdir(item_path):
                    continue
                    
                # Check if this is a Git repo
                if self._is_git_repo(item_path):
                    repos.append(item_path)
                else:
                    # Recursively search subdirectories with reduced depth
                    repos.extend(self._find_git_repos(item_path, max_depth - 1))
        except (PermissionError, OSError) as e:
            line_no = inspect.currentframe().f_lineno
            logger.error(f"[Line {line_no}] Error accessing directory {start_dir}: {e}")
        
        return repos

    def _find_stale_repos(self, days_threshold: int, base_dirs: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Find repositories that haven't been accessed in the specified time.
        
        Args:
            days_threshold: Number of days of inactivity
            base_dirs: Directories to search in, defaults to common project directories
            
        Returns:
            List of stale repositories with metadata
        """
        stale_repos = []
        
        # Default directories to search
        if not base_dirs:
            # Default to common project directories
            home_dir = os.path.expanduser("~")
            base_dirs = [
                os.path.join(home_dir, "projects"),
                os.path.join(home_dir, "code"),
                os.path.join(home_dir, "Documents", "projects"),
                os.path.join(home_dir, "work")
            ]
            # Only include directories that exist
            base_dirs = [d for d in base_dirs if os.path.isdir(d)]
            
            # If no predefined directories exist, use the home directory
            if not base_dirs:
                base_dirs = [home_dir]
        
        # Find Git repos in each base directory
        all_repos = []
        for base_dir in base_dirs:
            if os.path.isdir(base_dir):
                repos = self._find_git_repos(base_dir)
                all_repos.extend(repos)
        
        logger.info(f"Found {len(all_repos)} Git repositories to check")
        
        # Check each repo for last access time
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        
        for repo in all_repos:
            try:
                # Check when the repo was last modified
                git_dir = os.path.join(repo, '.git')
                
                # Check HEAD file's modification time as a proxy for repo activity
                head_file = os.path.join(git_dir, 'HEAD')
                if os.path.isfile(head_file):
                    last_mod_time = os.path.getmtime(head_file)
                    last_mod_date = datetime.fromtimestamp(last_mod_time)
                    
                    # Only consider repos that haven't been modified recently
                    if last_mod_date < threshold_date:
                        stale_repos.append({
                            "path": repo,
                            "name": os.path.basename(repo),
                            "last_modified": last_mod_date.strftime('%Y-%m-%d'),
                            "days_inactive": (datetime.now() - last_mod_date).days
                        })
            except (OSError, PermissionError):
                continue
        
        return stale_repos

    def _get_unused_branches(self, repo_path: str, days_threshold: int) -> List[Dict[str, Any]]:
        """
        Get list of branches that have not been modified in the specified time.
        
        Args:
            repo_path: Path to the Git repository
            days_threshold: Number of days of inactivity
            
        Returns:
            List of unused branches with metadata
        """
        line = inspect.currentframe().f_lineno
        # Make sure we're in a Git repo
        if not self._is_git_repo(repo_path):
            logger.error(f"[Line {line}] {repo_path} is not a Git repository")
            return []
            
        # Get all local branches
        line = inspect.currentframe().f_lineno
        branch_output = run_command("git branch", cwd=repo_path)
        if not branch_output:
            logger.warning(f"[Line {line}] Failed to get branches in {repo_path}")
            return []
            
        # Get the current branch
        current_branch = None
        for line in branch_output.splitlines():
            if line.startswith('*'):
                current_branch = line[1:].strip()
                break
                
        # Check each branch for its last commit date
        unused_branches = []
        line_no = inspect.currentframe().f_lineno
        
        for line in branch_output.splitlines():
            # Remove the leading * and spaces
            branch_name = line.strip()
            if branch_name.startswith('*'):
                branch_name = branch_name[1:].strip()
            
            # Skip the current branch
            if branch_name == current_branch:
                continue
                
            # Get the last commit date for this branch
            line_no = inspect.currentframe().f_lineno
            last_commit_date_output = run_command(
                f"git log -1 --format=%cd --date=iso {branch_name}", 
                cwd=repo_path
            )
            
            if not last_commit_date_output:
                logger.warning(f"[Line {line_no}] Failed to get last commit date for branch {branch_name} in {repo_path}")
                continue
                
            try:
                # Parse the date
                last_commit_date = datetime.strptime(
                    last_commit_date_output.split()[0], '%Y-%m-%d'
                )
                
                # Check if the branch is older than the threshold
                threshold_date = datetime.now() - timedelta(days=days_threshold)
                
                if last_commit_date < threshold_date:
                    # Check if the branch has been merged
                    line_no = inspect.currentframe().f_lineno
                    is_merged = run_command(
                        f"git branch --merged {current_branch} | grep -w {branch_name}",
                        cwd=repo_path
                    ) is not None
                    
                    # Get branch creation date (first commit date)
                    line_no = inspect.currentframe().f_lineno
                    first_commit_date_output = run_command(
                        f"git log --format=%cd --date=iso {branch_name} --reverse | head -1",
                        cwd=repo_path
                    )
                    
                    first_commit_date = None
                    if first_commit_date_output:
                        try:
                            first_commit_date = datetime.strptime(
                                first_commit_date_output.split()[0], '%Y-%m-%d'
                            )
                        except ValueError:
                            first_commit_date = None
                    
                    unused_branches.append({
                        "name": branch_name,
                        "last_commit": last_commit_date.strftime('%Y-%m-%d'),
                        "days_inactive": (datetime.now() - last_commit_date).days,
                        "is_merged": is_merged,
                        "created": first_commit_date.strftime('%Y-%m-%d') if first_commit_date else "Unknown"
                    })
                    
            except (ValueError, IndexError) as e:
                line_no = inspect.currentframe().f_lineno
                logger.error(f"[Line {line_no}] Error processing branch {branch_name} in {repo_path}: {e}")
                continue
        
        return unused_branches


# Register this cleaner
CLEANER_REGISTRY["git"] = GitCleaner 

def display_cleaner_help(cleaner_name: str) -> None:
    """
    Display help information for a specific cleaner.
    
    Args:
        cleaner_name: Name of the cleaner to display help for
    """
    # Create cleaner instance directly
    cleaner = GitCleaner()
    
    # Basic help text
    help_text = f"""
    {cleaner_name.upper()} Cleaner
    {'=' * (len(cleaner_name) + 8)}
    
    {cleaner.description}
    
    USAGE:
        maccleaner {cleaner_name} clean [OPTIONS]
    
    OPTIONS:
        --days DAYS      Number of days of inactivity before considering a file 
                        as unused (default: 30)
        
        --dry-run        Run in simulation mode without deleting anything
        
        --no-dry-run     Actually delete unused files (default)
        
        --verbose, -v    Enable verbose output for debugging
        
        -h, --help       Display this help information
    """
    
    # Add cleaner-specific options
    if cleaner_name == 'git':
        git_options = """
    GIT-SPECIFIC OPTIONS:
        --repo REPO      Path to a specific Git repository to clean.
                        Can be used multiple times to specify multiple repositories.
                        Example: --repo /path/to/repo1 --repo /path/to/repo2
                        
                        If not specified, the cleaner will scan common directories
                        for repositories that haven't been used in the specified
                        number of days.
                        
        --clean-unmerged Allow deletion of unmerged branches (USE WITH CAUTION!)
                        By default, only merged branches will be deleted.
    """
        help_text += git_options
    
    # Add examples
    examples = f"""
    EXAMPLES:
        # Run in dry-run mode (simulation)
        maccleaner {cleaner_name} clean --dry-run
        
        # Run with a custom threshold
        maccleaner {cleaner_name} clean --days 60
        
        # Run and actually delete files (default)
        maccleaner {cleaner_name} clean
    """
    
    # Add cleaner-specific examples
    if cleaner_name == 'git':
        git_examples = """
        # Clean a specific Git repository
        maccleaner git clean --repo /path/to/my/repo
        
        # Clean multiple repositories
        maccleaner git clean --repo /path/to/repo1 --repo /path/to/repo2
        
        # Force delete unmerged branches
        maccleaner git clean --clean-unmerged
        
        # Force delete unmerged branches in a specific repository 
        maccleaner git clean --repo /path/to/my/repo --clean-unmerged
    """
        examples += git_examples
    
    help_text += examples
    
    print(help_text) 