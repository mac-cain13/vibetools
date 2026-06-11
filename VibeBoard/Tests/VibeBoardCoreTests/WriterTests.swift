//
//  WriterTests.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import XCTest
@testable import VibeBoardCore

/// Field-preserving writer cases mirroring format spec section 5.
final class WriterTests: XCTestCase {

    /// Fixed clock so `updated` is deterministic in assertions.
    private let fixedNow = Date(timeIntervalSince1970: 1_780_000_000)

    /// The spec-format timestamp for `fixedNow`.
    private var fixedTimestamp: String { TicketWriter.isoTimestamp(fixedNow) }

    /// A document exercising unknown keys, comments, quoting, a block scalar,
    /// and a body with its own structure.
    private let fixture = """
    ---
    # keep this comment
    id: vibe-3
    title: "Quoted: title"
    custom_future_key: must survive
    description: |
      Line one of the blurb.
      Line two of the blurb.
    state: doing
    branch: feature/retry-upload
    created: 2026-01-01T00:00:00Z
    updated: 2026-01-01T00:00:00Z
    ---

    Body text here.

    ## Next step

    Do the thing.
    """

    // MARK: - Round-trip preservation (spec section 5.2)

    func testStateChangeOnlyTouchesIntendedLines() {
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: ["state": "on_hold"],
                                                 body: nil, now: fixedNow)

        let originalLines = fixture.components(separatedBy: "\n")
        let outputLines = output.components(separatedBy: "\n")
        XCTAssertEqual(originalLines.count, outputLines.count)

        var changed: [(String, String)] = []
        for (old, new) in zip(originalLines, outputLines) where old != new {
            changed.append((old, new))
        }
        XCTAssertEqual(changed.count, 2, "only the state and updated lines may differ")
        XCTAssertTrue(changed.contains { $0.0 == "state: doing" && $0.1 == "state: on_hold" })
        XCTAssertTrue(changed.contains { $0.0 == "updated: 2026-01-01T00:00:00Z" && $0.1 == "updated: \(fixedTimestamp)" })
    }

    func testUnknownKeysCommentsOrderingAndBodyRoundTripByteIdentical() {
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: ["session_id": "abc123"],
                                                 body: nil, now: fixedNow)

        // Everything from the original must survive except the updated line;
        // the new key's line is inserted before the closing delimiter.
        XCTAssertTrue(output.contains("# keep this comment\n"))
        XCTAssertTrue(output.contains("custom_future_key: must survive\n"))
        XCTAssertTrue(output.contains("title: \"Quoted: title\"\n"))
        XCTAssertTrue(output.contains("description: |\n  Line one of the blurb.\n  Line two of the blurb.\n"))
        XCTAssertTrue(output.contains("\nBody text here.\n\n## Next step\n\nDo the thing."))
        XCTAssertTrue(output.contains("session_id: abc123\n---"), "missing key inserts before closing ---")

        // Key ordering of existing keys is untouched.
        let idIndex = output.range(of: "id: vibe-3")!.lowerBound
        let customIndex = output.range(of: "custom_future_key")!.lowerBound
        let stateIndex = output.range(of: "state: doing")!.lowerBound
        XCTAssertLessThan(idIndex, customIndex)
        XCTAssertLessThan(customIndex, stateIndex)
    }

    func testUpdatedIsAlwaysRefreshed() {
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: [:],
                                                 body: nil, now: fixedNow)
        XCTAssertTrue(output.contains("updated: \(fixedTimestamp)\n"))
        XCTAssertFalse(output.contains("updated: 2026-01-01T00:00:00Z"))
    }

    func testTimestampFormatIsSpecCompliant() {
        let timestamp = TicketWriter.isoTimestamp(Date(timeIntervalSince1970: 0))
        XCTAssertEqual(timestamp, "1970-01-01T00:00:00Z")
    }

    // MARK: - Block scalars (spec section 5.2)

    func testReplacingBlockScalarRemovesContinuationLines() {
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: ["description": "One line now."],
                                                 body: nil, now: fixedNow)
        XCTAssertTrue(output.contains("description: One line now.\n"))
        XCTAssertFalse(output.contains("Line one of the blurb."))
        XCTAssertFalse(output.contains("Line two of the blurb."))
        // The keys around the block survive.
        XCTAssertTrue(output.contains("custom_future_key: must survive\n"))
        XCTAssertTrue(output.contains("state: doing\n"))
    }

    func testSettingMultilineValueWritesBlockScalar() {
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: ["description": "New first.\nNew second."],
                                                 body: nil, now: fixedNow)
        XCTAssertTrue(output.contains("description: |\n  New first.\n  New second.\n"))
        // Round-trips through the lenient parser.
        let ticket = TicketParser.parse(content: output, filenameStem: "vibe-3")
        XCTAssertEqual(ticket.fields["description"], "New first.\nNew second.")
    }

    func testBlockScalarContainingHorizontalRuleRoundTrips() {
        // The indented `  ---` continuation line must not be mistaken for the
        // closing delimiter: no field may leak into the body and `updated`
        // must land outside the block.
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: ["description": "Intro\n---\nOutro"],
                                                 body: nil, now: fixedNow)
        XCTAssertTrue(output.contains("description: |\n  Intro\n  ---\n  Outro\n"))
        let ticket = TicketParser.parse(content: output, filenameStem: "vibe-3")
        XCTAssertEqual(ticket.fields["description"], "Intro\n---\nOutro")
        XCTAssertEqual(ticket.fields["state"], "doing")
        XCTAssertEqual(ticket.fields["updated"], fixedTimestamp)
        XCTAssertTrue(ticket.body.hasPrefix("Body text here."))
    }

    func testReplacingValueWithInvalidBlockMarkerKeepsFollowingLines() {
        // `|pipe-thing` is a plain scalar (invalid block header), so updating
        // it must not swallow the indented line that follows.
        let content = """
        ---
        id: vibe-2
        branch: |pipe-thing
          - keep this stray indented line
        state: todo
        ---
        """
        let output = TicketWriter.updatedContent(of: content,
                                                 settingFields: ["branch": "feature/clean"],
                                                 body: nil, now: fixedNow)
        XCTAssertTrue(output.contains("branch: feature/clean\n"))
        XCTAssertTrue(output.contains("  - keep this stray indented line\n"))
        XCTAssertTrue(output.contains("state: todo\n"))
    }

    // MARK: - Duplicate keys (hand-edited tickets)

    func testDuplicateKeyUpdateRewritesEveryOccurrence() {
        // Readers resolve duplicates last-wins, so the writer must converge
        // every occurrence on the new value (matching the Python writer).
        let content = "---\nid: vibe-4\nstate: todo\nstate: doing\n---\nBody.\n"
        let output = TicketWriter.updatedContent(of: content,
                                                 settingFields: ["state": "ready"],
                                                 body: nil, now: fixedNow)
        XCTAssertFalse(output.contains("state: todo"))
        XCTAssertFalse(output.contains("state: doing"))
        XCTAssertEqual(output.components(separatedBy: "state: ready\n").count - 1, 2,
                       "every duplicate occurrence is rewritten")
        let ticket = TicketParser.parse(content: output, filenameStem: "vibe-4")
        XCTAssertEqual(ticket.fields["state"], "ready")
        XCTAssertEqual(ticket.body, "Body.")
    }

    // MARK: - Inserting and null (spec section 5.1 / 5.2)

    func testInsertMissingKeyBeforeClosingDelimiter() {
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: ["worktree": "/Volumes/External/Repositories/_vibecoding/vibe/x"],
                                                 body: nil, now: fixedNow)
        let frontmatterEnd = output.range(of: "\n---\n\n")!.lowerBound
        let insertedIndex = output.range(of: "worktree: /Volumes/External/Repositories/_vibecoding/vibe/x")!.lowerBound
        XCTAssertLessThan(insertedIndex, frontmatterEnd)
    }

    func testNilValueWritesNullLiteral() {
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: ["branch": nil],
                                                 body: nil, now: fixedNow)
        XCTAssertTrue(output.contains("branch: null\n"))
        let ticket = TicketParser.parse(content: output, filenameStem: "vibe-3")
        XCTAssertNil(ticket.branch)
    }

    func testQuotingOnlyWhenRequired() {
        XCTAssertEqual(TicketWriter.formatScalar("plain value"), "plain value")
        XCTAssertEqual(TicketWriter.formatScalar("colon: separated"), "\"colon: separated\"")
        XCTAssertEqual(TicketWriter.formatScalar("-leading-dash"), "\"-leading-dash\"")
        XCTAssertEqual(TicketWriter.formatScalar("feature/retry"), "feature/retry")
        XCTAssertEqual(TicketWriter.formatScalar(""), "\"\"")
    }

    // MARK: - Body edits

    func testBodyReplacementPreservesFrontmatter() {
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: [:],
                                                 body: "Completely new notes.\n\n## Next step\n\nNew step.",
                                                 now: fixedNow)
        XCTAssertTrue(output.contains("custom_future_key: must survive\n"))
        XCTAssertTrue(output.contains("description: |\n  Line one of the blurb.\n"))
        XCTAssertTrue(output.hasSuffix("---\n\nCompletely new notes.\n\n## Next step\n\nNew step.\n"))
        XCTAssertFalse(output.contains("Body text here."))
    }

    func testEmptyBodyLeavesOnlyFrontmatter() {
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: [:],
                                                 body: "", now: fixedNow)
        XCTAssertTrue(output.hasSuffix("---\n"))
        XCTAssertFalse(output.contains("Body text here."))
    }

    // MARK: - CRLF (spec section 6 tolerance, preserved on write)

    func testValueWithCRLFNewlinesIsWrittenAsBlockScalar() {
        // "\r\n" is a single grapheme that a Character-level contains("\n")
        // misses; the value's newlines must be normalized so it becomes a
        // block scalar instead of a scalar line with an embedded raw CR LF.
        let output = TicketWriter.updatedContent(of: fixture,
                                                 settingFields: ["title": "line1\r\nline2"],
                                                 body: nil, now: fixedNow)
        XCTAssertTrue(output.contains("title: |\n  line1\n  line2\n"))
        let ticket = TicketParser.parse(content: output, filenameStem: "vibe-3")
        XCTAssertEqual(ticket.title, "line1\nline2")
        XCTAssertEqual(ticket.fields["state"], "doing")
    }

    func testCRLFLinesUntouchedKeepTheirEndings() {
        let crlf = "---\r\nid: vibe-1\r\nstate: doing\r\nupdated: 2026-01-01T00:00:00Z\r\n---\r\nBody.\r\n"
        let output = TicketWriter.updatedContent(of: crlf,
                                                 settingFields: ["state": "ready"],
                                                 body: nil, now: fixedNow)
        XCTAssertTrue(output.contains("id: vibe-1\r\n"), "untouched line keeps CRLF")
        XCTAssertTrue(output.contains("state: ready\r\n"), "replaced line matches the file's ending")
        XCTAssertTrue(output.contains("updated: \(fixedTimestamp)\r\n"))
        XCTAssertTrue(output.contains("Body.\r\n"))
    }

    // MARK: - Missing frontmatter

    func testNoFrontmatterSynthesizesBlockAndKeepsContentAsBody() {
        let original = "Just a hand-written note.\n"
        let output = TicketWriter.updatedContent(of: original,
                                                 settingFields: ["state": "todo"],
                                                 body: nil, now: fixedNow)
        XCTAssertTrue(output.hasPrefix("---\n"))
        XCTAssertTrue(output.contains("state: todo\n"))
        XCTAssertTrue(output.contains("updated: \(fixedTimestamp)\n"))
        XCTAssertTrue(output.contains("Just a hand-written note."))
        let ticket = TicketParser.parse(content: output, filenameStem: "vibe-1")
        XCTAssertEqual(ticket.fields["state"], "todo")
        XCTAssertEqual(ticket.body, "Just a hand-written note.")
    }

    // MARK: - On-disk update (atomic write path)

    func testUpdateOnDiskWritesAtomicallyAndLeavesNoTempFiles() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("vibeboard-writer-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let url = directory.appendingPathComponent("vibe-1.md")
        try Data(fixture.utf8).write(to: url)

        try TicketWriter.update(fileAt: url, settingFields: ["state": "archived"], now: fixedNow)

        let content = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(content.contains("state: archived\n"))
        XCTAssertTrue(content.contains("custom_future_key: must survive\n"))

        let leftovers = try FileManager.default.contentsOfDirectory(atPath: directory.path)
            .filter { $0.contains(".tmp") }
        XCTAssertEqual(leftovers, [], "no temp files may remain after an atomic update")
    }
}
