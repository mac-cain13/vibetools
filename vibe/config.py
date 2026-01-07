"""Configuration constants for vibe."""

from pathlib import Path

# Worktree base directories
LOCAL_WORKTREE_BASE = Path("/Volumes/External/Repositories/_vibecoding")
REMOTE_WORKTREE_BASE = Path("/Volumes/_vibecoding")

# SSH configuration
SSH_KEY_PATH = Path.home() / ".ssh" / "id_vibecoding"
SSH_USER_HOST = "admin@vibecoding.local"

# Default coding tool command
CODING_TOOL_CMD = "cly"
