# MacCleaner

MacCleaner is a utility to clean unused files from various tech stacks on macOS, helping developers reclaim disk space.

## Features

- **Maven Cleaner**: Removes old artifacts from your local Maven repository
- **Docker Cleaner**: Cleans unused Docker images, containers, and volumes
- **Git Cleaner**: Removes old branches from local Git repositories
- **Kubernetes Cleaner**: Cleans up old Kubernetes resources
- **NPM Cleaner**: Removes npm caches and unused node_modules
- **Xcode Cleaner**: Cleans Xcode derived data, archives and caches
- **Homebrew Cleaner**: Cleans Homebrew caches and old versions
- **Python Cleaner**: Removes Python caches and unused virtual environments
- **iOS Simulator Cleaner**: Cleans iOS simulator devices and caches
- **Application Analyzer**: Analyzes disk usage for applications

## Installation

```shell
pip install mac-cleaner
```

### Install from Source Code

If you want to install the latest development version or customize the code, you can install from source:

```shell
# Clone the repository
git clone https://github.com/DoneSpeak/mac-cleaner.git
cd mac-cleaner
```

#### Method 1: Install using Makefile (easiest)

```shell
# Install MacCleaner (may require sudo)
make install

# Install for current user only (no sudo required)
make install USER=1

# Install in development mode
make dev-install

# Uninstall MacCleaner
make uninstall

# View all available make targets
make help
```

#### Method 2: Install using pip

```shell
# Install directly
pip install .

# Or, install in development mode (changes to the code will take effect immediately)
pip install -e .

# Or, install with development dependencies (for contributing)
pip install -e ".[dev]"
```

#### Method 3: Install using Poetry (recommended for development)

```shell
# Install Poetry if you don't have it already
# See https://python-poetry.org/docs/#installation

# Install dependencies and project
poetry install

# Activate the virtual environment
poetry shell
```

After installation, you can verify it works by running:

```shell
# Check the installed version
maccleaner --version

# List available cleaners
maccleaner list
```

## Usage

### List available cleaners and analyzers

```shell
maccleaner list
```

### Clean all supported tech stacks (simulation mode)

```shell
maccleaner clean --dry-run
```

### Clean a specific tech stack

```shell
maccleaner clean maven --dry-run
```

### Actually delete files (not just simulation)

```shell
maccleaner clean maven
```

### Analyze application disk usage

Get detailed help for the application analyzer:
```shell
maccleaner app-analyze --help-analyzer
```

Analyze all applications:
```shell
maccleaner app-analyze
```

Analyze a specific application (supports both full path and just app name):
```shell
# Using full path
maccleaner app-analyze /Applications/Safari.app

# Using just the application name (case-insensitive)
maccleaner app-analyze safari

# Using application name with .app extension
maccleaner app-analyze "Visual Studio Code.app"
```

Select output format (txt, json, or csv):
```shell
# Default human-readable text format
maccleaner app-analyze --format=txt

# JSON format for programmatic processing
maccleaner app-analyze --format=json

# CSV format for spreadsheet import
maccleaner app-analyze --format=csv
```

## Options

- `--days DAYS`: Number of days of inactivity before considering a resource unused (default: 30)
- `--dry-run`: Only simulate cleaning without actually removing files
- `--verbose, -v`: Enable verbose logging
- `--help, -h`: Show help message

## Cleaner Descriptions

- **maven**: Cleans old artifacts from your local Maven repository
- **docker**: Removes unused Docker images, containers, and volumes
- **git**: Cleans old branches from local Git repositories
- **k8s**: Removes unused Kubernetes resources (pods, replicasets, configmaps, secrets)
- **npm**: Cleans npm caches and unused node_modules directories
- **xcode**: Cleans Xcode derived data, caches, old archives, and device support files
- **brew**: Cleans Homebrew caches, downloads, and outdated package versions
- **python**: Cleans Python caches, __pycache__ directories, and old virtual environments
- **simulator**: Cleans unused iOS simulator devices, old runtimes, and caches

## Analyzer Descriptions

- **app_analyzer**: Analyzes disk usage for applications and their associated data

## Example Output from Application Analyzer

```
=== Application Disk Usage Analysis ===
Total apps analyzed: 121
Total disk usage: 15.24 GB

1. Visual Studio Code - 2.15 GB
   Bundle ID: com.microsoft.VSCode
   Location: /Applications/Visual Studio Code.app
   Disk usage by type:
     - Application bundle: 684.25 MB (31.8%)
     - App containers: 712.42 MB (33.1%)
     - Application support files: 625.35 MB (29.1%)
     - Cache files: 118.55 MB (5.5%)
     - Preferences: 10.28 MB (0.5%)

2. Xcode - 1.85 GB
   Bundle ID: com.apple.dt.Xcode
   Location: /Applications/Xcode.app
   Disk usage by type:
     - Application bundle: 1.64 GB (88.6%)
     - Application support files: 132.56 MB (7.0%)
     - Cache files: 65.32 MB (3.5%)
     - Crash reports: 12.45 MB (0.7%)
     - Preferences: 4.15 MB (0.2%)
...
```

## Development

### Requirements

- Python 3.6+
- macOS environment

### Project Structure

```
mac-cleaner/
├── maccleaner/             # Main package
│   ├── core/               # Core functionality
│   ├── cleaners/           # Individual cleaners
│   ├── analyzers/          # Analyzers
│   └── cli.py              # Command-line interface
├── tests/                  # Test suite
├── pyproject.toml          # Poetry configuration
└── README.md               # This file
```

### Local Development Setup

```shell
# Clone the repository
git clone https://github.com/DoneSpeak/mac-cleaner.git
cd mac-cleaner

# Method 1: Using pip with virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"

# Method 2: Using Poetry (recommended)
poetry install
poetry shell

# Run tests
pytest
```

### Contributing

Contributions are welcome! Here's how you can contribute:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Run tests to ensure they pass: `pytest`
5. Commit your changes: `git commit -m "Add some feature"`
6. Push to the branch: `git push origin feature-name`
7. Create a pull request

Please make sure to update tests as appropriate and follow the code style of the project.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Log Level Control

MacCleaner provides three levels of logging control:

- Default mode: Shows only results, no log messages (ERROR level)
- Verbose mode (`-v` or `--verbose`): Displays general information logs (INFO level)
- Debug mode (`-X` or `--debug`): Shows all detailed debug logs (DEBUG level)

Examples:
```bash
# Default mode - displays only results
python -m maccleaner.cli app-analyze safari

# Verbose mode - displays INFO level logs
python -m maccleaner.cli -v app-analyze safari

# Debug mode - displays all DEBUG level logs
python -m maccleaner.cli -X app-analyze safari
```

## Notes and Error Handling

MacCleaner implements several optimizations when processing multiple applications:

1. **Single-app analysis optimization** - When specifying a single application, it only analyzes the target app without scanning all applications
2. **Timeout protection** - Sets a 5-second timeout limit when parsing application information to prevent program freezes due to invalid plist files
3. **Error tolerance** - Failure to analyze a single application doesn't affect the overall analysis process
4. **Progress display** - Shows progress information when analyzing all applications
5. **Compatibility handling** - Processes various plist file formats, including binary and XML formats, and attempts multiple methods to extract information

If you encounter problems when analyzing all applications, try these solutions:
- Use the `-v` or `-X` parameter to view detailed logs and identify specific issues
- Specify analysis for a single application to avoid processing all applications
- Check if the application's Info.plist file is corrupted