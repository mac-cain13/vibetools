# vibe

A git worktree manager for seamless remote development sessions. Create isolated branch environments and connect instantly to your remote coding setup.

## Why vibe?

Working on multiple branches simultaneously requires constant context switching, stashing, and branch management overhead. **vibe** eliminates this friction by:

- **Instant branch isolation** - Each branch gets its own worktree directory
- **Zero context switching** - No more `git checkout` dance between features
- **Remote-first workflow** - Automatic SSH connection to your development machine
- **Clean workspace management** - Built-in cleanup for completed work

Perfect for developers juggling multiple features, bug fixes, or experiments who want to maintain flow state.

## Installation

Requires Python 3.9+.

### Recommended: Using the install script

The install script uses [uv](https://docs.astral.sh/uv/) for fast, reliable installation:

```bash
./install.sh
```

This will:
1. Install `uv` if not present
2. Install `vibe` as a global tool

### Manual installation

```bash
# With pip
pip install -e .

# With uv
uv tool install .

# With development dependencies
pip install -e ".[dev]"
```

After installation, the `vibe` command is available globally.

## Quick Start

```bash
# Create worktree and connect to remote with coding tool
vibe feature-branch

# Create worktree from a specific base branch
vibe feature-branch --from main

# Create worktree from a remote branch (auto-creates tracking branch)
vibe origin/feature-branch

# Connect with just a shell (no coding tool)
vibe --cli feature-branch

# Connect to remote home directory (no worktree)
vibe --cli

# Work locally instead of SSH
vibe --local feature-branch

# Clean up a specific worktree
vibe --clean feature-branch

# Clean up all worktrees across all repos
vibe --clean
```

## How It Works

1. **Worktree Creation** - Creates git worktrees in organized directory structure:
   ```
   /Volumes/External/Repositories/_vibecoding/
   └── your-repo/
       ├── main/
       ├── feature-1/
       └── hotfix-bug/
   ```

2. **Smart Branch Handling**:
   - **Existing local branches** - Uses existing worktree or creates one
   - **Remote branches** (`origin/branch`) - Creates local tracking branch automatically
   - **New branch names** - Creates new branch from current HEAD
   - **`--from` flag** - Creates new branch from specified base branch

3. **Remote Connection** - SSH to your development machine and automatically:
   - Navigate to the worktree directory
   - Unlock macOS keychain for git operations
   - Launch your coding environment (`cly` by default)

## CLI Reference

```
vibe [OPTIONS] [BRANCH]

Arguments:
  BRANCH    Branch name for the worktree. Creates worktree and connects to it.
            Supports origin/branch syntax for remote branches.

Options:
  --cli          Connect to remote CLI (shell only, without coding tool).
                 If no branch specified, connects to home directory.
  --local        Work locally instead of SSH to remote. Requires branch name.
  --clean        Clean worktrees. Without branch, cleans all.
                 With branch, cleans specific worktree.
  --from TEXT    Base branch to create new branch from.
  -h, --help     Show help message and exit.
```

## Cleanup Behavior

The `--clean` command provides intelligent worktree cleanup:

```bash
# Clean all worktrees (with safety checks)
vibe --clean

# Clean a specific worktree
vibe --clean feature-branch
```

**Safety features:**
- Skips worktrees with uncommitted changes (shown in yellow)
- Removes lingering directories that aren't valid worktrees
- Cleans up empty parent directories automatically
- Shows summary with cleaned/skipped/failed counts

**Example output:**
```
Cleaning worktrees in /Volumes/External/Repositories/_vibecoding

my-repo
  ● feature-1 — cleaned
  ○ feature-2 — skipped (uncommitted changes)
  ● old-branch — cleaned + parent

Summary: 2 cleaned · 1 skipped
```

## Configuration

Edit the constants in `vibe/config.py` for your setup:

```python
from pathlib import Path

# Worktree base directories
LOCAL_WORKTREE_BASE = Path("/your/local/path/_vibecoding")
REMOTE_WORKTREE_BASE = Path("/your/remote/path/_vibecoding")

# SSH configuration
SSH_USER_HOST = "user@your-dev-machine.local"
SSH_KEY_PATH = Path.home() / ".ssh" / "your_key"

# Default coding tool command
CODING_TOOL_CMD = "cly"  # or "code", "nvim", etc.
```

## Features

- **Tab completion** for branch names and worktree management
- **Safety checks** prevent cleaning worktrees with uncommitted changes
- **Remote branch support** - Use `origin/branch` to create tracking branches
- **Flexible base branches** - Create new branches from any local or remote branch
- **Batch cleanup** - Remove multiple completed worktrees at once
- **Lingering directory cleanup** - Removes invalid directories in worktree base
- **Rich terminal output** - Colored status messages and progress indicators
- **SSH error handling** - Helpful messages for connection failures
- **macOS keychain integration** - Automatic keychain unlock on remote connection

## Prerequisites

- Python 3.9+
- Git with worktree support
- SSH access to remote development machine
- Shared filesystem or sync between local/remote worktree paths

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python3 -m pytest tests/ -v

# Run tests with coverage
python3 -m pytest tests/ -v --cov=vibe --cov-report=term-missing
```

---

*Get in the right coding vibe, faster.*
