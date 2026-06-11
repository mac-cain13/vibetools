#!/usr/bin/env zsh
# Simple, elegant terminal title management for Claude
# From https://steipete.me/posts/2025/commanding-your-claude-code-army

# Set the terminal title to a LITERAL string. We deliberately do NOT use
# `print -P` (prompt expansion): a folder name can contain `%` — vibe encodes
# `/` in worktree directory names as `%2F` — and `print -P` would interpret it
# as a prompt escape (e.g. `%2F` = a color code), corrupting the title escape
# sequence so it leaks into the terminal.
_set_title() {
    print -n "\e]2;$1\a"
}

# Decode vibe's worktree-dir encoding (%2F -> /, %25 -> %) for a readable title.
_vibe_title_name() {
    local s=${1//"%2F"//}
    print -r -- "${s//"%25"/%}"
}

# Claude wrapper with custom terminal title
cly() {
    local folder=$(_vibe_title_name "${PWD:t}")  # decoded current folder name

    # Set title to show we're running Claude
    _set_title "$folder — Claude"
    
    # Start a background process to continuously reset the title
    # (prevents Claude from changing it)
    (
        while true; do
            _set_title "$folder — Claude"
            sleep 0.5
        done
    ) &
    local title_pid=$!
    
    # Run Claude with dangerous permissions
    "$HOME/.local/bin/claude" --dangerously-skip-permissions "$@"
    local exit_code=$?
    
    # Kill the background title setter
    kill $title_pid 2>/dev/null
    wait $title_pid 2>/dev/null  # Clean up zombie process
    
    # Restore normal title
    _set_title "${PWD/#$HOME/~}"
    
    # Return the original exit code
    return $exit_code
}

# Update terminal title before each prompt (using proper ZSH hooks)
_claude_precmd() {
    _set_title "${PWD/#$HOME/~}"
}

# Add our precmd function to the array (doesn't overwrite existing hooks)
if [[ -z ${precmd_functions[(r)_claude_precmd]} ]]; then
    precmd_functions+=(_claude_precmd)
fi