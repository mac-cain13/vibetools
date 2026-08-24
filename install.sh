#!/bin/bash
# Install script for vibe - Git worktree manager for remote development

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install uv if not present
install_uv() {
    echo "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Source the env to get uv in PATH for this session
    if [ -f "$HOME/.local/bin/env" ]; then
        source "$HOME/.local/bin/env"
    elif [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi

    # Add to PATH for current session
    export PATH="$HOME/.local/bin:$PATH"
}

# Install repository skills for Claude Code.
install_claude_skills() {
    local skills_src="$1"
    local claude_skills="$2"
    local skill_dir skill_name link

    if [ ! -d "$skills_src" ]; then
        echo "  ⚠ no skills/ directory found, skipping"
        return
    fi

    mkdir -p "$claude_skills"
    for skill_dir in "$skills_src"/*/; do
        [ -d "$skill_dir" ] || continue
        skill_name=$(basename "$skill_dir")
        link="$claude_skills/$skill_name"

        # Symlink so the installed skill always tracks the repo source.
        rm -rf "$link"
        ln -s "${skill_dir%/}" "$link"
        echo "  ✓ linked skill '$skill_name' for Claude Code"
    done
}

# Return whether every existing Codex skill has the same Claude Code entry.
codex_directory_matches_claude() {
    local codex_skills="$1"
    local claude_skills="$2"
    local entry counterpart

    while IFS= read -r entry; do
        counterpart="$claude_skills/$(basename "$entry")"
        if [ ! -e "$counterpart" ] || [ ! "$entry" -ef "$counterpart" ]; then
            return 1
        fi
    done < <(find "$codex_skills" -mindepth 1 -maxdepth 1 -print)
}

# Share the complete Claude Code skill directory with Codex.
share_skills_with_codex() {
    local user_root="$1"
    local claude_skills="$user_root/.claude/skills"
    local agents_root="$user_root/.agents"
    local codex_skills="$agents_root/skills"
    local shared_target="../.claude/skills"
    local timestamp backup suffix

    mkdir -p "$agents_root"

    if [ -L "$codex_skills" ]; then
        if [ "$codex_skills" -ef "$claude_skills" ]; then
            echo "  ✓ Codex already shares Claude Code skills"
            return
        fi

        echo "  ✗ $codex_skills points somewhere other than $claude_skills" >&2
        echo "    Preserving it; move it aside and rerun the installer." >&2
        return 1
    fi

    if [ -e "$codex_skills" ]; then
        if [ ! -d "$codex_skills" ] || ! codex_directory_matches_claude "$codex_skills" "$claude_skills"; then
            echo "  ✗ $codex_skills contains skills not mirrored in $claude_skills" >&2
            echo "    Preserving it; reconcile those skills and rerun the installer." >&2
            return 1
        fi

        timestamp=$(date -u +%Y%m%dT%H%M%SZ)
        backup="$codex_skills.before-shared-$timestamp"
        suffix=1
        while [ -e "$backup" ] || [ -L "$backup" ]; do
            backup="$codex_skills.before-shared-$timestamp-$suffix"
            suffix=$((suffix + 1))
        done
        mv "$codex_skills" "$backup"
        echo "  ✓ preserved previous Codex skill links at $backup"
    fi

    ln -s "$shared_target" "$codex_skills"
    echo "  ✓ shared Claude Code skills with Codex"
}

# Install and share agent skills from the requested source directory.
install_agent_skills() {
    local skills_src="${1:-$SCRIPT_DIR/skills}"
    local user_root="${VIBE_AGENT_HOME:-$HOME}"
    local claude_skills="$user_root/.claude/skills"

    if [ -d "$skills_src" ]; then
        skills_src="$(cd "$skills_src" && pwd)"
    fi

    install_claude_skills "$skills_src" "$claude_skills"
    share_skills_with_codex "$user_root"
}

# Keep the functions available to focused tests without running the full install.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    return 0
fi

echo "Installing vibe..."
echo ""

# Step 1: Check/install uv
echo "Step 1: Checking for uv..."
if command_exists uv; then
    echo "  ✓ uv is already installed"
else
    install_uv
    if command_exists uv; then
        echo "  ✓ uv installed successfully"
    else
        echo "  ✗ Failed to install uv"
        echo ""
        echo "Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi
echo ""

# Step 2: Install vibe using uv tool
echo "Step 2: Installing vibe Python package..."
cd "$SCRIPT_DIR"

# Uninstall existing version if present (to ensure clean upgrade)
uv tool uninstall vibe 2>/dev/null || true

# Clear the build cache for vibe to ensure fresh build
# This is necessary because uv caches wheels by name+version, and if the
# version hasn't changed, it will use the stale cached wheel
uv cache clean vibe 2>/dev/null || true

# Install the package
if uv tool install . --force; then
    echo "  ✓ vibe installed successfully"
else
    echo "  ✗ Failed to install vibe"
    exit 1
fi
echo ""

# Step 3: Deploy shared Claude Code and Codex skills
echo "Step 3: Deploying shared agent skills..."
install_agent_skills "$SCRIPT_DIR/skills"
echo ""

# Step 4: Verify installation
echo "Step 4: Verifying installation..."
if command_exists vibe; then
    echo "  ✓ 'vibe' command is available"
    VIBE_PATH=$(which vibe)
    echo "    Location: $VIBE_PATH"
else
    echo "  ⚠ 'vibe' command not found in PATH"
    echo ""
    echo "  You may need to add ~/.local/bin to your PATH:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "  Or restart your terminal."
fi
echo ""

# Done
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Installation complete!"
echo ""
echo "Usage:"
echo "  vibe                             # Connect to current repo/worktree"
echo "  vibe feature-branch              # Create worktree, SSH with coding tool"
echo "  vibe feature-branch --from main  # Create from main branch"
echo "  vibe --cli                       # SSH to home directory"
echo "  vibe --local feature-branch      # Work locally"
echo "  vibe --clean                     # Clean all worktrees"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
