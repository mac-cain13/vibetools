"""Shared utilities for vibe."""

from __future__ import annotations

from pathlib import Path
from rich.console import Console

# Shared console instance for consistent output
console = Console()


def is_directory_empty(directory: Path) -> bool:
    """Check if directory is empty, ignoring .DS_Store files.

    Args:
        directory: Path to check

    Returns:
        True if directory is empty (or only contains .DS_Store), False otherwise
    """
    if not directory.is_dir():
        return False

    for item in directory.iterdir():
        if item.name != ".DS_Store":
            return False
    return True
