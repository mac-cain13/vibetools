//
//  StoreTests.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import XCTest
@testable import VibeBoardCore

/// TicketStore mutation cases: the guarded body save (never silently
/// overwrite another writer's body, spec section 5.5) and title editing.
final class StoreTests: XCTestCase {

    private var storeDirectory: URL!

    override func setUpWithError() throws {
        storeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("vibeboard-store-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: storeDirectory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: storeDirectory)
    }

    /// Writes a ticket file into the store directory.
    ///
    /// - Parameters:
    ///   - name: File name to create.
    ///   - content: Full document content.
    /// - Returns: The URL of the written file.
    @discardableResult
    private func write(_ name: String, content: String) throws -> URL {
        let url = storeDirectory.appendingPathComponent(name)
        try Data(content.utf8).write(to: url)
        return url
    }

    /// A minimal ticket document with the given body.
    ///
    /// - Parameter body: Body text after the closing delimiter.
    /// - Returns: The full document content.
    private func document(body: String) -> String {
        return "---\nid: vibe-1\ntitle: Original title\nstate: doing\n---\n\n\(body)\n"
    }

    // MARK: - Guarded body save (spec section 5.5)

    @MainActor
    func testSaveBodySucceedsWhenOnDiskBodyMatchesSnapshot() throws {
        let url = try write("vibe-1.md", content: document(body: "Original notes."))
        let store = TicketStore(storeURL: storeDirectory)
        store.reload()

        let outcome = store.saveBody("Edited notes.", forTicketID: "vibe-1",
                                     ifBodyMatches: "Original notes.")

        XCTAssertEqual(outcome, .saved)
        let content = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(content.contains("Edited notes."))
        XCTAssertTrue(content.contains("title: Original title\n"), "frontmatter survives a body save")
    }

    @MainActor
    func testSaveBodyRefusesWhenBodyChangedOnDiskSinceSnapshot() throws {
        let url = try write("vibe-1.md", content: document(body: "Original notes."))
        let store = TicketStore(storeURL: storeDirectory)
        store.reload()

        // Another writer (e.g. a park writing "## Next step") changes the
        // body while the editor still holds the stale snapshot.
        let parkedBody = "Original notes.\n\n## Next step\n\nResume from the park note."
        try TicketWriter.update(fileAt: url, settingFields: ["branch": "feature/x"], body: parkedBody)

        let outcome = store.saveBody("Edited from a stale snapshot.", forTicketID: "vibe-1",
                                     ifBodyMatches: "Original notes.")

        XCTAssertEqual(outcome, .conflict)
        let content = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(content.contains("## Next step"), "the concurrent writer's body survives")
        XCTAssertFalse(content.contains("Edited from a stale snapshot."))
    }

    @MainActor
    func testSaveBodyWithoutSnapshotOverwritesUnconditionally() throws {
        let url = try write("vibe-1.md", content: document(body: "Original notes."))
        let store = TicketStore(storeURL: storeDirectory)
        store.reload()

        try TicketWriter.update(fileAt: url, settingFields: [:], body: "Concurrent change.")

        let outcome = store.saveBody("Forced overwrite.", forTicketID: "vibe-1")

        XCTAssertEqual(outcome, .saved)
        let content = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(content.contains("Forced overwrite."))
    }

    @MainActor
    func testSaveBodyForUnknownTicketFailsAndSetsLastError() throws {
        let store = TicketStore(storeURL: storeDirectory)
        store.reload()

        let outcome = store.saveBody("Anything.", forTicketID: "vibe-99",
                                     ifBodyMatches: "Whatever.")

        XCTAssertEqual(outcome, .failed)
        XCTAssertNotNil(store.lastError)
    }

    // MARK: - Title editing (spec section 4: editable in the app)

    @MainActor
    func testSetTitleWritesTitleFieldPreservingEverythingElse() throws {
        let url = try write("vibe-1.md", content: document(body: "Notes."))
        let store = TicketStore(storeURL: storeDirectory)
        store.reload()

        store.setTitle("Renamed title", forTicketID: "vibe-1")

        let content = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(content.contains("title: Renamed title\n"))
        XCTAssertTrue(content.contains("state: doing\n"))
        XCTAssertTrue(content.contains("Notes."))
        XCTAssertEqual(store.tickets.first?.title, "Renamed title")
    }

    // MARK: - Loading and filename rule (spec section 1)

    @MainActor
    func testLoadTicketsReadsOnlyTicketFilesAndSortsByFilename() throws {
        try write("vibe-2.md", content: document(body: "Two."))
        try write("vibe-1.md", content: document(body: "One."))
        try write("README.md", content: "not a ticket")
        try write(".DS_Store", content: "junk")

        let store = TicketStore(storeURL: storeDirectory)
        store.reload()

        XCTAssertEqual(store.tickets.map(\.id), ["vibe-1", "vibe-2"])
    }

    func testTicketFilenameRule() {
        XCTAssertTrue(TicketStore.isTicketFilename("vibe-12.md"))
        XCTAssertTrue(TicketStore.isTicketFilename("repo-name-3.md"))
        XCTAssertFalse(TicketStore.isTicketFilename(".DS_Store"))
        XCTAssertFalse(TicketStore.isTicketFilename("README.md"))
        XCTAssertFalse(TicketStore.isTicketFilename("vibe-12.md.tmp"))
        XCTAssertFalse(TicketStore.isTicketFilename(".vibe-12.md.abc.tmp"))
        XCTAssertFalse(TicketStore.isTicketFilename("vibe-.md"))
        XCTAssertFalse(TicketStore.isTicketFilename("-12.md"))
        XCTAssertFalse(TicketStore.isTicketFilename("vibe-12.markdown"))
    }

    // MARK: - Resume command

    func testResumeCommandForSafeID() {
        XCTAssertEqual(ResumeCommand.command(forTicketID: "vibe-12"), "vibe resume vibe-12")
    }

    func testResumeCommandQuotesUnsafeID() {
        XCTAssertEqual(ResumeCommand.command(forTicketID: "weird id; rm -rf"),
                       "vibe resume 'weird id; rm -rf'")
        XCTAssertEqual(ResumeCommand.shellQuote("it's"), "'it'\\''s'")
    }
}

extension StoreTests {

    // MARK: - Change diffing (drives park/resume notifications)

    @MainActor
    func testReloadReportsAddedAndRemovedTicketsButNotFirstLoad() throws {
        try write("vibe-1.md", content: "---\nid: vibe-1\nrepo: vibe\nbranch: feature-a\n---\n")
        let store = TicketStore(storeURL: storeDirectory)

        var events: [(added: [String], removed: [String])] = []
        store.onChange = { added, removed in
            events.append((added.map(\.ticketID), removed.map(\.ticketID)))
        }

        // First load must NOT fire onChange (the tickets already existed).
        store.reload()
        XCTAssertTrue(events.isEmpty)

        // Adding a ticket reports it as added.
        try write("vibe-2.md", content: "---\nid: vibe-2\nrepo: vibe\nbranch: feature-b\n---\n")
        store.reload()
        XCTAssertEqual(events.count, 1)
        XCTAssertEqual(events.last?.added, ["vibe-2"])
        XCTAssertEqual(events.last?.removed, [])

        // Removing a ticket reports it as removed.
        try FileManager.default.removeItem(at: storeDirectory.appendingPathComponent("vibe-2.md"))
        store.reload()
        XCTAssertEqual(events.count, 2)
        XCTAssertEqual(events.last?.added, [])
        XCTAssertEqual(events.last?.removed, ["vibe-2"])
    }

    @MainActor
    func testReloadDoesNotReportPureContentEdits() throws {
        try write("vibe-1.md", content: "---\nid: vibe-1\nstate: on_hold\n---\nOne.\n")
        let store = TicketStore(storeURL: storeDirectory)

        var fired = false
        store.onChange = { _, _ in fired = true }
        store.reload()  // first load

        // Editing an existing ticket's content is neither an add nor a remove.
        try write("vibe-1.md", content: "---\nid: vibe-1\nstate: on_hold\n---\nTwo.\n")
        store.reload()

        XCTAssertFalse(fired)
    }
}
