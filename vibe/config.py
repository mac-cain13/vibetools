"""Configuration constants for vibe."""

from pathlib import Path

# Repository base directories (aligned paths for git compatibility)
LOCAL_REPO_BASE = Path("/Volumes/External/Repositories")
REMOTE_REPO_BASE = Path("/Volumes/External/Repositories")

# Worktree base directories (inside repo base)
LOCAL_WORKTREE_BASE = LOCAL_REPO_BASE / "_vibecoding"
REMOTE_WORKTREE_BASE = REMOTE_REPO_BASE / "_vibecoding"

# SSH configuration
SSH_KEY_PATH = Path.home() / ".ssh" / "id_vibecoding"
SSH_USER_HOST = "admin@vibecoding.local"

# Coding tool commands
CLAUDE_CODE_CMD = "cly"      # Claude Code wrapper
CODEX_CMD = "cdx"            # Codex wrapper
OPEN_CODE_CMD = "opencode"   # OpenCode (direct invocation)
