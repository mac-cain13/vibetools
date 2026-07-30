#!/usr/bin/env zsh
# Claude wrapper (cly), plus a terminal title for the shell prompt.
#
# cly deliberately does NOT manage the terminal title. Claude Code publishes its
# own state there — a braille spinner while working, `✳ ` when idle — and that
# title is the only signal herdr's `working` detection has (its sole other
# working rule covers a niche overlay; every blocked rule reads the screen body).
# An earlier version re-asserted "<folder> — Claude" every 0.5s expressly to stop
# Claude changing it, which left herdr seeing blocked and idle but never working.
# Claude Code also needs CLAUDE_CODE_DISABLE_TERMINAL_TITLE unset in
# ~/.claude/settings.json, or it emits no title at all.

# Set the terminal title to a LITERAL string. We deliberately do NOT use
# `print -P` (prompt expansion): a folder name can contain `%` — vibe encodes
# `/` in worktree directory names as `%2F` — and `print -P` would interpret it
# as a prompt escape (e.g. `%2F` = a color code), corrupting the title escape
# sequence so it leaks into the terminal.
_set_title() {
    print -n "\e]2;$1\a"
}

cly() {
    "$HOME/.local/bin/claude" --dangerously-skip-permissions "$@"
}

# Title the shell prompt with the cwd. This only runs between commands, never
# while an agent holds the foreground, so it cannot disturb agent detection.
_claude_precmd() {
    _set_title "${PWD/#$HOME/~}"
}

# Add our precmd function to the array (doesn't overwrite existing hooks)
if [[ -z ${precmd_functions[(r)_claude_precmd]} ]]; then
    precmd_functions+=(_claude_precmd)
fi
