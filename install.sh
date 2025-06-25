#!/bin/bash
# Install script for vibe.zsh

# Configuration
TARGET_DIR="$HOME/.config/zsh"
TARGET_FILE="$TARGET_DIR/vibe.zsh"
SOURCE_FILE="$(dirname "$0")/vibe.zsh"

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# Copy the file
if cp "$SOURCE_FILE" "$TARGET_FILE"; then
    echo "✓ Installed vibe.zsh to $TARGET_FILE"
    
    # Check if it's already sourced in .zshrc
    if grep -q "source.*vibe.zsh" "$HOME/.zshrc" 2>/dev/null; then
        echo "✓ vibe.zsh is already sourced in .zshrc"
    else
        echo ""
        echo "To complete installation, add this line to your .zshrc:"
        echo "source ~/.config/zsh/vibe.zsh"
    fi
else
    echo "✗ Failed to install vibe.zsh"
    exit 1
fi