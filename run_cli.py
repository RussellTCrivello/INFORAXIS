"""
Entry point for the CLI application.

DEPRECATED as an operational interface: the web frontend is the primary
control surface (Input / Ingestion page). This script is kept as a thin
compatibility adapter over the same IngestionService the frontend uses -
no business logic lives here anymore.
"""

import sys
import multiprocessing
from pathlib import Path

# Windows-native console safety (redirected output uses legacy code pages)
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

# Set multiprocessing start method (Windows uses 'spawn' by default)
if __name__ == '__main__':
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # Already set, ignore

# Simplified initialization
from core.init import (
    setup_project_path,
    initialize_settings,
    initialize_database_config,
    initialize_system
)

# Set up project path
project_root = setup_project_path(__file__)

# Initialize settings
initialize_settings(project_root)

# Load database configuration
initialize_database_config()

# Initialize system
initialize_system()

if __name__ == '__main__':
    # Compatibility adapter: with arguments -> non-interactive service run;
    # with no arguments -> the legacy interactive flow (deprecated).
    from apps.cli.main import cli_main, main

    if len(sys.argv) > 1:
        sys.exit(cli_main())
    main()
else:
    # When imported by multiprocessing child process, ensure path is set up
    setup_project_path()
