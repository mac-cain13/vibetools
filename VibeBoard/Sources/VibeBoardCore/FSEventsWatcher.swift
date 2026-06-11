//
//  FSEventsWatcher.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import Foundation
import CoreServices
import OSLog

/// One file-system event delivered by an `FSEventsWatcher`.
public struct FSEvent: Sendable {
    /// Absolute path of the item the event refers to.
    public let path: String
    /// Raw FSEvents flags for the event.
    public let flags: FSEventStreamEventFlags
    /// FSEvents event id.
    public let eventID: FSEventStreamEventId

    /// Creates an event value.
    ///
    /// - Parameters:
    ///   - path: Absolute path of the item.
    ///   - flags: Raw FSEvents flags.
    ///   - eventID: FSEvents event id.
    public init(path: String, flags: FSEventStreamEventFlags, eventID: FSEventStreamEventId) {
        self.path = path
        self.flags = flags
        self.eventID = eventID
    }
}

/// Errors thrown by `FSEventsWatcher`.
public enum FSEventsWatcherError: Error {
    /// `FSEventStreamCreate` returned no stream.
    case streamCreationFailed(path: String)
    /// `FSEventStreamStart` returned false.
    case startFailed(path: String)
}

/// Watches a directory with FSEvents (`FSEventStreamCreate` — true push, no
/// polling) and delivers events to a handler on a private dispatch queue.
///
/// The handler is `@Sendable` because it is invoked from the watcher's queue;
/// hop to the main actor inside the handler when touching UI state.
public final class FSEventsWatcher {

    /// Handler invoked with each batch of events, on the watcher's queue.
    public typealias Handler = @Sendable ([FSEvent]) -> Void

    private static let logger = Logger(subsystem: "com.nonstrict.VibeBoard", category: "fsevents")

    private let directory: URL
    private let latency: TimeInterval
    private let handler: Handler
    private let queue = DispatchQueue(label: "com.nonstrict.VibeBoard.fsevents")
    private var streamRef: FSEventStreamRef?

    /// Creates a watcher for one directory.
    ///
    /// - Parameters:
    ///   - directory: Directory to watch (events cover its contents).
    ///   - latency: FSEvents coalescing latency in seconds.
    ///   - handler: Called with each event batch on a private queue.
    public init(directory: URL, latency: TimeInterval = 0.2, handler: @escaping Handler) {
        self.directory = directory
        self.latency = latency
        self.handler = handler
    }

    deinit {
        stop()
    }

    /// Creates and starts the FSEvents stream.
    ///
    /// - Throws: `FSEventsWatcherError` when the stream cannot be created or started.
    public func start() throws {
        guard streamRef == nil else { return }
        Self.logger.debug("Starting FSEvents stream for \(self.directory.path, privacy: .public)")

        var context = FSEventStreamContext(
            version: 0,
            info: Unmanaged.passUnretained(self).toOpaque(),
            retain: nil,
            release: nil,
            copyDescription: nil
        )
        let flags = FSEventStreamCreateFlags(
            kFSEventStreamCreateFlagUseCFTypes
                | kFSEventStreamCreateFlagFileEvents
                | kFSEventStreamCreateFlagNoDefer
        )
        guard let stream = FSEventStreamCreate(
            kCFAllocatorDefault,
            fsEventsStreamCallback,
            &context,
            [directory.path] as CFArray,
            FSEventStreamEventId(kFSEventStreamEventIdSinceNow),
            latency,
            flags
        ) else {
            throw FSEventsWatcherError.streamCreationFailed(path: directory.path)
        }

        FSEventStreamSetDispatchQueue(stream, queue)
        guard FSEventStreamStart(stream) else {
            FSEventStreamInvalidate(stream)
            FSEventStreamRelease(stream)
            throw FSEventsWatcherError.startFailed(path: directory.path)
        }
        streamRef = stream
        Self.logger.notice("FSEvents stream started for \(self.directory.path, privacy: .public)")
    }

    /// Stops and releases the FSEvents stream; safe to call repeatedly.
    public func stop() {
        guard let stream = streamRef else { return }
        Self.logger.debug("Stopping FSEvents stream for \(self.directory.path, privacy: .public)")
        FSEventStreamStop(stream)
        FSEventStreamInvalidate(stream)
        FSEventStreamRelease(stream)
        streamRef = nil
        Self.logger.notice("FSEvents stream stopped for \(self.directory.path, privacy: .public)")
    }

    /// Forwards a decoded event batch to the handler. Called by the C callback
    /// on the watcher's queue.
    ///
    /// - Parameter events: The decoded events.
    internal func deliver(_ events: [FSEvent]) {
        handler(events)
    }
}

/// C callback trampoline for the FSEvents stream: decodes the CF-typed event
/// arrays and forwards them to the owning `FSEventsWatcher`.
private let fsEventsStreamCallback: FSEventStreamCallback = { _, info, numEvents, eventPaths, eventFlags, eventIDs in
    guard let info else { return }
    let watcher = Unmanaged<FSEventsWatcher>.fromOpaque(info).takeUnretainedValue()
    // With kFSEventStreamCreateFlagUseCFTypes, eventPaths is a CFArray of CFString.
    let paths = Unmanaged<NSArray>.fromOpaque(eventPaths).takeUnretainedValue()
    var events: [FSEvent] = []
    events.reserveCapacity(numEvents)
    for index in 0..<numEvents {
        let path = paths[index] as? String ?? ""
        events.append(FSEvent(path: path, flags: eventFlags[index], eventID: eventIDs[index]))
    }
    watcher.deliver(events)
}
