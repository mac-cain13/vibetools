//
//  TicketStore.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import Foundation
import OSLog

/// Main-actor model object that loads all tickets from the store directory,
/// watches it with FSEvents (no polling), and publishes the ticket list.
///
/// The store location defaults to `/Volumes/External/Repositories/_vibeboard`
/// (format spec section 1) and can be overridden with the `storePath`
/// `UserDefaults` key — which also covers the `-storePath /some/dir` launch
/// argument via the `NSArgumentDomain`.
@MainActor
public final class TicketStore: ObservableObject {

    /// All tickets currently in the store, sorted by filename.
    @Published public private(set) var tickets: [Ticket] = []

    /// Human-readable description of the most recent failed operation, for the UI.
    @Published public private(set) var lastError: String?

    /// The `_vibeboard` store directory being read and watched.
    public let storeURL: URL

    /// The repo base directory (the store's parent, per format spec section 1).
    public var repoBaseURL: URL { storeURL.deletingLastPathComponent() }

    /// Called after a reload whose ticket set changed (compared by id), with
    /// the tickets `(added, removed)` since the previous load. Not invoked on
    /// the very first load. The app uses this to post park/resume notifications.
    public var onChange: (([Ticket], [Ticket]) -> Void)?

    private let logger = Logger(subsystem: "com.nonstrict.VibeBoard", category: "store")
    private var watcher: FSEventsWatcher?
    private var pendingReload: Task<Void, Never>?
    private var hasLoadedOnce = false

    /// Resolves the store directory: the `storePath` default (set via
    /// `defaults write` or the `-storePath` launch argument) when present,
    /// otherwise the spec section 1 default location.
    ///
    /// - Parameter userDefaults: Defaults database to consult (injectable for tests).
    /// - Returns: The resolved store directory URL.
    nonisolated public static func resolveStoreURL(userDefaults: UserDefaults = .standard) -> URL {
        if let override = userDefaults.string(forKey: "storePath"),
           !override.trimmingCharacters(in: .whitespaces).isEmpty {
            return URL(fileURLWithPath: (override as NSString).expandingTildeInPath, isDirectory: true)
        }
        return URL(fileURLWithPath: "/Volumes/External/Repositories/_vibeboard", isDirectory: true)
    }

    /// Creates a store bound to a directory.
    ///
    /// - Parameter storeURL: Store directory, or `nil` to resolve the default/override.
    public init(storeURL: URL? = nil) {
        self.storeURL = storeURL ?? Self.resolveStoreURL()
    }

    // MARK: - Lifecycle

    /// Loads the tickets and starts the FSEvents watch on the store directory.
    /// Safe to call repeatedly; subsequent calls only trigger a reload.
    public func start() {
        reload()
        guard watcher == nil else { return }
        logger.debug("Starting store watch on \(self.storeURL.path, privacy: .public)")

        do {
            try FileManager.default.createDirectory(at: storeURL, withIntermediateDirectories: true)
        } catch {
            logger.error("Could not create store directory: \((error as NSError).debugDescription, privacy: .public)")
        }

        let newWatcher = FSEventsWatcher(directory: storeURL) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.scheduleReload()
            }
        }
        do {
            try newWatcher.start()
            watcher = newWatcher
            logger.notice("Store watch started on \(self.storeURL.path, privacy: .public)")
        } catch {
            lastError = "Could not watch \(storeURL.path)"
            logger.error("Failed to start FSEvents watch: \((error as NSError).debugDescription, privacy: .public)")
        }
    }

    /// Stops the FSEvents watch and cancels any pending debounced reload.
    public func stop() {
        logger.debug("Stopping store watch")
        pendingReload?.cancel()
        pendingReload = nil
        watcher?.stop()
        watcher = nil
        logger.notice("Store watch stopped")
    }

    /// Debounces bursts of FSEvents into a single reload (~250 ms quiet period).
    private func scheduleReload() {
        pendingReload?.cancel()
        pendingReload = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard !Task.isCancelled else { return }
            self?.reload()
        }
    }

    /// Re-reads every ticket file from the store directory and publishes the
    /// result. After the initial load, diffs the ticket set by id and reports
    /// additions/removals through `onChange` (park = added, resume = removed).
    public func reload() {
        logger.debug("Reloading tickets from \(self.storeURL.path, privacy: .public)")
        let previous = tickets
        let loaded = Self.loadTickets(from: storeURL)
        tickets = loaded
        logger.notice("Loaded \(self.tickets.count) tickets")

        defer { hasLoadedOnce = true }
        guard hasLoadedOnce, let onChange else { return }

        let previousIDs = Set(previous.map(\.id))
        let loadedIDs = Set(loaded.map(\.id))
        let added = loaded.filter { !previousIDs.contains($0.id) }
        let removed = previous.filter { !loadedIDs.contains($0.id) }
        if !added.isEmpty || !removed.isEmpty {
            logger.notice("Ticket set changed: +\(added.count) -\(removed.count)")
            onChange(added, removed)
        }
    }

    /// Reads and parses all ticket files in a directory, ignoring anything
    /// that is not a `*.md` file matching the ticket naming rule (spec section 1).
    ///
    /// - Parameter directory: The store directory.
    /// - Returns: Parsed tickets sorted by filename; unreadable files are skipped.
    nonisolated private static func loadTickets(from directory: URL) -> [Ticket] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: directory.path)) ?? []
        var tickets: [Ticket] = []
        for name in names.sorted() where isTicketFilename(name) {
            let url = directory.appendingPathComponent(name)
            guard let data = try? Data(contentsOf: url) else { continue }
            // Lenient decode: prefer UTF-8, fall back to Latin-1 so a ticket
            // with stray bytes still shows up rather than disappearing.
            let content = String(data: data, encoding: .utf8)
                ?? String(data: data, encoding: .isoLatin1)
                ?? ""
            tickets.append(TicketParser.parse(content: content, fileURL: url))
        }
        return tickets
    }

    /// Checks a file name against the ticket naming rule `<repo>-<n>.md`
    /// (spec section 2). Hidden files, temp files, and non-matching names are
    /// rejected so `.DS_Store`, a README, or writer temp files never parse.
    ///
    /// - Parameter name: A directory entry name.
    /// - Returns: Whether the name is a ticket file name.
    nonisolated public static func isTicketFilename(_ name: String) -> Bool {
        guard name.hasSuffix(".md"), !name.hasPrefix(".") else { return false }
        let stem = name.dropLast(3)
        guard let dash = stem.lastIndex(of: "-") else { return false }
        let repoPart = stem[stem.startIndex..<dash]
        let numberPart = stem[stem.index(after: dash)...]
        return !repoPart.isEmpty
            && !numberPart.isEmpty
            && numberPart.allSatisfy { $0.isASCII && $0.isNumber }
    }

    // MARK: - Mutations

    /// Sets the `title` field of a ticket via the field-preserving writer
    /// (format spec section 4: the title is editable in the app).
    ///
    /// - Parameters:
    ///   - title: The new card title.
    ///   - id: The ticket's identity (`Ticket.id`).
    public func setTitle(_ title: String, forTicketID id: String) {
        updateTicket(id: id, fields: ["title": title])
    }

    /// Outcome of a guarded body save.
    public enum BodySaveOutcome: Sendable {
        /// The body was written.
        case saved
        /// The on-disk body no longer matched the expected snapshot; nothing
        /// was written.
        case conflict
        /// The write failed (unknown ticket or file system error);
        /// `lastError` describes the failure.
        case failed
    }

    /// Replaces a ticket's body (the freeform notes) via the field-preserving
    /// writer; frontmatter is untouched apart from the refreshed `updated`.
    ///
    /// When `expectedBody` is given, the ticket is re-read from disk first and
    /// the save is refused if its body no longer matches — another writer
    /// (e.g. a park writing `## Next step`, spec section 5.5) changed the body
    /// since the snapshot was taken, and overwriting would destroy its content.
    ///
    /// - Parameters:
    ///   - body: The new body text.
    ///   - id: The ticket's identity (`Ticket.id`).
    ///   - expectedBody: The body snapshot the edit was based on, or `nil` to
    ///     save unconditionally.
    /// - Returns: Whether the body was saved, refused on a conflict, or failed.
    @discardableResult
    public func saveBody(_ body: String, forTicketID id: String,
                         ifBodyMatches expectedBody: String? = nil) -> BodySaveOutcome {
        if let expectedBody {
            guard let ticket = tickets.first(where: { $0.id == id }), let url = ticket.fileURL else {
                logger.error("Cannot update unknown ticket \(id, privacy: .public)")
                lastError = "Unknown ticket \(id)"
                return .failed
            }
            // Re-read straight from disk: the published ticket lags behind a
            // concurrent writer (the FSEvents reload is debounced) and the
            // caller's snapshot can be older still.
            if let data = try? Data(contentsOf: url) {
                let content = String(data: data, encoding: .utf8)
                    ?? String(data: data, encoding: .isoLatin1)
                    ?? ""
                let fresh = TicketParser.parse(content: content, fileURL: url)
                guard fresh.body == expectedBody else {
                    logger.notice("Refused body save for \(id, privacy: .public): body changed on disk")
                    reload()
                    return .conflict
                }
            }
        }
        return updateTicket(id: id, fields: [:], body: body) ? .saved : .failed
    }

    /// Clears the published `lastError` (the UI's dismiss action).
    public func clearLastError() {
        lastError = nil
    }

    /// Shared lookup + write + reload for ticket mutations.
    ///
    /// - Parameters:
    ///   - id: The ticket's identity (`Ticket.id`).
    ///   - fields: Frontmatter keys to set.
    ///   - body: Optional replacement body.
    /// - Returns: Whether the write succeeded.
    @discardableResult
    private func updateTicket(id: String, fields: [String: String?], body: String? = nil) -> Bool {
        guard let ticket = tickets.first(where: { $0.id == id }), let url = ticket.fileURL else {
            logger.error("Cannot update unknown ticket \(id, privacy: .public)")
            lastError = "Unknown ticket \(id)"
            return false
        }
        logger.debug("Writing update to ticket \(id, privacy: .public)")
        var succeeded = false
        do {
            try TicketWriter.update(fileAt: url, settingFields: fields, body: body)
            lastError = nil
            succeeded = true
            logger.notice("Wrote update to ticket \(id, privacy: .public)")
        } catch {
            lastError = "Could not update \(id)"
            logger.error("Update failed: \((error as NSError).debugDescription, privacy: .public)")
        }
        reload()
        return succeeded
    }
}
