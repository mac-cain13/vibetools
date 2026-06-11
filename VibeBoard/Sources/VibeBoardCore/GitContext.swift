//
//  GitContext.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import Foundation
import OSLog

/// Git facts shown beside a ticket as context. Display only — git facts never
/// change a ticket's `state` (format spec section 10).
public struct GitContext: Hashable, Sendable {
    /// Whether the worktree has uncommitted changes (`git status --porcelain` non-empty).
    public let hasUncommittedChanges: Bool

    /// Commits ahead of upstream, or `nil` when there is no upstream or the
    /// count could not be determined.
    public let commitsAhead: Int?

    /// Creates a context value.
    ///
    /// - Parameters:
    ///   - hasUncommittedChanges: Whether the worktree is dirty.
    ///   - commitsAhead: Commits ahead of upstream, when known.
    public init(hasUncommittedChanges: Bool, commitsAhead: Int?) {
        self.hasUncommittedChanges = hasUncommittedChanges
        self.commitsAhead = commitsAhead
    }

    /// One-line summary for the card's git context line, or `nil` when there
    /// is nothing noteworthy to show.
    public var summaryLine: String? {
        var parts: [String] = []
        if hasUncommittedChanges { parts.append("uncommitted changes") }
        if let ahead = commitsAhead, ahead > 0 {
            parts.append(ahead == 1 ? "1 commit ahead" : "\(ahead) commits ahead")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

/// Loads git context for a ticket's worktree by shelling out to `git`,
/// asynchronously and off the main actor.
public enum GitContextLoader {

    private static let logger = Logger(subsystem: "com.nonstrict.VibeBoard", category: "git")

    /// Loads git context for a worktree path.
    ///
    /// Runs `git status --porcelain` (dirty check) and
    /// `git rev-list --count @{upstream}..HEAD` (commits ahead; failure is
    /// tolerated — e.g. no upstream configured).
    ///
    /// - Parameter worktreePath: Absolute path of the worktree.
    /// - Returns: The context, or `nil` when the path does not exist or the
    ///   status command fails (not a git checkout, etc.).
    public static func load(worktreePath: String) async -> GitContext? {
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: worktreePath, isDirectory: &isDirectory),
              isDirectory.boolValue else {
            return nil
        }

        logger.debug("Loading git context for \(worktreePath, privacy: .public)")

        guard let status = await runGit(["status", "--porcelain"], in: worktreePath),
              status.exitCode == 0 else {
            return nil
        }
        let isDirty = !status.standardOutput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty

        var commitsAhead: Int?
        if let revList = await runGit(["rev-list", "--count", "@{upstream}..HEAD"], in: worktreePath),
           revList.exitCode == 0 {
            commitsAhead = Int(revList.standardOutput.trimmingCharacters(in: .whitespacesAndNewlines))
        }

        logger.notice("Loaded git context for \(worktreePath, privacy: .public)")
        return GitContext(hasUncommittedChanges: isDirty, commitsAhead: commitsAhead)
    }

    /// Runs a git command and captures its standard output, off the main actor.
    ///
    /// Arguments are passed directly to the process (no shell), so no shell
    /// escaping is needed.
    ///
    /// - Parameters:
    ///   - arguments: Git subcommand and flags (without the leading `git`).
    ///   - directory: Worktree to operate on (passed via `git -C`).
    /// - Returns: Exit code and captured stdout, or `nil` when git failed to launch.
    private static func runGit(_ arguments: [String], in directory: String) async -> (exitCode: Int32, standardOutput: String)? {
        return await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .utility).async {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
                process.arguments = ["-C", directory] + arguments
                let stdout = Pipe()
                process.standardOutput = stdout
                // Discard stderr instead of capturing it: an unread Pipe can
                // fill its ~64KB buffer on a chatty git, blocking the child and
                // deadlocking the stdout read below.
                process.standardError = FileHandle.nullDevice
                do {
                    try process.run()
                } catch {
                    logger.error("git failed to launch: \((error as NSError).debugDescription, privacy: .public)")
                    continuation.resume(returning: nil)
                    return
                }
                let data = stdout.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                let output = String(data: data, encoding: .utf8) ?? ""
                continuation.resume(returning: (process.terminationStatus, output))
            }
        }
    }
}
