//
//  ParserTests.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import XCTest
@testable import VibeBoardCore

/// Parser leniency cases mirroring format spec section 6.
final class ParserTests: XCTestCase {

    /// Parses content with a default filename stem.
    ///
    /// - Parameters:
    ///   - content: Ticket file content.
    ///   - stem: Filename stem to use as fallback identity.
    /// - Returns: The parsed ticket.
    private func parse(_ content: String, stem: String = "vibe-7") -> Ticket {
        return TicketParser.parse(content: content, filenameStem: stem)
    }

    // MARK: - Happy path

    func testParsesSimpleFrontmatterAndBody() {
        let ticket = parse("""
        ---
        id: vibe-12
        title: Retry logic for upload client
        repo: vibe
        branch: feature/retry-upload
        state: on_hold
        priority: high
        tool: claude
        created: 2026-06-10T14:30:00Z
        updated: 2026-06-10T15:00:00Z
        ---

        Freeform body.

        ## Next step

        Wire the backoff cap into the retry loop.
        """)

        XCTAssertEqual(ticket.ticketID, "vibe-12")
        XCTAssertEqual(ticket.title, "Retry logic for upload client")
        XCTAssertEqual(ticket.repo, "vibe")
        XCTAssertEqual(ticket.branch, "feature/retry-upload")
        // state is no longer a typed accessor; it survives only as a raw field.
        XCTAssertEqual(ticket.fields["state"], "on_hold")
        // priority is a retired field — tolerated and preserved as a raw key.
        XCTAssertEqual(ticket.fields["priority"], "high")
        XCTAssertEqual(ticket.tool, .claude)
        XCTAssertNotNil(ticket.created)
        XCTAssertNotNil(ticket.updated)
        XCTAssertTrue(ticket.body.hasPrefix("Freeform body."))
        XCTAssertTrue(ticket.body.contains("## Next step"))
    }

    // MARK: - Tolerances (spec section 6)

    func testToleratesCRLFLineEndings() {
        let content = "---\r\nid: vibe-3\r\nstate: on_hold\r\n---\r\n\r\nBody line.\r\n"
        let ticket = parse(content)
        XCTAssertEqual(ticket.ticketID, "vibe-3")
        XCTAssertEqual(ticket.fields["state"], "on_hold")
        XCTAssertEqual(ticket.body, "Body line.")
    }

    func testToleratesCommentsBlankLinesAndTrailingWhitespace() {
        let ticket = parse("""
        ---
        # this is a comment
        id: vibe-4

        state: on_hold
        # another comment
        ---
        Body.
        """)
        XCTAssertEqual(ticket.ticketID, "vibe-4")
        XCTAssertEqual(ticket.fields["state"], "on_hold")
        XCTAssertNil(ticket.fields["# this is a comment"])
    }

    func testStripsOneLayerOfMatchingQuotes() {
        let ticket = parse("""
        ---
        title: "Quoted: with colon"
        repo: 'single quoted'
        description: "escaped \\"quote\\" inside"
        ---
        """)
        XCTAssertEqual(ticket.title, "Quoted: with colon")
        XCTAssertEqual(ticket.repo, "single quoted")
        XCTAssertEqual(ticket.fields["description"], "escaped \"quote\" inside")
    }

    func testParsesBlockScalarDescription() {
        let ticket = parse("""
        ---
        id: vibe-9
        description: |
          Add bounded retry with backoff
          to the upload client.
        state: on_hold
        ---
        Body.
        """)
        XCTAssertEqual(ticket.fields["description"],
                       "Add bounded retry with backoff\nto the upload client.")
        XCTAssertEqual(ticket.cardDescription,
                       "Add bounded retry with backoff\nto the upload client.")
        // The key after the block must still parse.
        XCTAssertEqual(ticket.fields["state"], "on_hold")
    }

    func testParsesBlockScalarWithInteriorBlankLine() {
        let ticket = parse("""
        ---
        description: |
          First paragraph.

          Second paragraph.
        state: on_hold
        ---
        """)
        XCTAssertEqual(ticket.fields["description"], "First paragraph.\n\nSecond paragraph.")
        XCTAssertEqual(ticket.fields["state"], "on_hold")
    }

    func testValueStartingWithMarkerButInvalidHeaderIsPlainScalar() {
        // `>hello` / `|pipe-thing` are not block-scalar headers (only +, -,
        // and digits may follow the marker) — they read as plain scalars,
        // matching the Python implementation.
        let ticket = parse("""
        ---
        title: >hello
        branch: |pipe-thing
        state: on_hold
        ---
        """)
        XCTAssertEqual(ticket.title, ">hello")
        XCTAssertEqual(ticket.branch, "|pipe-thing")
        XCTAssertEqual(ticket.fields["state"], "on_hold")
    }

    func testBlockScalarHeaderWithChompingIndicatorStillParses() {
        let ticket = parse("""
        ---
        description: |-
          Chomped block.
        state: on_hold
        ---
        """)
        XCTAssertEqual(ticket.fields["description"], "Chomped block.")
        XCTAssertEqual(ticket.fields["state"], "on_hold")
    }

    func testIndentedDashesInsideBlockScalarAreNotClosingDelimiter() {
        // A Markdown horizontal rule inside a block scalar is a continuation
        // line, never the closing `---` (delimiters must be at column zero).
        let ticket = parse("""
        ---
        id: vibe-6
        description: |
          Intro
          ---
          Outro
        state: on_hold
        ---
        Body.
        """)
        XCTAssertEqual(ticket.fields["description"], "Intro\n---\nOutro")
        XCTAssertEqual(ticket.fields["state"], "on_hold")
        XCTAssertEqual(ticket.body, "Body.")
    }

    // MARK: - Duplicate keys (hand-edited tickets; last-wins resolution)

    func testDuplicateKeysResolveLastWins() {
        let ticket = parse("---\nbranch: feature-a\nbranch: feature-b\n---\n")
        XCTAssertEqual(ticket.branch, "feature-b")
    }

    func testLaterNullDuplicateClearsEarlierValue() {
        let ticket = parse("---\nbranch: feature-x\nbranch: null\n---\n")
        XCTAssertNil(ticket.branch)
    }

    func testEmptyAndNullValuesReadAsAbsent() {
        let ticket = parse("""
        ---
        id: vibe-5
        branch:
        worktree: null
        session_id: ~
        ---
        """)
        XCTAssertNil(ticket.branch)
        XCTAssertNil(ticket.worktreePath)
        XCTAssertNil(ticket.sessionID)
    }

    // MARK: - Malformed frontmatter (never drop a ticket)

    func testMissingFrontmatterTreatsWholeFileAsBody() {
        let ticket = parse("Just a plain note.\n\nWith two paragraphs.\n", stem: "bezel-3")
        XCTAssertEqual(ticket.ticketID, "bezel-3")
        XCTAssertEqual(ticket.repo, "bezel")
        XCTAssertNil(ticket.fields["state"])
        XCTAssertTrue(ticket.body.hasPrefix("Just a plain note."))
        XCTAssertEqual(ticket.fields, [:])
    }

    func testMissingClosingDelimiterTreatsWholeFileAsBody() {
        let content = "---\nid: vibe-12\nno closing delimiter here\n"
        let ticket = parse(content, stem: "vibe-12")
        XCTAssertEqual(ticket.ticketID, "vibe-12")
        XCTAssertEqual(ticket.fields, [:])
        XCTAssertTrue(ticket.body.contains("id: vibe-12"))
    }

    func testEmptyFileStillProducesTicket() {
        let ticket = parse("", stem: "vibe-1")
        XCTAssertEqual(ticket.ticketID, "vibe-1")
        XCTAssertNil(ticket.fields["state"])
        XCTAssertEqual(ticket.body, "")
    }

    // MARK: - Raw fields preserved (spec section 6: never drop unknown keys)

    func testStateIsPreservedAsRawField() {
        // The app no longer acts on state; the parser keeps it verbatim so a
        // field-preserving write round-trips it.
        let ticket = parse("---\nstate: on_hold\n---\n")
        XCTAssertEqual(ticket.fields["state"], "on_hold")
    }

    func testUnknownStateValueIsPreservedVerbatim() {
        let ticket = parse("---\nstate: blocked\n---\n")
        XCTAssertEqual(ticket.fields["state"], "blocked")
    }

    func testRetiredPriorityFieldIsPreserved() {
        // priority is retired but still tolerated: kept verbatim in fields so
        // a field-preserving write round-trips it on legacy tickets.
        let ticket = parse("---\npriority: urgent\n---\n")
        XCTAssertEqual(ticket.fields["priority"], "urgent")
    }

    func testUnknownToolReadsAsNil() {
        let ticket = parse("---\ntool: cursor\n---\n")
        XCTAssertNil(ticket.tool)
    }

    // MARK: - Defaults (spec section 6)

    func testDefaultsWhenKeysMissing() {
        let ticket = parse("---\n---\n", stem: "myrepo-42")
        XCTAssertEqual(ticket.ticketID, "myrepo-42")
        XCTAssertEqual(ticket.title, "myrepo-42")
        XCTAssertEqual(ticket.repo, "myrepo")
        XCTAssertNil(ticket.fields["state"])
        XCTAssertNil(ticket.branch)
        XCTAssertNil(ticket.worktreePath)
        XCTAssertNil(ticket.sessionID)
        XCTAssertNil(ticket.cardDescription)
    }

    func testRepoFallbackWithoutDigitSuffix() {
        // No trailing -<digits>: the id is used unchanged.
        XCTAssertEqual(Ticket.repoName(fromID: "noNumber"), "noNumber")
        XCTAssertEqual(Ticket.repoName(fromID: "repo-name-12"), "repo-name")
        XCTAssertEqual(Ticket.repoName(fromID: "repo-12x"), "repo-12x")
    }

    func testDescriptionFallsBackToFirstBodyParagraph() {
        let ticket = parse("""
        ---
        id: vibe-2
        ---

        First paragraph line one
        continues on line two.

        Second paragraph.
        """)
        XCTAssertEqual(ticket.cardDescription, "First paragraph line one continues on line two.")
    }

    func testExplicitDescriptionWinsOverBody() {
        let ticket = parse("""
        ---
        description: The blurb.
        ---
        Body paragraph.
        """)
        XCTAssertEqual(ticket.cardDescription, "The blurb.")
    }

    // MARK: - Park-owned body sections (spec section 7)

    func testExtractsBraindumpAndNextStepSections() {
        let ticket = parse("""
        ---
        id: vibe-12
        ---

        Some background the agent wrote.

        ## Braindump

        Tried the v2 upload API but its auth is flaky.
        Maybe just pin v1.

        ## Next step

        Context: client times out on slow networks.
        Wire the backoff cap, then rerun the tests.
        """)
        XCTAssertEqual(ticket.braindump,
                       "Tried the v2 upload API but its auth is flaky.\nMaybe just pin v1.")
        XCTAssertEqual(ticket.nextStep,
                       "Context: client times out on slow networks.\nWire the backoff cap, then rerun the tests.")
        XCTAssertEqual(ticket.freeformNotes, "Some background the agent wrote.")
    }

    func testBraindumpIsNilWhenAbsent() {
        let ticket = parse("""
        ---
        id: vibe-12
        ---

        Background.

        ## Next step

        Do the thing.
        """)
        XCTAssertNil(ticket.braindump)
        XCTAssertEqual(ticket.nextStep, "Do the thing.")
        XCTAssertEqual(ticket.freeformNotes, "Background.")
    }

    func testFreeformNotesIsNilWhenBodyIsOnlyParkSections() {
        let ticket = parse("""
        ---
        id: vibe-12
        ---

        ## Braindump

        My thoughts.

        ## Next step

        The next step.
        """)
        XCTAssertEqual(ticket.braindump, "My thoughts.")
        XCTAssertEqual(ticket.nextStep, "The next step.")
        XCTAssertNil(ticket.freeformNotes)
    }

    func testSectionHeadingMatchIsCaseInsensitiveAndSectionRunsToNextHeading() {
        let ticket = parse("""
        ---
        id: vibe-12
        ---

        ## BRAINDUMP

        Line one.

        ### A subheading stays inside the section

        Line two.

        ## Next step

        Next.
        """)
        XCTAssertEqual(ticket.braindump,
                       "Line one.\n\n### A subheading stays inside the section\n\nLine two.")
        XCTAssertEqual(ticket.nextStep, "Next.")
    }

    func testEmptyParkSectionReadsAsNil() {
        let ticket = parse("""
        ---
        id: vibe-12
        ---

        ## Braindump

        ## Next step

        Only the next step has content.
        """)
        XCTAssertNil(ticket.braindump)
        XCTAssertEqual(ticket.nextStep, "Only the next step has content.")
    }

    // MARK: - Unknown keys

    func testUnknownKeysAreExposedNotFatal() {
        let ticket = parse("""
        ---
        id: vibe-8
        some_future_field: kept
        state: on_hold
        ---
        """)
        XCTAssertEqual(ticket.fields["some_future_field"], "kept")
        XCTAssertEqual(ticket.fields["state"], "on_hold")
    }
}
