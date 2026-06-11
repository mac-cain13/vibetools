//
//  main.swift
//  VibeBoard (FSEventsSpike)
//
//  Created by Claude on 2026-06-10.
//

import Foundation
import CoreServices
import VibeBoardCore

/// Renders FSEvents flags as human-readable names plus the raw hex value.
///
/// - Parameter flags: Raw FSEvents flags for one event.
/// - Returns: Comma-separated flag names with the hex value, e.g.
///   `created,file (0x00000100)`.
func describeFlags(_ flags: FSEventStreamEventFlags) -> String {
    let knownFlags: [(Int, String)] = [
        (kFSEventStreamEventFlagItemCreated, "created"),
        (kFSEventStreamEventFlagItemRemoved, "removed"),
        (kFSEventStreamEventFlagItemRenamed, "renamed"),
        (kFSEventStreamEventFlagItemModified, "modified"),
        (kFSEventStreamEventFlagItemInodeMetaMod, "inode-meta"),
        (kFSEventStreamEventFlagItemFinderInfoMod, "finder-info"),
        (kFSEventStreamEventFlagItemChangeOwner, "chown"),
        (kFSEventStreamEventFlagItemXattrMod, "xattr"),
        (kFSEventStreamEventFlagItemCloned, "cloned"),
        (kFSEventStreamEventFlagItemIsFile, "file"),
        (kFSEventStreamEventFlagItemIsDir, "dir"),
        (kFSEventStreamEventFlagItemIsSymlink, "symlink"),
        (kFSEventStreamEventFlagMustScanSubDirs, "must-scan-subdirs"),
        (kFSEventStreamEventFlagEventIdsWrapped, "ids-wrapped"),
        (kFSEventStreamEventFlagHistoryDone, "history-done"),
        (kFSEventStreamEventFlagRootChanged, "root-changed"),
        (kFSEventStreamEventFlagMount, "mount"),
        (kFSEventStreamEventFlagUnmount, "unmount"),
    ]
    let names = knownFlags
        .filter { flags & FSEventStreamEventFlags($0.0) != 0 }
        .map { $0.1 }
    let hex = String(format: "0x%08x", flags)
    return names.isEmpty ? hex : "\(names.joined(separator: ",")) (\(hex))"
}

/// Formats the current moment with fractional seconds for event lines.
///
/// - Returns: An ISO 8601 timestamp like `2026-06-10T14:30:00.123Z`.
func eventTimestamp() -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: Date())
}

// Line-buffer stdout so event lines appear immediately even when piped to a
// file or `tee` (the default block buffering would hold them back).
setvbuf(stdout, nil, _IOLBF, 0)

let arguments = CommandLine.arguments
guard arguments.count == 2 else {
    FileHandle.standardError.write(Data("usage: FSEventsSpike <directory-to-watch>\n".utf8))
    exit(64)
}

let directory = URL(fileURLWithPath: arguments[1], isDirectory: true)
guard FileManager.default.fileExists(atPath: directory.path) else {
    FileHandle.standardError.write(Data("error: \(directory.path) does not exist\n".utf8))
    exit(66)
}

let watcher = FSEventsWatcher(directory: directory, latency: 0.1) { events in
    for event in events {
        print("\(eventTimestamp())\t\(event.path)\t\(describeFlags(event.flags))\tid=\(event.eventID)")
    }
}

do {
    try watcher.start()
} catch {
    FileHandle.standardError.write(
        Data("error: failed to start FSEvents stream: \((error as NSError).debugDescription)\n".utf8)
    )
    exit(1)
}

print("Watching \(directory.path) with FSEvents — one line per event (timestamp, path, flags). Ctrl-C to stop.")
dispatchMain()
