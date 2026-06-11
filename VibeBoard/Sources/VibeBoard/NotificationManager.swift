//
//  NotificationManager.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-11.
//

import Foundation
import OSLog
import UserNotifications
import VibeBoardCore

/// Posts local notifications when work is parked (a ticket appears) or resumed
/// (a ticket is deleted).
///
/// `UNUserNotificationCenter` requires the process to run inside a bundle with a
/// `CFBundleIdentifier` — a bare `swift run` executable has none and trapping
/// there would crash. Every entry point is gated on `isAvailable`, so the same
/// binary runs fine for development (notifications simply no-op) and delivers
/// notifications when launched from the signed `.app` bundle.
enum NotificationManager {

    private static let logger = Logger(subsystem: "com.nonstrict.VibeBoard", category: "notifications")

    /// Whether local notifications can be used (true only inside an app bundle).
    private static var isAvailable: Bool { Bundle.main.bundleIdentifier != nil }

    /// Requests notification authorization once at launch. No-ops (with a log
    /// line) when run outside an app bundle.
    static func requestAuthorization() {
        guard isAvailable else {
            logger.notice("Notifications unavailable: no bundle id (run the VibeBoard.app bundle)")
            return
        }
        logger.debug("Requesting notification authorization")
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, error in
            if let error {
                logger.error("Notification authorization failed: \((error as NSError).debugDescription, privacy: .public)")
            } else {
                logger.notice("Notification authorization granted=\(granted)")
            }
        }
    }

    /// Notifies that a piece of work was parked.
    ///
    /// - Parameter ticket: The newly created (parked) ticket.
    static func notifyParked(_ ticket: Ticket) {
        post(prefix: "Parked", ticket: ticket)
    }

    /// Notifies that a piece of work was resumed (its ticket was deleted).
    ///
    /// - Parameter ticket: The ticket that was removed from the store.
    static func notifyResumed(_ ticket: Ticket) {
        post(prefix: "Resumed", ticket: ticket)
    }

    /// Builds and delivers a notification describing a parked/resumed ticket:
    /// title `<action> <project>`, the branch as subtitle, the work title as body.
    ///
    /// - Parameters:
    ///   - prefix: The action word for the title (e.g. `Parked`).
    ///   - ticket: The ticket the notification is about.
    private static func post(prefix: String, ticket: Ticket) {
        guard isAvailable else { return }
        logger.debug("Posting \(prefix, privacy: .public) notification for \(ticket.ticketID, privacy: .public)")

        let content = UNMutableNotificationContent()
        content.title = "\(prefix) \(ticket.repo)"
        if let branch = ticket.branch, !branch.isEmpty { content.subtitle = branch }
        content.body = ticket.title
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: UUID().uuidString, content: content, trigger: nil
        )
        UNUserNotificationCenter.current().add(request) { error in
            if let error {
                logger.error("Failed to post notification: \((error as NSError).debugDescription, privacy: .public)")
            } else {
                logger.notice("Posted \(prefix, privacy: .public) notification for \(ticket.ticketID, privacy: .public)")
            }
        }
    }
}
