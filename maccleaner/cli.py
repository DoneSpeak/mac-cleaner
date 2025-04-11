#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Command-line interface for MacCleaner.

This module provides the main command-line interface for the MacCleaner tool, using
argparse to parse arguments and subcommands.
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import List, Optional, Dict, Any, Type

from maccleaner.core.cleaner import Cleaner
from maccleaner.core.analyzer import Analyzer
from maccleaner.cleaners import CLEANER_REGISTRY
from maccleaner.analyzers import ANALYZER_REGISTRY
from maccleaner import __version__

# Configure logging
logger = logging.getLogger("maccleaner")


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """
    Set up logging configuration.
    
    Args:
        verbose: Whether to enable verbose logging (INFO level)
        debug: Whether to enable debug logging (DEBUG level)
    """
    if debug:
        log_level = logging.DEBUG
    elif verbose:
        log_level = logging.INFO
    else:
        log_level = logging.ERROR  # 默认只显示错误级别日志
    
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure root logger
    logging.basicConfig(level=log_level, format=log_format)
    
    # Set log level for requests and urllib3 to WARNING to reduce noise
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_available_cleaners() -> Dict[str, Type[Cleaner]]:
    """
    Get available cleaners.
    
    Returns:
        Dictionary mapping cleaner names to cleaner classes
    """
    return CLEANER_REGISTRY


def get_available_analyzers() -> Dict[str, Type[Analyzer]]:
    """
    Get available analyzers.
        
    Returns:
        Dictionary mapping analyzer names to analyzer classes
    """
    return ANALYZER_REGISTRY


def create_parser() -> argparse.ArgumentParser:
    """
    Create the command-line argument parser.
        
    Returns:
        Configured argument parser
    """
    parser = argparse.ArgumentParser(
        description="MacCleaner - A utility to clean unused files from various tech stacks on macOS"
    )
    parser.add_argument(
        "--version", action="version", version=f"MacCleaner {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging (INFO level)"
    )
    parser.add_argument(
        "-X", "--debug", action="store_true", help="Enable debug logging (DEBUG level)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List available cleaners and analyzers")
    
    # Help command - 可以保留这个，作为专用获取特定cleaner帮助的命令
    help_parser = subparsers.add_parser("help", help="Show detailed help for a specific cleaner")
    help_parser.add_argument(
        "cleaner", choices=get_available_cleaners().keys(),
        help="Specific cleaner to show help for"
    )
    
    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Clean unused files")
    clean_parser.add_argument(
        "--days", type=int, default=30,
        help="Number of days of inactivity before considering a resource unused"
    )
    clean_parser.add_argument(
        "--dry-run", action="store_true",
        help="Only simulate cleaning without actually removing files"
    )
    clean_parser.add_argument(
        "cleaner", nargs="?", choices=get_available_cleaners().keys(),
        help="Specific cleaner to run (if not specified, run all). Use 'clean <cleaner> -h' for detailed help."
    )
    
    # Analyze app command
    analyze_parser = subparsers.add_parser("app-analyze", help="Analyze application disk usage")
    analyze_parser.add_argument(
        "--help-analyzer", action="store_true",
        help="Show detailed help for app analyzer"
    )
    analyze_parser.add_argument(
        "target", nargs="?", type=str,
        help="Application to analyze (full path or just name). If not specified, analyze all applications"
    )
    analyze_parser.add_argument(
        "--format", type=str, choices=["txt", "json", "csv"], default="txt",
        help="Output format: txt (human-readable), json, or csv (default: txt)"
    )
    
    return parser


def run_cleaner(cleaner_name: str, days_threshold: int, dry_run: bool, args: Optional[List[str]] = None) -> bool:
    """
    Run a specific cleaner.
    
    Args:
        cleaner_name: Name of the cleaner to run
        days_threshold: Number of days of inactivity
        dry_run: Whether to simulate cleaning
        args: Additional arguments to pass to the cleaner
        
    Returns:
        True if cleaning was successful, False otherwise
    """
    cleaner_class = get_available_cleaners().get(cleaner_name)
    if not cleaner_class:
        logger.error(f"Cleaner '{cleaner_name}' not found")
        return False
    
    logger.info(f"Running cleaner: {cleaner_name}")
    cleaner = cleaner_class()
    
    try:
        result = cleaner.clean(days_threshold, dry_run, args)
        return result
    except Exception as e:
        logger.error(f"Error running cleaner '{cleaner_name}': {e}")
        logger.debug("Exception details:", exc_info=True)
        return False


def run_analyzer(analyzer_name: str, target: Optional[str] = None, output_format: str = "txt") -> bool:
    """
    Run a specific analyzer.
    
    Args:
        analyzer_name: Name of the analyzer to run
        target: Optional target to analyze
        output_format: Output format (txt, json, or csv)
        
    Returns:
        True if analysis was successful, False otherwise
    """
    analyzer_class = get_available_analyzers().get(analyzer_name)
    if not analyzer_class:
        logger.error(f"Analyzer '{analyzer_name}' not found")
        return False
    
    logger.info(f"Running analyzer: {analyzer_name}")
    logger.debug(f"Target: {target}, Output format: {output_format}")
    
    try:
        # Create the analyzer instance
        analyzer = analyzer_class()
        logger.debug(f"Created analyzer instance: {analyzer.__class__.__name__}")
        
        # Check prerequisites first
        logger.debug("Checking analyzer prerequisites...")
        if not analyzer.check_prerequisites():
            logger.error(f"Analyzer prerequisites not met for {analyzer_name}")
            return False
            
        # Run the analysis
        logger.debug(f"Starting analysis with target: {target}")
        result = analyzer.analyze(target)
        logger.debug(f"Analysis complete, got result with keys: {list(result.keys())}")
        
        # Generate and print the report in the requested format
        try:
            logger.debug(f"Generating report in {output_format} format")
            report = analyzer.generate_report(result, output_format)
            print(report)
        except Exception as e:
            logger.error(f"Failed to generate report in {output_format} format: {e}")
            logger.debug("Exception details:", exc_info=True)
            return False
            
        return result.get("success", False)
    except Exception as e:
        logger.error(f"Error running analyzer '{analyzer_name}': {e}")
        logger.debug("Exception details:", exc_info=True)
        
        # Add more detailed error information
        if isinstance(e, json.JSONDecodeError):
            logger.error(f"JSON parsing error at position {e.pos}: {e.msg}")
            logger.debug(f"Error document: {e.doc[:100]}...")
        elif isinstance(e, TypeError):
            logger.error(f"Type error: {e}")
            logger.debug(f"Error occurred during {e.__traceback__.tb_frame.f_code.co_name}")
        elif isinstance(e, AttributeError):
            logger.error(f"Attribute error: {e}")
            logger.debug(f"Error occurred during {e.__traceback__.tb_frame.f_code.co_name}")
        elif isinstance(e, (FileNotFoundError, PermissionError, OSError)):
            logger.error(f"File operation error: {e}")
            
        return False


def display_analyzer_help() -> None:
    """Display detailed help for the application analyzer."""
    help_text = """
MacCleaner Application Analyzer Help
===================================

The Application Analyzer is a tool to analyze disk usage of applications on your macOS system.
It identifies various types of data associated with applications and calculates their sizes.
    
    USAGE:
    maccleaner app-analyze [OPTIONS] [target]
    
    OPTIONS:
    --help-analyzer   Display this help information
    --format=FORMAT   Output format: txt (default), json, or csv

ARGUMENTS:
    target            Application to analyze. Can be specified in several ways:
                      - Full path: /Applications/Safari.app
                      - Just name: safari (case-insensitive)
                      - With .app: Safari.app
                      If not specified, all applications will be analyzed.

DATA ANALYZED:
    - Application bundle size
    - Cache files (~/Library/Caches)
    - Application support files (~/Library/Application Support)
    - Preference files (~/Library/Preferences)
    - Log files (~/Library/Logs)
    - App containers (~/Library/Containers)
    - Saved application state (~/Library/Saved Application State)
    - Crash reports (~/Library/Logs/DiagnosticReports)
    
    EXAMPLES:
    # Analyze all applications
    maccleaner app-analyze

    # Analyze a specific application by name
    maccleaner app-analyze safari

    # Analyze a specific application with full path
    maccleaner app-analyze /Applications/Safari.app

    # Get JSON output for a specific application
    maccleaner app-analyze safari --format=json

    # Get CSV output for a specific application
    maccleaner app-analyze safari --format=csv

    # Display this help information
    maccleaner app-analyze --help-analyzer
"""
    print(help_text)


def main(args: Optional[List[str]] = None) -> int:
    """
    Main entry point for the application.
    
    Args:
        args: Command-line arguments (if None, use sys.argv)
        
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # 如果args为None，使用sys.argv[1:]
    if args is None:
        prog_name = os.path.basename(sys.argv[0]) if len(sys.argv) > 0 else "maccleaner"
        args = sys.argv[1:] if len(sys.argv) > 1 else []
    else:
        prog_name = "maccleaner"  # 当明确提供args时，使用默认名称
    
    # 直接处理版本参数
    if args and len(args) == 1 and args[0] in ['--version', '-V']:
        print(f"MacCleaner {__version__}")
        return 0
    
    # 创建parser和subparsers
    parser = create_parser()
    parser.prog = prog_name  # 设置程序名称
    
    # 没有命令时显示帮助
    if len(args) == 0:
        parser.print_help()
        return 0
    
    # 特殊处理子命令的帮助
    if len(args) >= 2:
        # 处理clean子命令帮助
        if args[0] == 'clean' and len(args) == 2 and args[1] in ['-h', '--help']:
            cmd_help = f"""
usage: {prog_name} clean [-h] [--days DAYS] [--dry-run] [{",".join(get_available_cleaners().keys())}]

Clean unused files from various tech stacks.

positional arguments:
  {{{",".join(get_available_cleaners().keys())}}}
                        Specific cleaner to run (if not specified, run all). 
                        Use 'clean <cleaner> -h' for detailed help.

options:
  -h, --help            show this help message and exit
  --days DAYS           Number of days of inactivity before considering a resource unused (default: 30)
  --dry-run             Only simulate cleaning without actually removing files

Examples:
  # Run all cleaners in dry-run mode
  {prog_name} clean --dry-run

  # Clean old Git branches
  {prog_name} clean git

  # Clean Homebrew items older than 60 days
  {prog_name} clean brew --days 60
            """
            print(cmd_help)
            return 0
            
        # 处理app-analyze子命令帮助
        elif args[0] == 'app-analyze' and len(args) == 2 and args[1] in ['-h', '--help']:
            cmd_help = f"""
usage: {prog_name} app-analyze [-h] [--help-analyzer] [--format {{txt,json,csv}}] [target]

Analyze application disk usage.

positional arguments:
  target                Application to analyze (full path or just name). 
                        If not specified, analyze all applications.

options:
  -h, --help            show this help message and exit
  --help-analyzer       Show detailed help for app analyzer
  --format {{txt,json,csv}}
                        Output format: txt (human-readable), json, or csv (default: txt)

Examples:
  # Analyze all applications
  {prog_name} app-analyze

  # Analyze a specific application
  {prog_name} app-analyze safari

  # Get JSON output for a specific application
  {prog_name} app-analyze safari --format=json
            """
            print(cmd_help)
            return 0
            
        # 处理特定cleaner的帮助
        elif args[0] == 'clean' and len(args) >= 3 and (args[2] == '-h' or args[2] == '--help'):
            cleaner_name = args[1]
            cleaner_class = get_available_cleaners().get(cleaner_name)
            if cleaner_class:
                cleaner = cleaner_class()
                if hasattr(cleaner, 'display_help') and callable(getattr(cleaner, 'display_help')):
                    cleaner.display_help()
                    return 0
    
    # 常规解析参数
    parsed_args = parser.parse_args(args)
    
    # Set up logging
    setup_logging(parsed_args.verbose, parsed_args.debug)
    
    if parsed_args.command == "list":
        print("Available cleaners:")
        for name, cleaner_class in sorted(get_available_cleaners().items()):
            cleaner = cleaner_class()
            print(f"  - {name}: {cleaner.description}")
        
        print("\nAvailable analyzers:")
        for name, analyzer_class in sorted(get_available_analyzers().items()):
            analyzer = analyzer_class()
            print(f"  - {name}: {analyzer.description}")
        
        return 0
    elif parsed_args.command == "help":
        # Handle help command
        cleaner_class = get_available_cleaners().get(parsed_args.cleaner)
        if cleaner_class:
            cleaner = cleaner_class()
            if hasattr(cleaner, 'display_help') and callable(getattr(cleaner, 'display_help')):
                cleaner.display_help()
                return 0
            else:
                print(f"No detailed help available for {parsed_args.cleaner} cleaner")
                return 1
        return 1
    elif parsed_args.command == "clean":
        # If no cleaner specified, run all of them
        if parsed_args.cleaner:
            cleaners_to_run = [parsed_args.cleaner]
        else:
            cleaners_to_run = get_available_cleaners().keys()
        
        # Run the specified cleaners
        success = True
        for cleaner_name in cleaners_to_run:
            cleaner_success = run_cleaner(
                cleaner_name, parsed_args.days, parsed_args.dry_run, args
            )
            if not cleaner_success:
                logger.warning(f"Cleaner '{cleaner_name}' failed")
                success = False
        
        return 0 if success else 1
    elif parsed_args.command == "app-analyze":
        # Handle app-analyze help command
        if parsed_args.help_analyzer:
            display_analyzer_help()
            return 0
            
        # Default case - run the analyzer    
        success = run_analyzer("app_analyzer", parsed_args.target, parsed_args.format)
        return 0 if success else 1
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main()) 