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
