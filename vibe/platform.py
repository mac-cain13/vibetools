"""Platform detection for vibe."""

from __future__ import annotations

import os
import sys
from enum import Enum


class Platform(Enum):
    """Supported platforms."""

    MACOS = "macos"
    WSL = "wsl"


def detect_platform() -> Platform:
    """Detect the current platform.

    Detection order:
    1. VIBE_PLATFORM environment variable (for testing/override)
    2. sys.platform == "darwin" → MACOS
    3. /proc/version contains "microsoft" or "WSL" → WSL
    4. sys.platform == "linux" → WSL (assumed to be WSL on Linux)
    5. Fallback → MACOS

    Returns:
        Detected Platform enum value
    """
    # Allow explicit override via environment variable
    env_override = os.environ.get("VIBE_PLATFORM", "").lower()
    if env_override == "wsl":
        return Platform.WSL
    if env_override == "macos":
        return Platform.MACOS

    # macOS detection
    if sys.platform == "darwin":
        return Platform.MACOS

    # WSL detection via /proc/version
    if sys.platform == "linux":
        try:
            with open("/proc/version", "r") as f:
                version_info = f.read().lower()
            if "microsoft" in version_info or "wsl" in version_info:
                return Platform.WSL
        except OSError:
            pass
        # Linux but not WSL — assume WSL for this project's use case
        return Platform.WSL

    # Fallback to macOS
    return Platform.MACOS
