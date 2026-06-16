//
//  ResumeCommand.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import Foundation

/// Builds the `vibe resume <id>` command the board copies to the clipboard.
///
/// Ticket ids end up pasted into a shell, so they are validated against the
/// conservative charset from format spec section 6 and shell-quoted when they
/// fall outside it (tickets are hand-editable files).
public enum ResumeCommand {

    /// Builds the resume command for a ticket.
    ///
    /// - Parameter ticketID: The ticket id (e.g. `vibe-12`).
    /// - Returns: The command string, e.g. `vibe resume vibe-12`. Ids outside
    ///   the safe charset are single-quoted for the shell.
    public static func command(forTicketID ticketID: String) -> String {
        return "vibe resume \(quoteIfNeeded(ticketID))"
    }

    /// One ticket's input to the multi-window tmux command: its id plus the
    /// worktree to `cd` into before resuming (omitted when absent).
    public struct TmuxEntry: Sendable {

        /// The ticket id passed to `vibe resume`.
        public let ticketID: String

        /// Absolute path of the ticket's worktree, or `nil` to skip the `cd`.
        public let worktreePath: String?

        /// Creates an entry.
        ///
        /// - Parameters:
        ///   - ticketID: The ticket id (e.g. `vibe-12`).
        ///   - worktreePath: The worktree path to `cd` into, if known.
        public init(ticketID: String, worktreePath: String?) {
            self.ticketID = ticketID
            self.worktreePath = worktreePath
        }
    }

    /// Builds a multi-line tmux command that opens one new window per ticket in
    /// the **current** tmux session, each window `cd`-ing into the ticket's
    /// worktree (when known), running `vibe resume <id>`, and then `exec`-ing a
    /// fresh login shell so the window survives — and stays open — after the
    /// vibe session ends. Paste it while attached to a tmux session.
    ///
    /// Each window's inner command runs through tmux's own `sh`, so ids and
    /// paths are shell-quoted for that inner shell and the whole inner command
    /// is quoted again for the shell you paste into. `$SHELL` is left unquoted
    /// so the inner shell expands it to your login shell.
    ///
    /// - Parameter entries: The tickets to open, in the order windows should be
    ///   created.
    /// - Returns: Newline-separated `tmux new-window …` lines, or an empty
    ///   string when `entries` is empty.
    public static func tmuxResumeAllCommand(for entries: [TmuxEntry]) -> String {
        return entries.map(tmuxWindowLine).joined(separator: "\n")
    }

    /// Builds a single `tmux new-window …` line for one ticket. See
    /// ``tmuxResumeAllCommand(for:)`` for the quoting rationale.
    private static func tmuxWindowLine(for entry: TmuxEntry) -> String {
        let id = quoteIfNeeded(entry.ticketID)
        var inner = ""
        if let path = entry.worktreePath, !path.isEmpty {
            inner += "cd \(quoteIfNeeded(path)); "
        }
        inner += "vibe resume \(id); exec $SHELL"
        return "tmux new-window -n \(id) \(shellQuote(inner))"
    }

    /// Returns the value unchanged when it matches the conservative id charset
    /// (`[A-Za-z0-9._/-]`, spec section 6), otherwise shell-quotes it.
    ///
    /// - Parameter value: Raw value read from a ticket.
    /// - Returns: A shell-safe representation of the value.
    internal static func quoteIfNeeded(_ value: String) -> String {
        let safe = !value.isEmpty && value.unicodeScalars.allSatisfy { scalar in
            switch scalar {
            case "a"..."z", "A"..."Z", "0"..."9", ".", "_", "/", "-":
                return true
            default:
                return false
            }
        }
        return safe ? value : shellQuote(value)
    }

    /// Single-quotes a string for POSIX shells, escaping embedded single quotes.
    ///
    /// - Parameter value: The string to quote.
    /// - Returns: The quoted string (equivalent to Python's `shlex.quote`).
    internal static func shellQuote(_ value: String) -> String {
        return "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}
