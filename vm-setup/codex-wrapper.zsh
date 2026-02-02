#!/usr/bin/env zsh
# Simple, elegant terminal title management for Codex
# Adapted from claude-wrapper.zsh

# Codex wrapper with custom terminal title
cdx() {
    local folder=${PWD:t}  # Just the current folder name

    # Set title to show we're running Codex
    _set_title "$folder — Codex"

    # Start a background process to continuously reset the title
    # (prevents Codex from changing it)
    (
        while true; do
            _set_title "$folder — Codex"
            sleep 0.5
        done
    ) &
    local title_pid=$!

    # Run Codex with full approval bypass
    codex --dangerously-bypass-approvals-and-sandbox "$@"
    local exit_code=$?

    # Kill the background title setter
    kill $title_pid 2>/dev/null
    wait $title_pid 2>/dev/null  # Clean up zombie process

    # Restore normal title
    _set_title "%~"

    # Return the original exit code
    return $exit_code
}
