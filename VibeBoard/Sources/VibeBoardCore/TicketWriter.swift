//
//  TicketWriter.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import Foundation
import OSLog

/// Field-preserving ticket writer (format spec sections 2 and 5).
///
/// Updates perform a line-level edit of the frontmatter block: only the lines
/// for the keys being changed are touched, so unknown keys, ordering, comments
/// and the body round-trip byte-identical. Every update refreshes `updated`
/// and is written atomically (temp file + rename on the same volume). Ticket
/// creation is not the app's responsibility (the vibeboard skill owns it).
public enum TicketWriter {

    private static let logger = Logger(subsystem: "com.nonstrict.VibeBoard", category: "writer")

    // MARK: - Updating

    /// Updates frontmatter fields (and optionally the body) of a ticket file.
    ///
    /// Only the lines for the given keys are rewritten; everything else is
    /// preserved byte-identical. `updated` is always refreshed. The write is
    /// atomic (temp file in the same directory, then rename over the original).
    ///
    /// - Parameters:
    ///   - url: Location of the ticket file on disk.
    ///   - changes: Keys to set; a `nil` value writes the literal `null`.
    ///   - newBody: When non-nil, replaces the entire body after the closing `---`.
    ///   - now: Timestamp source for `updated` (injectable for tests).
    /// - Throws: File system errors from reading or writing the file.
    public static func update(fileAt url: URL,
                              settingFields changes: [String: String?],
                              body newBody: String? = nil,
                              now: Date = Date()) throws {
        logger.debug("Updating ticket file at \(url.path, privacy: .public)")
        let raw = try String(contentsOf: url, encoding: .utf8)
        let rewritten = updatedContent(of: raw, settingFields: changes, body: newBody, now: now)
        try atomicWrite(rewritten, to: url)
        logger.notice("Updated ticket file at \(url.path, privacy: .public)")
    }

    /// Pure transformation behind `update(fileAt:)`: applies field and body
    /// changes to raw document text via line-level editing.
    ///
    /// - Parameters:
    ///   - raw: Original file content.
    ///   - changes: Keys to set; a `nil` value writes the literal `null`.
    ///   - newBody: When non-nil, replaces the body.
    ///   - now: Timestamp for the refreshed `updated` field.
    /// - Returns: The rewritten document text.
    internal static func updatedContent(of raw: String,
                                        settingFields changes: [String: String?],
                                        body newBody: String?,
                                        now: Date) -> String {
        var allChanges = changes
        allChanges["updated"] = isoTimestamp(now)

        var lines = splitLinesKeepingTerminators(raw)

        guard frontmatterRange(in: lines) != nil else {
            // No valid frontmatter: synthesize a block on top, keep the whole
            // original content as the body (never drop content).
            var output: [String] = ["---\n"]
            for key in allChanges.keys.sorted() {
                let value = allChanges[key] ?? nil
                output.append(contentsOf: formattedLines(key: key, value: value, terminator: "\n"))
            }
            output.append("---\n")
            let bodyText = (newBody ?? raw).trimmingCharacters(in: .whitespacesAndNewlines)
            if !bodyText.isEmpty {
                output.append("\n")
                output.append(bodyText + "\n")
            }
            return output.joined()
        }

        // Apply each key change with a fresh structure scan (indices shift as
        // lines are inserted/removed). Sorted order keeps output deterministic.
        for key in allChanges.keys.sorted() {
            let value = allChanges[key] ?? nil
            guard let range = frontmatterRange(in: lines) else { break }
            if keyLineIndex(of: key, in: lines, range: range) != nil {
                // Rewrite EVERY line declaring the key — a hand-edited ticket
                // can carry duplicates, and all readers resolve duplicates
                // last-wins, so updating only the first occurrence would make
                // the write invisible. Matches the Python writer's behavior.
                var searchStart = range.open + 1
                while let currentRange = frontmatterRange(in: lines),
                      let keyIndex = keyLineIndex(of: key, in: lines, range: currentRange, from: searchStart) {
                    let extent = valueExtent(at: keyIndex, in: lines, range: currentRange)
                    var terminatorText = terminator(of: lines[keyIndex])
                    if terminatorText.isEmpty { terminatorText = "\n" }
                    let replacement = formattedLines(key: key, value: value, terminator: terminatorText)
                    lines.replaceSubrange(extent, with: replacement)
                    searchStart = extent.lowerBound + replacement.count
                }
            } else {
                var terminatorText = terminator(of: lines[range.open])
                if terminatorText.isEmpty { terminatorText = "\n" }
                lines.insert(contentsOf: formattedLines(key: key, value: value, terminator: terminatorText),
                             at: range.close)
            }
        }

        if let newBody, let range = frontmatterRange(in: lines) {
            lines = Array(lines[range.open...range.close])
            if terminator(of: lines[lines.count - 1]).isEmpty {
                lines[lines.count - 1] += "\n"
            }
            let bodyText = newBody.trimmingCharacters(in: .whitespacesAndNewlines)
            if !bodyText.isEmpty {
                lines.append("\n")
                lines.append(bodyText + "\n")
            }
        }

        return lines.joined()
    }

    // MARK: - Line-level editing internals

    /// Frontmatter delimiter positions within a line array.
    internal struct FrontmatterRange {
        /// Index of the opening `---` line (always 0).
        let open: Int
        /// Index of the closing `---` line.
        let close: Int
    }

    /// Locates the frontmatter block in lines that keep their terminators.
    ///
    /// The closing delimiter must start at column zero: an indented `  ---`
    /// is a block scalar continuation line, never a delimiter (spec section 6
    /// tolerates trailing whitespace only).
    ///
    /// - Parameter lines: Lines including their original terminators.
    /// - Returns: The delimiter positions, or `nil` when the document has no
    ///   valid frontmatter (no opening `---` first line or no closing `---`).
    internal static func frontmatterRange(in lines: [String]) -> FrontmatterRange? {
        guard let first = lines.first,
              lineContent(first).trimmingCharacters(in: .whitespaces) == "---" else {
            return nil
        }
        for index in 1..<lines.count {
            let content = lineContent(lines[index])
            if content.first == " " || content.first == "\t" { continue }
            if content.trimmingCharacters(in: .whitespaces) == "---" {
                return FrontmatterRange(open: 0, close: index)
            }
        }
        return nil
    }

    /// Finds the next frontmatter line declaring the given key.
    ///
    /// Comment lines, blank lines, and indented continuation lines are never
    /// key lines, mirroring the lenient parser.
    ///
    /// - Parameters:
    ///   - key: Frontmatter key to find.
    ///   - lines: Lines including their terminators.
    ///   - range: The frontmatter delimiter positions.
    ///   - startIndex: First line index to consider, or `nil` to scan the
    ///     whole block (used to walk duplicate occurrences of a key).
    /// - Returns: The line index of the key at or after `startIndex`, or `nil`
    ///   when absent.
    internal static func keyLineIndex(of key: String, in lines: [String], range: FrontmatterRange,
                                      from startIndex: Int? = nil) -> Int? {
        let start = max(startIndex ?? (range.open + 1), range.open + 1)
        guard start < range.close else { return nil }
        for index in start..<range.close {
            let content = lineContent(lines[index])
            if content.first == " " || content.first == "\t" { continue }
            let trimmed = content.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty || trimmed.hasPrefix("#") { continue }
            guard let colon = content.firstIndex(of: ":") else { continue }
            if String(content[content.startIndex..<colon]).trimmingCharacters(in: .whitespaces) == key {
                return index
            }
        }
        return nil
    }

    /// Computes the full line extent of a key's value, including the indented
    /// continuation lines of a `|`/`>` block scalar (spec section 5.2: replacing
    /// a block-scalar key must remove its continuation lines too).
    ///
    /// - Parameters:
    ///   - keyIndex: Index of the `key: value` line.
    ///   - lines: Lines including their terminators.
    ///   - range: The frontmatter delimiter positions.
    /// - Returns: The half-open range of lines occupied by the key and its value.
    internal static func valueExtent(at keyIndex: Int, in lines: [String], range: FrontmatterRange) -> Range<Int> {
        let content = lineContent(lines[keyIndex])
        guard let colon = content.firstIndex(of: ":") else { return keyIndex..<(keyIndex + 1) }
        let after = String(content[content.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
        guard TicketParser.isBlockScalarMarker(after) else { return keyIndex..<(keyIndex + 1) }

        var lastIncluded = keyIndex
        var index = keyIndex + 1
        while index < range.close {
            let lineText = lineContent(lines[index])
            if lineText.first == " " || lineText.first == "\t" {
                lastIncluded = index
                index += 1
            } else if lineText.trimmingCharacters(in: .whitespaces).isEmpty {
                // Interior blank: included only if a later indented line follows.
                index += 1
            } else {
                break
            }
        }
        return keyIndex..<(lastIncluded + 1)
    }

    /// Formats the replacement line(s) for a key (spec section 5.1).
    ///
    /// `nil` writes the literal `null`; multiline values become a `|` block
    /// scalar with two-space indentation; single-line values are quoted only
    /// when required. Value newlines are normalized to `\n` first — a CRLF is
    /// a single grapheme that `contains("\n")` would miss, which would embed a
    /// raw CR LF into a scalar line.
    ///
    /// - Parameters:
    ///   - key: Frontmatter key.
    ///   - value: New value, or `nil` for the literal `null`.
    ///   - terminator: Line terminator to use (`\n` or `\r\n`).
    /// - Returns: One or more full lines including terminators.
    internal static func formattedLines(key: String, value: String?, terminator: String) -> [String] {
        guard let value else { return ["\(key): null\(terminator)"] }
        let normalized = value
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
        if normalized.contains("\n") {
            var lines = ["\(key): |\(terminator)"]
            for blockLine in normalized.components(separatedBy: "\n") {
                lines.append(blockLine.isEmpty ? terminator : "  \(blockLine)\(terminator)")
            }
            return lines
        }
        return ["\(key): \(formatScalar(normalized))\(terminator)"]
    }

    /// Quotes a scalar value only when the spec requires it: the value
    /// contains `: `, starts with a YAML-special character, or has leading or
    /// trailing whitespace (spec section 5.1).
    ///
    /// - Parameter value: Single-line value to format.
    /// - Returns: The value, double-quoted and escaped when needed.
    internal static func formatScalar(_ value: String) -> String {
        let specialLeading: Set<Character> = ["!", "&", "*", "-", "?", "|", ">", "%", "@", "`",
                                              "\"", "'", "#", "{", "}", "[", "]", ",", ":"]
        let needsQuoting = value.isEmpty
            || value.contains(": ")
            || specialLeading.contains(value.first ?? " ")
            || value != value.trimmingCharacters(in: .whitespaces)
        guard needsQuoting else { return value }
        let escaped = value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        return "\"\(escaped)\""
    }

    /// Splits text into lines that keep their original terminators, so
    /// untouched lines re-join byte-identical (`\n` and `\r\n` both supported).
    ///
    /// - Parameter text: Raw document text.
    /// - Returns: Lines including terminators; the final line may lack one.
    internal static func splitLinesKeepingTerminators(_ text: String) -> [String] {
        var lines: [String] = []
        var current = ""
        for character in text {
            current.append(character)
            // Note: "\r\n" is a single Swift Character (grapheme cluster).
            if character == "\n" || character == "\r\n" {
                lines.append(current)
                current = ""
            }
        }
        if !current.isEmpty { lines.append(current) }
        return lines
    }

    /// Returns a line's content without its terminator.
    ///
    /// Implemented on unicode scalars: `"\r\n"` is a single Swift `Character`
    /// (grapheme cluster) that is *not* equal to `"\n"`, so `Character`-level
    /// operations like `hasSuffix("\n")`/`dropLast` would fail to detect a
    /// CRLF terminator at all — terminator handling must happen at the
    /// unicode-scalar level.
    ///
    /// - Parameter line: A line possibly ending in `\n` or `\r\n`.
    /// - Returns: The content with the terminator removed.
    internal static func lineContent(_ line: String) -> String {
        var scalars = Substring(line).unicodeScalars
        if scalars.last == "\n" { scalars.removeLast() }
        if scalars.last == "\r" { scalars.removeLast() }
        return String(scalars)
    }

    /// Returns a line's terminator (`\r\n`, `\n`, or empty at EOF), determined
    /// at the unicode-scalar level for byte precision.
    ///
    /// - Parameter line: A line possibly ending in `\n` or `\r\n`.
    /// - Returns: The terminator string, possibly empty.
    internal static func terminator(of line: String) -> String {
        var scalars = Substring(line).unicodeScalars
        guard scalars.last == "\n" else { return "" }
        scalars.removeLast()
        return scalars.last == "\r" ? "\r\n" : "\n"
    }

    // MARK: - Shared helpers

    /// Formats a date per spec section 5.4: UTC, second precision,
    /// `YYYY-MM-DDTHH:MM:SSZ`.
    ///
    /// - Parameter date: The date to format.
    /// - Returns: The ISO 8601 UTC timestamp string.
    internal static func isoTimestamp(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter.string(from: date)
    }

    /// Writes content atomically: a hidden temp file in the same directory,
    /// then a rename over the original (spec section 5.3).
    ///
    /// - Parameters:
    ///   - content: Full document text to write.
    ///   - url: Destination ticket file (must already exist).
    /// - Throws: File system errors; the temp file is cleaned up on failure.
    internal static func atomicWrite(_ content: String, to url: URL) throws {
        let directory = url.deletingLastPathComponent()
        let tempURL = directory.appendingPathComponent(".\(url.lastPathComponent).\(UUID().uuidString).tmp")
        do {
            try Data(content.utf8).write(to: tempURL)
        } catch {
            // A failed write (e.g. volume full) can still leave a partial file.
            try? FileManager.default.removeItem(at: tempURL)
            logger.error("Atomic write failed: \((error as NSError).debugDescription, privacy: .public)")
            throw error
        }
        do {
            _ = try FileManager.default.replaceItemAt(url, withItemAt: tempURL)
        } catch {
            try? FileManager.default.removeItem(at: tempURL)
            logger.error("Atomic write failed: \((error as NSError).debugDescription, privacy: .public)")
            throw error
        }
    }
}
