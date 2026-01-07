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
# Connect to current repo or worktree (prompts for coding tool)
vibe

# Create worktree and connect (prompts for coding tool)
vibe feature-branch

# Create worktree with cloud code (cly)
vibe feature-branch --cc

# Create worktree with open code (opencode)
vibe feature-branch --oc

# Create worktree from a specific base branch
vibe feature-branch --from main

# Create worktree from a remote branch (auto-creates tracking branch)
vibe origin/feature-branch

# Connect with just a shell (no coding tool)
vibe --cli feature-branch

# Connect to remote home directory (no worktree)
vibe --cli

# Work locally instead of SSH
vibe --local feature-branch --cc

# Clean up a specific worktree
vibe --clean feature-branch

# Clean up all worktrees across all repos
vibe --clean
```

### Context-Aware Behavior

**vibe** automatically detects your current git context:

- **In a main repository**: `vibe` connects to that repository on the remote machine
- **In a worktree**: `vibe` connects to that worktree on the remote machine
- **Creating branches from a worktree**: `vibe new-branch` branches from the worktree's current HEAD (not the main repo)

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
   - Launch your coding environment (cloud code or open code)

## CLI Reference

```
vibe [OPTIONS] [BRANCH]

Arguments:
  BRANCH    Branch name for the worktree. Creates worktree and connects to it.
            Supports origin/branch syntax for remote branches.
            If omitted, connects to current repo/worktree context.

Options:
  --oc           Use open code (opencode) as the coding tool.
  --cc           Use cloud code (cly) as the coding tool.
  --cli          Connect to remote CLI (shell only, without coding tool).
                 If no branch specified, connects to home directory.
  --local        Work locally instead of SSH to remote. Requires branch name.
  --clean        Clean worktrees. Without branch, cleans all.
                 With branch, cleans specific worktree.
  --from TEXT    Base branch to create new branch from.
  -h, --help     Show help message and exit.
```

When neither `--oc` nor `--cc` is specified, vibe prompts you to select a coding tool using an arrow-key menu.

### No-Argument Behavior

When you run `vibe` without a branch name:

| Context | Behavior |
|---------|----------|
| In main repo | Connects to that repo on the remote machine |
| In worktree | Connects to that worktree on the remote machine |
| Not in git | Shows error: "Not in a git repository" |

### Worktree-Aware Branching

When creating a new branch from inside an existing worktree:

```bash
# From inside a worktree - branches from worktree's HEAD
vibe new-feature

# Override with --from to branch from a specific base
vibe new-feature --from main
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

# Repository base directories (must match on both host and VM for git to work)
LOCAL_REPO_BASE = Path("/Volumes/External/Repositories")
REMOTE_REPO_BASE = Path("/Volumes/External/Repositories")

# Worktree base directories (inside repo base)
LOCAL_WORKTREE_BASE = LOCAL_REPO_BASE / "_vibecoding"
REMOTE_WORKTREE_BASE = REMOTE_REPO_BASE / "_vibecoding"

# SSH configuration
SSH_USER_HOST = "user@your-dev-machine.local"
SSH_KEY_PATH = Path.home() / ".ssh" / "your_key"

# Coding tool commands
CLOUD_CODE_CMD = "cly"       # Cloud code wrapper (--cc)
OPEN_CODE_CMD = "opencode"   # Open code command (--oc)
```

**Important:** The paths must be identical on both the host and VM for git worktree operations to work correctly. This is achieved by mounting the shared folder at the same path (using a symlink on the VM if needed).

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
