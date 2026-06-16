//
//  Ticket.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import Foundation

/// Coding tool recorded on a ticket (format spec section 4).
///
/// Unlike `state` the spec defines no default for `tool`, so unknown
/// or missing values decode to `nil` rather than a fallback case.
public enum TicketTool: String, CaseIterable, Sendable {
    case claude
    case codex
    case opencode

    /// Creates a tool from a raw frontmatter value, tolerating unknown input.
    ///
    /// - Parameter lenientValue: Raw `tool` value from frontmatter, or `nil` when absent.
    /// - Returns: `nil` for missing or unrecognized values (no spec default exists).
    public init?(lenientValue: String?) {
        guard let raw = lenientValue?.trimmingCharacters(in: .whitespaces).lowercased(),
              let tool = TicketTool(rawValue: raw) else {
            return nil
        }
        self = tool
    }
}

/// A single ticket loaded from the store: the raw frontmatter fields plus the body.
///
/// The struct stores exactly what the lenient parser extracted (`fields` keeps
/// unknown keys too) and layers the spec section 6 defaults on top through
/// typed accessors, so readers never fail on missing or malformed data.
public struct Ticket: Identifiable, Hashable, Sendable {
    /// Location of the ticket file on disk; `nil` for tickets parsed from a string in tests.
    public let fileURL: URL?

    /// File name without the `.md` extension; the fallback identity for the ticket.
    public let filenameStem: String

    /// Raw frontmatter key/value pairs, unknown keys included. Values are
    /// post-processing (quotes stripped, block scalars joined); keys whose
    /// value was empty or the literal `null` are absent.
    public let fields: [String: String]

    /// Freeform Markdown body (everything after the closing `---`), edge-trimmed.
    public let body: String

    /// Creates a ticket from parsed parts.
    ///
    /// - Parameters:
    ///   - fileURL: Location on disk, or `nil` when not file-backed.
    ///   - filenameStem: File name without extension, used for identity fallbacks.
    ///   - fields: Parsed frontmatter fields (unknown keys preserved).
    ///   - body: Freeform Markdown body.
    public init(fileURL: URL?, filenameStem: String, fields: [String: String], body: String) {
        self.fileURL = fileURL
        self.filenameStem = filenameStem
        self.fields = fields
        self.body = body
    }

    // MARK: - Identity

    /// Unique identity within the store. Backed by the filename stem because the
    /// store is a flat directory, so stems are guaranteed unique even when a
    /// hand-edited `id` field collides between two files.
    public var id: String { filenameStem }

    /// Domain ticket id (`<repo>-<n>`), falling back to the filename stem
    /// when the `id` field is absent (spec section 6 default).
    public var ticketID: String { fields["id"] ?? filenameStem }

    // MARK: - Typed accessors (spec section 6 defaults)

    /// Card title; falls back to the ticket id when absent.
    public var title: String { fields["title"] ?? ticketID }

    /// Repository name; falls back to the id minus its trailing `-<digits>`.
    public var repo: String { fields["repo"] ?? Ticket.repoName(fromID: ticketID) }

    /// Coding tool, or `nil` when absent or unrecognized.
    public var tool: TicketTool? { TicketTool(lenientValue: fields["tool"]) }

    /// Work branch, or `nil` until the first park.
    public var branch: String? { fields["branch"] }

    /// Branch the work is based on, usually `main`.
    public var baseBranch: String? { fields["base_branch"] }

    /// Absolute worktree path while one exists; informational only.
    public var worktreePath: String? { fields["worktree"] }

    /// Most recent coding-tool session id (best-effort).
    public var sessionID: String? { fields["session_id"] }

    /// Creation timestamp, when present and parseable.
    public var created: Date? { fields["created"].flatMap(Ticket.parseTimestamp) }

    /// Last-update timestamp, when present and parseable.
    public var updated: Date? { fields["updated"].flatMap(Ticket.parseTimestamp) }

    /// Short card blurb: the `description` field, or the body's first
    /// paragraph when the field is absent (spec section 6 default).
    public var cardDescription: String? { fields["description"] ?? firstBodyParagraph }

    /// First non-empty paragraph of the body with lines joined by spaces,
    /// or `nil` when the body has no content.
    public var firstBodyParagraph: String? {
        var paragraph: [String] = []
        for line in body.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty {
                if !paragraph.isEmpty { break }
            } else {
                paragraph.append(trimmed)
            }
        }
        return paragraph.isEmpty ? nil : paragraph.joined(separator: " ")
    }

    // MARK: - Park-owned body sections

    /// Heading text of the human braindump section park captures from the
    /// `/park` invocation (spec section 7). Matched case-insensitively on read.
    public static let braindumpHeading = "Braindump"

    /// Heading text of the agent's next-step section park writes (spec
    /// section 7). Matched case-insensitively on read.
    public static let nextStepHeading = "Next step"

    /// The human's braindump — the content under `## Braindump` — or `nil` when
    /// the ticket was parked without one.
    public var braindump: String? { bodySection(named: Ticket.braindumpHeading) }

    /// The agent's parked-context note — the content under `## Next step` — or
    /// `nil` when absent.
    public var nextStep: String? { bodySection(named: Ticket.nextStepHeading) }

    /// The freeform remainder of the body with the park-owned `## Braindump` and
    /// `## Next step` sections removed, or `nil` when nothing is left. This is
    /// the human's general notes, shown and edited separately from the two
    /// park-owned sections.
    public var freeformNotes: String? {
        let owned: Set<String> = [
            Ticket.braindumpHeading.lowercased(),
            Ticket.nextStepHeading.lowercased(),
        ]
        var skipping = false
        var kept: [String] = []
        for line in body.components(separatedBy: "\n") {
            if let title = Ticket.h2Title(of: line) {
                skipping = owned.contains(title.lowercased())
                if skipping { continue } // drop the heading line of owned sections
                kept.append(line)        // keep other section headings verbatim
                continue
            }
            if !skipping { kept.append(line) }
        }
        let text = kept.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }

    /// Returns the trimmed content under a level-2 (`## `) heading, or `nil` when
    /// the heading is absent or its section is empty. The section runs from its
    /// heading to the next `## ` heading or the end of the body.
    ///
    /// - Parameter name: The heading text to match (case-insensitive).
    /// - Returns: The section's content, or `nil`.
    internal func bodySection(named name: String) -> String? {
        var found = false
        var capturing = false
        var captured: [String] = []
        for line in body.components(separatedBy: "\n") {
            if let title = Ticket.h2Title(of: line) {
                if capturing { break } // the next section ends ours
                if title.caseInsensitiveCompare(name) == .orderedSame {
                    found = true
                    capturing = true
                }
                continue
            }
            if capturing { captured.append(line) }
        }
        guard found else { return nil }
        let text = captured.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }

    /// The title of a level-2 Markdown heading line (`## Title`), or `nil` when
    /// the line is not exactly an h2. Used to split the body into sections.
    ///
    /// - Parameter line: A single body line.
    /// - Returns: The trimmed heading title, or `nil`.
    internal static func h2Title(of line: String) -> String? {
        guard line.hasPrefix("## ") else { return nil }
        return String(line.dropFirst(3)).trimmingCharacters(in: .whitespaces)
    }

    // MARK: - Helpers

    /// Recovers the repository name from a ticket id by stripping the trailing
    /// `-<digits>` suffix (spec section 2 fallback rule).
    ///
    /// - Parameter id: A ticket id such as `vibe-12`.
    /// - Returns: The repo prefix (`vibe`), or the unchanged id when no
    ///   trailing `-<digits>` suffix exists.
    public static func repoName(fromID id: String) -> String {
        guard let dash = id.lastIndex(of: "-") else { return id }
        let digits = id[id.index(after: dash)...]
        guard !digits.isEmpty, digits.allSatisfy({ $0.isASCII && $0.isNumber }) else { return id }
        return String(id[..<dash])
    }

    /// Parses a spec section 5 timestamp (`YYYY-MM-DDTHH:MM:SSZ`), also
    /// tolerating fractional seconds.
    ///
    /// - Parameter value: Raw timestamp string from frontmatter.
    /// - Returns: The parsed date, or `nil` when the value is not ISO 8601.
    internal static func parseTimestamp(_ value: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        if let date = formatter.date(from: value) { return date }
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: value)
    }
}
