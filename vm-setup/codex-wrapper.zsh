#!/usr/bin/env zsh
# Codex wrapper (cdx).
#
# As with cly, no terminal-title management: Codex publishes idle/working/blocked
# in the title, and herdr's *only* `idle` rule for Codex reads it (priority 100).
# Overwriting the title meant idle could never match, so sessions fell through to
# the body-based `weak_blocker` rule and looked permanently blocked.

cdx() {
    codex --dangerously-bypass-approvals-and-sandbox "$@"
}
