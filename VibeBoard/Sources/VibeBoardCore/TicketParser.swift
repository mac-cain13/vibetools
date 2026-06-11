//
//  TicketParser.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import Foundation

/// Lenient ticket parser (format spec section 6 — hard requirement).
///
/// Tolerates CRLF line endings, trailing whitespace, `#` comment lines,
/// quoted scalar values, `|`/`>` block scalars, empty values, and missing or
/// malformed frontmatter. A ticket is never dropped: a file without valid
/// frontmatter parses as all-body with the id derived from the filename.
public enum TicketParser {

    /// Parses a ticket file's content, deriving the filename stem from the URL.
    ///
    /// - Parameters:
    ///   - content: Full file content (UTF-8 text).
    ///   - fileURL: The on-disk location; its stem is the id fallback.
    /// - Returns: The parsed ticket; never fails.
    public static func parse(content: String, fileURL: URL) -> Ticket {
        let stem = fileURL.deletingPathExtension().lastPathComponent
        return parse(content: content, filenameStem: stem, fileURL: fileURL)
    }

    /// Parses ticket content with an explicit filename stem.
    ///
    /// - Parameters:
    ///   - content: Full file content (UTF-8 text).
    ///   - filenameStem: File name without the `.md` extension (id fallback).
    ///   - fileURL: The on-disk location, or `nil` when not file-backed.
    /// - Returns: The parsed ticket; never fails.
    public static func parse(content: String, filenameStem: String, fileURL: URL? = nil) -> Ticket {
        // Split into logical lines; strip a trailing CR so CRLF files parse identically.
        let lines = content.components(separatedBy: "\n").map { line -> String in
            line.hasSuffix("\r") ? String(line.dropLast()) : line
        }

        // Frontmatter requires `---` as the very first line and a closing `---` line.
        guard let first = lines.first,
              first.trimmingCharacters(in: .whitespaces) == "---",
              let close = closingDelimiterIndex(in: lines) else {
            // Malformed/missing frontmatter: the entire file is body (spec section 6).
            return Ticket(fileURL: fileURL,
                          filenameStem: filenameStem,
                          fields: [:],
                          body: normalizeBody(content.replacingOccurrences(of: "\r\n", with: "\n")))
        }

        var fields: [String: String] = [:]
        var index = 1
        while index < close {
            let line = lines[index]
            index += 1

            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty || trimmed.hasPrefix("#") { continue }
            // A stray indented line outside a block scalar is tolerated and skipped.
            if line.first == " " || line.first == "\t" { continue }
            guard let colon = line.firstIndex(of: ":") else { continue }

            let key = String(line[line.startIndex..<colon]).trimmingCharacters(in: .whitespaces)
            guard !key.isEmpty else { continue }
            let rawValue = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)

            if isBlockScalarMarker(rawValue) {
                let (value, nextIndex) = parseBlockScalar(lines: lines, startingAt: index, close: close)
                index = nextIndex
                if !value.isEmpty { fields[key] = value }
                continue
            }

            let value = unquote(rawValue)
            // Empty values and the null literals read as absent (spec section 6).
            // A later duplicate also clears an earlier value, keeping duplicate
            // resolution consistently last-wins.
            if value.isEmpty || value == "null" || value == "~" {
                fields.removeValue(forKey: key)
                continue
            }
            fields[key] = value
        }

        let body = normalizeBody(lines[(close + 1)...].joined(separator: "\n"))
        return Ticket(fileURL: fileURL, filenameStem: filenameStem, fields: fields, body: body)
    }

    // MARK: - Internals

    /// Finds the index of the closing `---` delimiter line.
    ///
    /// The delimiter must start at column zero: an indented `  ---` is a block
    /// scalar continuation line, never a delimiter (spec section 6 tolerates
    /// trailing whitespace only).
    ///
    /// - Parameter lines: Logical lines of the document (CR already stripped).
    /// - Returns: The index of the first `---` line after line zero, or `nil`.
    internal static func closingDelimiterIndex(in lines: [String]) -> Int? {
        for index in 1..<lines.count {
            let line = lines[index]
            if line.first == " " || line.first == "\t" { continue }
            if line.trimmingCharacters(in: .whitespaces) == "---" { return index }
        }
        return nil
    }

    /// Checks whether a raw scalar value is a block-scalar header: `|` or `>`
    /// followed only by chomping/indent indicators (`+`, `-`, digits), such as
    /// `|`, `|-`, or `>2`. Anything else after the marker (e.g. `>hello`) is a
    /// plain scalar, matching the Python implementation's marker validation.
    ///
    /// - Parameter value: Trimmed raw value from a `key: value` line.
    /// - Returns: Whether the value introduces a block scalar.
    internal static func isBlockScalarMarker(_ value: String) -> Bool {
        guard let first = value.first, first == "|" || first == ">" else { return false }
        return value.dropFirst().allSatisfy { "+-0123456789".contains($0) }
    }

    /// Collects the indented continuation lines of a `|`/`>` block scalar.
    ///
    /// Continuation lines are those starting with whitespace; blank lines are
    /// included when followed by another indented line (YAML allows interior
    /// blanks). Indentation common to the block (taken from its first
    /// non-empty line) is stripped.
    ///
    /// - Parameters:
    ///   - lines: Logical lines of the document.
    ///   - start: Index of the first line after the `key: |` line.
    ///   - close: Index of the closing `---` delimiter (exclusive bound).
    /// - Returns: The joined block value (edge newlines trimmed) and the index
    ///   of the first line after the block.
    internal static func parseBlockScalar(lines: [String], startingAt start: Int, close: Int) -> (value: String, nextIndex: Int) {
        var blockLines: [String] = []
        var pendingBlanks = 0
        var index = start
        while index < close {
            let line = lines[index]
            if line.first == " " || line.first == "\t" {
                blockLines.append(contentsOf: Array(repeating: "", count: pendingBlanks))
                pendingBlanks = 0
                blockLines.append(line)
                index += 1
            } else if line.trimmingCharacters(in: .whitespaces).isEmpty {
                pendingBlanks += 1
                index += 1
            } else {
                break
            }
        }

        let indent = blockLines
            .first { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
            .map { String($0.prefix(while: { $0 == " " })) } ?? ""
        let stripped = blockLines.map { line -> String in
            line.hasPrefix(indent) ? String(line.dropFirst(indent.count)) : line
        }
        let value = stripped.joined(separator: "\n").trimmingCharacters(in: .newlines)
        return (value, index)
    }

    /// Strips one layer of matching single or double quotes from a scalar.
    ///
    /// - Parameter value: Trimmed raw scalar value from a frontmatter line.
    /// - Returns: The unquoted value with quote escapes resolved, or the input
    ///   unchanged when it is not quoted.
    internal static func unquote(_ value: String) -> String {
        guard value.count >= 2, let first = value.first, let last = value.last,
              first == last, first == "\"" || first == "'" else {
            return value
        }
        let inner = String(value.dropFirst().dropLast())
        if first == "\"" {
            return inner
                .replacingOccurrences(of: "\\\"", with: "\"")
                .replacingOccurrences(of: "\\\\", with: "\\")
        }
        return inner.replacingOccurrences(of: "''", with: "'")
    }

    /// Trims whitespace and newlines from the edges of the body for display
    /// and editing; interior content is untouched.
    ///
    /// - Parameter text: Raw body text after the closing delimiter.
    /// - Returns: The edge-trimmed body.
    internal static func normalizeBody(_ text: String) -> String {
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
