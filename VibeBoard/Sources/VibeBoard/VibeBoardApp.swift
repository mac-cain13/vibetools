//
//  VibeBoardApp.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import SwiftUI
import AppKit
import OSLog
import VibeBoardCore

/// Application delegate that makes Vibe Board a menubar-only accessory app.
///
/// Setting the activation policy to `.accessory` keeps the process out of the
/// Dock and the app switcher: it lives entirely in the menubar, with floating
/// ticket windows opened on demand.
@MainActor
final class VibeBoardAppDelegate: NSObject, NSApplicationDelegate {

    private let logger = Logger(subsystem: "com.nonstrict.VibeBoard", category: "app")

    /// The shared ticket store. Owned by the delegate (not a SwiftUI
    /// `@StateObject`) so it starts watching — and posting notifications — at
    /// launch rather than when the menubar popover is first opened.
    let store = TicketStore()

    /// Demotes the process to a menubar-only accessory, requests notification
    /// authorization, wires park/resume notifications, and starts the store.
    ///
    /// - Parameter notification: The launch notification (unused).
    func applicationDidFinishLaunching(_ notification: Notification) {
        logger.debug("Setting activation policy to accessory")
        NSApp.setActivationPolicy(.accessory)

        NotificationManager.requestAuthorization()
        store.onChange = { added, removed in
            for ticket in added { NotificationManager.notifyParked(ticket) }
            for ticket in removed { NotificationManager.notifyResumed(ticket) }
        }
        store.start()

        logger.notice("Activation policy set to accessory; store started; running as menubar app")
    }
}

/// The Vibe Board application: a menubar list of parked tickets with a floating
/// window per ticket for reading and commenting.
@main
struct VibeBoardApp: App {

    @NSApplicationDelegateAdaptor(VibeBoardAppDelegate.self) private var appDelegate

    var body: some Scene {
        MenuBarExtra("Vibe Board", systemImage: "tray.full") {
            MenuBarContentView()
                .environmentObject(appDelegate.store)
        }
        .menuBarExtraStyle(.window)

        WindowGroup(for: String.self) { $ticketID in
            TicketWindowView(ticketID: ticketID)
                .environmentObject(appDelegate.store)
        }
        .windowLevel(.floating)
        .windowResizability(.contentSize)
        .defaultSize(width: 520, height: 480)
    }
}
