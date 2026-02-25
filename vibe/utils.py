"""Shared utilities for vibe."""

from __future__ import annotations

from pathlib import Path
from rich.console import Console

from vibe.config import JUNK_FILES

# Shared console instance for consistent output
console = Console()


def is_junk_file(name: str) -> bool:
    """Check if a filename is a platform-specific junk file.

    Args:
        name: Filename to check

    Returns:
        True if the file is a known junk file
    """
    return name in JUNK_FILES


def is_directory_empty(directory: Path) -> bool:
    """Check if directory is empty, ignoring platform-specific junk files.

    Args:
        directory: Path to check

    Returns:
        True if directory is empty (or only contains junk files), False otherwise
    """
    if not directory.is_dir():
        return False

    for item in directory.iterdir():
        if not is_junk_file(item.name):
            return False
    return True
