"""Configuration constants for vibe."""

from pathlib import Path

from vibe.platform import Platform, detect_platform

_platform = detect_platform()

# Platform-specific configuration
if _platform == Platform.MACOS:
    # Repository base directories (aligned paths for git compatibility)
    LOCAL_REPO_BASE = Path("/Volumes/External/Repositories")
    REMOTE_REPO_BASE = Path("/Volumes/External/Repositories")

    # SSH configuration
    SSH_USER_HOST = "admin@vibecoding.local"

    # macOS keychain unlock (needed for Xcode code signing over SSH)
    UNLOCK_KEYCHAIN = True
    KEYCHAIN_COMMAND = (
        "security -v unlock-keychain -p admin ~/Library/Keychains/login.keychain-db"
    )

    # Platform-specific junk files to ignore when checking empty directories
    JUNK_FILES = [".DS_Store"]

    # SSH lands directly in macOS shell, no wrapper needed
    REMOTE_WSL_WRAPPER = False

else:  # WSL
    # Repository base directories
    LOCAL_REPO_BASE = Path.home() / "Repositories"
    REMOTE_REPO_BASE = Path("/mnt/repos")

    # SSH configuration
    SSH_USER_HOST = "admin@172.21.0.10"

    # No keychain on Windows/WSL
    UNLOCK_KEYCHAIN = False
    KEYCHAIN_COMMAND = None

    # Platform-specific junk files to ignore when checking empty directories
    JUNK_FILES = ["Thumbs.db", "desktop.ini"]

    # SSH lands in Windows, need wsl -e to enter WSL
    REMOTE_WSL_WRAPPER = True

# Shared configuration (same on all platforms)

# Worktree base directories (inside repo base)
LOCAL_WORKTREE_BASE = LOCAL_REPO_BASE / "_vibecoding"
REMOTE_WORKTREE_BASE = REMOTE_REPO_BASE / "_vibecoding"

# SSH key path
SSH_KEY_PATH = Path.home() / ".ssh" / "id_vibecoding"

# Coding tool commands
CLAUDE_CODE_CMD = "cly"      # Claude Code wrapper
CODEX_CMD = "cdx"            # Codex wrapper
OPEN_CODE_CMD = "opencode"   # OpenCode (direct invocation)
