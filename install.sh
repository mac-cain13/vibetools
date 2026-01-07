#!/bin/bash
# Install script for vibe - Git worktree manager for remote development

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing vibe..."
echo ""

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

# Step 3: Verify installation
echo "Step 3: Verifying installation..."
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
