"""Configuration constants for vibe."""

from pathlib import Path

# Worktree base directories
LOCAL_WORKTREE_BASE = Path("/Volumes/External/Repositories/_vibecoding")
REMOTE_WORKTREE_BASE = Path("/Volumes/_vibecoding")

# SSH configuration
SSH_KEY_PATH = Path.home() / ".ssh" / "id_vibecoding"
SSH_USER_HOST = "admin@vibecoding.local"

# Coding tool commands
CLOUD_CODE_CMD = "cly"       # Cloud code wrapper
OPEN_CODE_CMD = "opencode"   # Open code (direct invocation)

# Default coding tool (for backwards compatibility)
CODING_TOOL_CMD = CLOUD_CODE_CMD
