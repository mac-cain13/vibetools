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
3. Link this repository's skills into Claude Code and share the complete user
   skill directory with Codex

Claude Code remains the canonical user-skill location at `~/.claude/skills`.
Codex's documented user-skill location, `~/.agents/skills`, is linked to it so
skills added for either agent stay available to both. If the Codex directory
already contains entries that are not mirrored in Claude Code, the installer
preserves it and stops with instructions instead of overwriting those skills.

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
# Connect to current repo or worktree (interactive tool picker)
vibe

# Create worktree with Codex
vibe feature-branch --codex

# Create worktree with Claude Code
vibe feature-branch --claude

# Create worktree with OpenCode
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
vibe --local feature-branch --claude

# Resume parked work from the NSProject board (recreates the worktree, relaunches the tool)
vibe resume BZL_q7m2x

# Clean up a specific worktree
vibe --clean feature-branch

# Clean up all worktrees across all repos
vibe --clean
```

### Park & resume (NSProject board)

`vibe resume <ticket-id>` picks parked work back up from the **NSProject board**
— the two-person team's Markdown-in-Git project board (`<CODE>_<hash>` ticket
ids like `BZL_q7m2x`). Parking is handled by the `park` skill: it captures the
current work as a `wip: park <id>` commit on the work branch (local only, never
pushed), records a `work[]` entry on the ticket (branch, session, tool,
`parked_at`) and rewrites the ticket's `## Where I left off` handoff. Resume
reconstructs (or reuses) the work branch's worktree, unwinds the park commit
when the tip is this ticket's `wip: park <id>` marker, relaunches the recorded
coding tool (resuming the Claude session when one is recorded and local), and
clears the board's `parked_at` marker. When the branch isn't available on this
machine (cross-dev — the parker never pushed it), resume launches a fresh
session in the main checkout seeded from the ticket's `## Where I left off`.
When a parked session exits, vibe removes the worktree (it is reconstructed on
resume); `vibe --clean` is a backstop sweep (worktrees with uncommitted changes
are skipped). The on-disk contract is specified in
[docs/nsproject-park.md](docs/nsproject-park.md); the board itself (folders,
ticket schema, the macOS Kanban app) is the separate NSProject repo.

### Selecting a VM (running clones side by side)

Local VMs are addressed by their **tart name**, not by mDNS. By default **vibe**
connects to `config.DEFAULT_VM` (`vibecoding`), resolving its current IP with
`tart ip` — so `.local` name collisions between clones never come into play. To
run several clones at once — e.g. one on a macOS beta, one reserved for
GUI-heavy automation — just name the one you want. VMs dedicated to AI work
share a `vibecoding-` prefix, so `--vm` takes a **short name** and expands it
(`--vm beta` → `vibecoding-beta`); this keeps invocations terse and guards
against accidentally targeting an unrelated VM. Full names still work:

```bash
# Default: the `vibecoding` tart VM, resolved via `tart ip`
vibe feature-branch --claude

# A different clone by short name — expands to `vibecoding-beta`
vibe feature-branch --vm beta

# An explicit host — e.g. a VM on other hardware / over Tailscale
vibe --cli --host admin@mac-mini.tailnet.ts.net

# Set a default target for the shell so you don't repeat the flag
export VIBE_VM=beta   # also prefix-expanded to `vibecoding-beta`
vibe feature-branch --claude
```

Resolution precedence (first match wins): `--host` → `--vm` → `$VIBE_SSH_HOST`
→ `$VIBE_VM` → `config.DEFAULT_VM` (the default local VM) → `config.SSH_USER_HOST`
(only when no default VM is configured, e.g. WSL, which has no tart). `--vm` /
`$VIBE_VM` / `DEFAULT_VM` all name a **tart VM** and resolve to `<user>@<ip>` via
`tart ip`; this replaces mDNS, which was ambiguous because cloned VMs share the
`vibecoding` guest hostname (they would all answer to `vibecoding.local`). Short
`--vm` / `$VIBE_VM` names are expanded with the `vibecoding-` prefix
(`config.VM_PREFIX`); the bare default (`vibecoding`) and already-prefixed names
pass through unchanged.
Because tart clones share an SSH host key and get DHCP addresses, tart-resolved
connections auto-accept the host key and keep it out of your `known_hosts`, so a
reassigned address never triggers a blocking host-key mismatch.

If the default VM isn't running, resolution fails fast with an actionable error
(rather than a slow mDNS timeout). To reach a VM by its `.local` name anyway,
name it explicitly: `--host admin@vibecoding.local`.


### Running inside herdr

[herdr](https://herdr.dev) classifies a pane's agent by scanning the foreground
process group for an *eligible* process, then matching that agent's screen
manifest against the terminal. Shells, `sleep` and `ssh` are **not** eligible, so
a pane where **vibe** has SSH'd into a VM is not recognised as anything at all.

`HERDR_AGENT` names the manifest to use — but only when set on the eligible
process, which here is **vibe itself**, not the `ssh` child it spawns. Since
macOS reads another process's environment from its exec-time image, vibe cannot
just assign to `os.environ`; it re-execs itself with the variable set. That
happens automatically when vibe is run inside a herdr pane, before any git work,
and only once (the hint's presence is what stops it looping). Panes then show up
as `claude`/`codex`/`opencode` with live idle/working/blocked status.

Requires **herdr 0.7.5+** on macOS (0.7.1+ on Linux) — older builds ignore the
hint entirely. Check with `herdr --version`.

Setting `HERDR_AGENT` yourself takes precedence and skips the re-exec, which is
also how you name a manifest vibe does not map:

```bash
HERDR_AGENT=kimi vibe feature-branch --claude
```

Shell connections (`--cli`) get no hint — there is no agent in the pane. Check
the names your herdr build ships with `herdr server agent-manifests` if a pane
stays unrecognised; the tool→manifest map is `HERDR_AGENT_NAMES` in
`vibe/herdr.py`, and `herdr agent explain <pane>` shows the matched manifest,
rule and evidence.

**vibe clears the pane before launching the agent** (inside herdr only). herdr's
screen rules match against the pane's recent buffer, so anything left on screen
above the agent keeps being evaluated. That is not cosmetic: Codex's
`weak_blocker` rule looks for a prompt phrase anywhere in that buffer next to a
`yes` or a `❯`, so a shell prompt sitting above Codex supplies the `❯` and pins
the session at `blocked` for as long as it runs. Clearing removes vibe's own
output too — the screen is briefly blank while SSH connects.

This is a mitigation, not a cure: that rule also accepts the word `yes`, which
Codex will eventually write itself, and the phrase comes from Codex's ordinary
replies (*"What would you like to work on?"*). The real fix belongs in herdr's
`codex` manifest, whose `weak_blocker` scans `whole_recent` rather than the live
tail, and whose only `idle` rule sits at priority 100 and can never outrank it.

**Terminal titles are left entirely to the agent.** `cly` and `cdx` used to
re-assert `"<folder> — Claude"` every 0.5s expressly to stop the agent changing
it, and Claude Code additionally had `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` set.
Both are gone: the agents encode idle/working/blocked in the OSC title, and
herdr's detection depends on it. Do not reintroduce title management here.

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
vibe [OPTIONS] [BRANCH] [TICKET]

Arguments:
  BRANCH    Branch name for the worktree. Creates worktree and connects to it.
            Supports origin/branch syntax for remote branches.
            If omitted, connects to current repo/worktree context.
            The literal 'resume' resumes an NSProject ticket instead.
  TICKET    Ticket id for 'vibe resume <ticket>'. Only valid after 'resume'.

Options:
  --codex        Use Codex (cdx) as the coding tool.
  --claude       Use Claude Code (cly) as the coding tool.
  --oc           Use OpenCode (opencode) as the coding tool.
  --cli          Connect to remote CLI (shell only, without coding tool).
                 If no branch specified, connects to home directory.
  --local        Work locally instead of SSH to remote. Requires branch name.
  --clean        Clean worktrees. Without branch, cleans all.
                 With branch, cleans specific worktree.
  --from TEXT    Base branch to create new branch from.
  --vm TEXT      Connect to an AI-work VM by its short name; the `vibecoding-`
                 prefix is added automatically (e.g. `--vm goldengate` →
                 `vibecoding-goldengate`), resolved via `tart ip`. Full names
                 accepted too. Defaults to $VIBE_VM.
  --host TEXT    Connect to an explicit user@host. Overrides --vm.
                 Defaults to $VIBE_SSH_HOST.
  -h, --help     Show help message and exit.
```

When no coding tool flag is specified, vibe prompts with an interactive picker.

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

# Default local VM: connected to by tart name (resolved via `tart ip`), not
# mDNS. Set to None on hosts without tart (e.g. WSL) to use SSH_USER_HOST.
DEFAULT_VM = "vibecoding"

# SSH configuration. SSH_USER_HOST is the static fallback used only when
# DEFAULT_VM is None; it also supplies the default SSH username for tart VMs.
SSH_USER_HOST = "user@your-dev-machine.local"
SSH_KEY_PATH = Path.home() / ".ssh" / "your_key"

# Coding tool commands
CLAUDE_CODE_CMD = "cly"      # Claude Code wrapper (--claude)
CODEX_CMD = "cdx"            # Codex wrapper (--codex)
OPEN_CODE_CMD = "opencode"   # OpenCode command (--oc)
```

**Important:** The paths must be identical on both the host and VM for git worktree operations to work correctly. This is achieved by mounting the shared folder at the same path (using a symlink on the VM if needed).

## Features

- **Tab completion** for branch names and worktree management
- **Safety checks** prevent cleaning worktrees with uncommitted changes
- **Remote branch support** - Use `origin/branch` to create tracking branches
- **Flexible base branches** - Create new branches from any local or remote branch
- **Batch cleanup** - Remove multiple completed worktrees at once
- **Lingering directory cleanup** - Removes invalid directories in worktree base
- **Portable worktrees** - Recorded with relative paths, so a worktree works from both the host and the VM whatever each has the drive mounted at
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
