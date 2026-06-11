//
//  MenuBarContentView.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-11.
//

import AppKit
import SwiftUI
import VibeBoardCore

/// The menubar popover content: a compact list of all parked tickets, newest
/// first, with a per-row "copy resume command" action. Clicking a row opens
/// that ticket's floating window. A header shows the count and a Quit button.
struct MenuBarContentView: View {

    @EnvironmentObject private var store: TicketStore
    @Environment(\.openWindow) private var openWindow

    /// Roughly how tall one ticket row renders (project tag + title + id/branch
    /// line + padding + divider). Used to size the list to a target row count.
    private static let estimatedRowHeight: CGFloat = 68

    /// How many rows tall the list is (shorter lists leave space, longer ones
    /// scroll). A definite height is required: `MenuBarExtra(.window)` sizes the
    /// popover to fit its content, so a `maxHeight` alone collapses to the
    /// content height and is effectively ignored.
    private static let visibleRowCount = 8

    /// The list's fixed height — `visibleRowCount` rows tall.
    private static var listHeight: CGFloat {
        estimatedRowHeight * CGFloat(visibleRowCount)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            content
        }
        .frame(width: 340)
    }

    /// Parked tickets sorted by `updated` descending, then id, so the most
    /// recently touched work surfaces first.
    private var sortedTickets: [Ticket] {
        store.tickets.sorted { lhs, rhs in
            let lhsUpdated = lhs.updated ?? .distantPast
            let rhsUpdated = rhs.updated ?? .distantPast
            if lhsUpdated != rhsUpdated { return lhsUpdated > rhsUpdated }
            return lhs.id < rhs.id
        }
    }

    /// The title bar: the parked count on the left, a Quit button on the right.
    private var header: some View {
        HStack {
            Text("Parked")
                .font(.headline)
            Spacer()
            Text("\(store.tickets.count)")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button {
                NSApplication.shared.terminate(nil)
            } label: {
                Image(systemName: "power")
            }
            .buttonStyle(.plain)
            .help("Quit Vibe Board")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    /// The ticket list, or an empty-state placeholder when nothing is parked.
    @ViewBuilder
    private var content: some View {
        if sortedTickets.isEmpty {
            Text("No parked work")
                .font(.callout)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.vertical, 28)
        } else {
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(sortedTickets) { ticket in
                        MenuBarTicketRow(ticket: ticket) {
                            openWindow(value: ticket.id)
                        }
                        Divider()
                    }
                }
            }
            .frame(height: Self.listHeight)
        }
    }
}

/// A single ticket row in the menubar list: the colored project tag, the title,
/// the ticket id, the branch (when present), and a hover-revealed button that
/// copies `vibe resume <id>` to the clipboard. Clicking the row opens the
/// ticket's floating window via the `onOpen` action.
struct MenuBarTicketRow: View {

    /// The ticket this row represents.
    let ticket: Ticket

    /// Invoked when the row body is clicked (opens the ticket window).
    let onOpen: () -> Void

    /// Whether the pointer is over the row (drives the copy button).
    @State private var isHovered = false

    /// Whether the resume command was just copied (transient checkmark).
    @State private var copied = false

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 3) {
                ProjectTag(project: ticket.repo)
                Text(ticket.title)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 8) {
                    Text(ticket.ticketID)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.tertiary)
                    if let branch = ticket.branch {
                        Label(branch, systemImage: "arrow.triangle.branch")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
            }
            copyButton
                .opacity(isHovered ? 1 : 0)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(isHovered ? Color.primary.opacity(0.06) : Color.clear)
        .contentShape(Rectangle())
        .onTapGesture { onOpen() }
        .onHover { hovering in
            isHovered = hovering
            if !hovering { copied = false }
        }
        .animation(.easeInOut(duration: 0.12), value: isHovered)
    }

    /// The button that copies `vibe resume <id>` to the clipboard, flashing a
    /// checkmark for a moment. `.plain` so the click hits the button rather
    /// than the row's open gesture.
    private var copyButton: some View {
        Button {
            copyResumeCommand()
        } label: {
            Image(systemName: copied ? "checkmark" : "doc.on.clipboard")
                .font(.caption.weight(.semibold))
                .foregroundStyle(copied ? Color.green : Color.secondary)
        }
        .buttonStyle(.plain)
        .help("Copy “vibe resume \(ticket.ticketID)”")
    }

    /// Copies the resume command to the general pasteboard and flashes the
    /// checkmark briefly. No terminal is spawned.
    private func copyResumeCommand() {
        let command = ResumeCommand.command(forTicketID: ticket.ticketID)
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(command, forType: .string)
        copied = true
        Task {
            try? await Task.sleep(nanoseconds: 1_200_000_000)
            if isHovered { copied = false }
        }
    }
}
