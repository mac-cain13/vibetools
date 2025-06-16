# vibe.zsh

A git worktree manager for seamless remote development sessions. Create isolated branch environments and connect instantly to your remote coding setup.

## Why vibe.zsh?

Working on multiple branches simultaneously requires constant context switching, stashing, and branch management overhead. **vibe.zsh** eliminates this friction by:

- **Instant branch isolation** - Each branch gets its own worktree directory
- **Zero context switching** - No more `git checkout` dance between features
- **Remote-first workflow** - Automatic SSH connection to your development machine
- **Clean workspace management** - Built-in cleanup for completed work

Perfect for developers juggling multiple features, bug fixes, or experiments who want to maintain flow state.

## Quick Start

```bash
# Add to your ~/.zshrc
[ -f ~/.config/zsh/vibe.zsh ] && source ~/.config/zsh/vibe.zsh

# Create worktree and connect to remote with Claude Code CLI
vibe feature-branch

# Connect with just a shell (no cly)
vibe --cli feature-branch

# Connect to remote home directory
vibe --cli

# Clean up completed worktrees
vibe --clean feature-branch
vibe --clean  # clean all repos
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
   - Existing local branches → Use existing worktree
   - Remote branches (`origin/branch`) → Create local tracking branch
   - New names → Create new branch from current HEAD

3. **Remote Connection** - SSH to your development machine and automatically:
   - Navigate to the worktree directory
   - Launch your coding environment (`cly` by default)

## Configuration

Edit the constants in `vibe()` function for your setup:

```bash
LOCAL_WORKTREE_BASE="/your/local/path/_vibecoding"
REMOTE_WORKTREE_BASE="/your/remote/path/_vibecoding" 
SSH_USER_HOST="user@your-dev-machine.local"
SSH_KEY_PATH="~/.ssh/your_key"
CODING_TOOL_CMD="cly"  # or "code", "nvim", etc.
```

## Features

- **Tab completion** for branch names and worktree management
- **Safety checks** prevent cleaning worktrees with uncommitted changes
- **Flexible branch support** works with local, remote, and new branches
- **Batch cleanup** remove multiple completed worktrees at once

## Prerequisites

- Git with worktree support
- SSH access to remote development machine
- Shared filesystem or sync between local/remote worktree paths

---

*Get in the right coding vibe, faster.*