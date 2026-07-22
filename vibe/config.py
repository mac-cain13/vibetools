"""Configuration constants for vibe."""

from __future__ import annotations

from pathlib import Path

from vibe.platform import Platform, Shell, detect_platform

_platform = detect_platform()

# Platform-specific configuration
if _platform == Platform.MACOS:
    # Repository base directories (aligned paths for git compatibility)
    LOCAL_REPO_BASE = Path("/Volumes/External/Repositories")
    REMOTE_REPO_BASE = Path("/Volumes/External/Repositories")

    # Default VM for local development. Local VMs are addressed by their tart
    # name (resolved to a fresh IP via `tart ip`), NOT by mDNS — this keeps
    # cloned VMs unambiguous even though they share the vibecoding.local guest
    # hostname. Override per-invocation with --vm/--host or $VIBE_VM.
    DEFAULT_VM: str | None = "vibecoding"

    # SSH configuration. Legacy mDNS host — no longer used for the default path
    # (see DEFAULT_VM); kept as the source of the default SSH username and as an
    # explicit escape hatch (`--host admin@vibecoding.local`).
    SSH_USER_HOST = "admin@vibecoding.local"

    # macOS keychain unlock (needed for Xcode code signing over SSH)
    UNLOCK_KEYCHAIN = True
    KEYCHAIN_COMMAND = (
        "security -v unlock-keychain -p admin ~/Library/Keychains/login.keychain-db"
    )

    # Platform-specific junk files to ignore when checking empty directories
    JUNK_FILES = [".DS_Store"]

    # SSH lands directly in macOS shell, no wrapper needed
    REMOTE_IS_WINDOWS = False
    DEFAULT_REMOTE_SHELL: Shell | None = None

else:  # WSL
    # Repository base directories (/mnt/z is the host's Repositories share)
    LOCAL_REPO_BASE = Path("/mnt/z")
    REMOTE_REPO_BASE = Path("/mnt/z")

    # No tart on Windows/WSL hosts — connect to the static host directly.
    DEFAULT_VM: str | None = None

    # SSH configuration
    SSH_USER_HOST = "admin@172.21.0.10"

    # No keychain on Windows/WSL
    UNLOCK_KEYCHAIN = False
    KEYCHAIN_COMMAND = None

    # Platform-specific junk files to ignore when checking empty directories
    JUNK_FILES = ["Thumbs.db", "desktop.ini"]

    # SSH lands in Windows — shell choice (WSL or PowerShell) made at runtime
    REMOTE_IS_WINDOWS = True
    DEFAULT_REMOTE_SHELL = Shell.WSL

# Shared configuration (same on all platforms)

# Worktree base directories (inside repo base)
LOCAL_WORKTREE_BASE = LOCAL_REPO_BASE / "_vibecoding"
REMOTE_WORKTREE_BASE = REMOTE_REPO_BASE / "_vibecoding"

# Parked work lives on the NSProject board (discovered at runtime), not in a
# flat store — see vibe/nsproject.py and docs/nsproject-park.md.

# SSH key path
SSH_KEY_PATH = Path.home() / ".ssh" / "id_vibecoding"

# Coding tool commands (wrapper scripts — used in WSL shell)
CLAUDE_CODE_CMD = "cly"      # Claude Code wrapper
CODEX_CMD = "cdx"            # Codex wrapper
OPEN_CODE_CMD = "opencode"   # OpenCode (direct invocation)

# Direct coding tool commands (no wrappers — used in PowerShell)
CLAUDE_CODE_DIRECT_CMD = "claude --dangerously-skip-permissions"
CODEX_DIRECT_CMD = "codex --dangerously-bypass-approvals-and-sandbox"
OPEN_CODE_DIRECT_CMD = "opencode"


def wsl_path_to_windows(path: Path) -> str:
    """Convert a WSL /mnt/x/... path to Windows X:\\... format.

    Args:
        path: WSL-style path (e.g., /mnt/z/_vibecoding/repo/branch)

    Returns:
        Windows-style path string (e.g., Z:\\_vibecoding\\repo\\branch)
    """
    parts = path.parts  # ('/', 'mnt', 'z', '_vibecoding', ...)
    if len(parts) >= 3 and parts[1] == "mnt":
        drive = parts[2].upper()
        rest = "\\".join(parts[3:])
        return f"{drive}:\\{rest}" if rest else f"{drive}:\\"
    # Fallback: return as-is
    return str(path)
