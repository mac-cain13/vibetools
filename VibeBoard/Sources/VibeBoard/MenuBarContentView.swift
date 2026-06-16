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

    /// Parked tickets grouped by project, projects ordered alphabetically
    /// (case-insensitive), and the tickets within each project ordered by their
    /// last-touched time (`updated`, falling back to `created`) descending so the
    /// most recent work surfaces at the top of its group.
    private var groupedTickets: [(project: String, tickets: [Ticket])] {
        let groups = Dictionary(grouping: store.tickets, by: \.repo)
        return groups
            .map { project, tickets in
                (project: project, tickets: tickets.sorted(by: Self.moreRecent))
            }
            .sorted { $0.project.localizedCaseInsensitiveCompare($1.project) == .orderedAscending }
    }

    /// Orders two tickets most-recent-first by their last-touched time, using
    /// `updated` when present and otherwise `created`, with the ticket id as a
    /// stable tiebreaker.
    private static func moreRecent(_ lhs: Ticket, _ rhs: Ticket) -> Bool {
        let lhsTouched = lhs.updated ?? lhs.created ?? .distantPast
        let rhsTouched = rhs.updated ?? rhs.created ?? .distantPast
        if lhsTouched != rhsTouched { return lhsTouched > rhsTouched }
        return lhs.id < rhs.id
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

    /// Projects whose ticket rows are currently collapsed (hidden). Tapping a
    /// section header toggles membership here.
    @State private var collapsedProjects: Set<String> = []

    /// The ticket list grouped by project, or an empty-state placeholder when
    /// nothing is parked. Each project is introduced by a full-width colored
    /// section header that collapses/expands its tickets when clicked; the
    /// tickets are listed below newest first.
    @ViewBuilder
    private var content: some View {
        let groups = groupedTickets
        if groups.isEmpty {
            Text("No parked work")
                .font(.callout)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.vertical, 28)
        } else {
            ScrollView {
                LazyVStack(spacing: 0, pinnedViews: .sectionHeaders) {
                    ForEach(groups, id: \.project) { group in
                        let isCollapsed = collapsedProjects.contains(group.project)
                        Section {
                            if !isCollapsed {
                                ForEach(group.tickets) { ticket in
                                    MenuBarTicketRow(ticket: ticket) {
                                        openWindow(value: ticket.id)
                                    }
                                    Divider()
                                }
                            }
                        } header: {
                            MenuBarProjectHeader(project: group.project,
                                                 count: group.tickets.count,
                                                 isCollapsed: isCollapsed,
                                                 resumeAllCommand: Self.resumeAllCommand(for: group.tickets),
                                                 onToggle: { toggleCollapsed(group.project) })
                        }
                    }
                }
            }
            .frame(height: Self.listHeight)
        }
    }

    /// The tmux command that opens a `vibe resume` window per ticket in a
    /// project, built in the same order the rows are displayed (newest first).
    private static func resumeAllCommand(for tickets: [Ticket]) -> String {
        ResumeCommand.tmuxResumeAllCommand(for: tickets.map {
            ResumeCommand.TmuxEntry(ticketID: $0.ticketID, worktreePath: $0.worktreePath)
        })
    }

    /// Collapses an expanded project or expands a collapsed one, animating the
    /// rows in/out.
    private func toggleCollapsed(_ project: String) {
        withAnimation(.easeInOut(duration: 0.15)) {
            if collapsedProjects.contains(project) {
                collapsedProjects.remove(project)
            } else {
                collapsedProjects.insert(project)
            }
        }
    }
}

/// A pinned section header introducing a project group: the whole row is filled
/// with the project's color and shows a disclosure chevron, the project name,
/// the number of parked tickets, and a button that copies a tmux command to
/// resume every ticket in the project. Clicking the row (outside the copy
/// button) collapses or expands the project's tickets via `onToggle`.
struct MenuBarProjectHeader: View {

    /// The project / repository name this group represents.
    let project: String

    /// How many parked tickets belong to this project.
    let count: Int

    /// Whether this project's tickets are currently collapsed (hidden).
    let isCollapsed: Bool

    /// The tmux command copied by the project-level copy button: one
    /// `vibe resume` window per ticket.
    let resumeAllCommand: String

    /// Invoked when the header is clicked, to toggle collapsed state.
    let onToggle: () -> Void

    /// Whether the resume-all command was just copied (transient checkmark).
    @State private var copied = false

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "chevron.right")
                .font(.caption2.weight(.bold))
                .rotationEffect(.degrees(isCollapsed ? 0 : 90))
            Text(project)
                .font(.caption.weight(.semibold))
                .lineLimit(1)
            Text("\(count)")
                .font(.caption2)
                .opacity(0.8)
            Spacer()
            copyButton
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.project(project))
        .contentShape(Rectangle())
        .onTapGesture { onToggle() }
        .help(isCollapsed ? "Show \(project) tickets" : "Hide \(project) tickets")
    }

    /// The button that copies the project's tmux resume-all command, flashing a
    /// checkmark briefly. `.plain` so its click is consumed here rather than
    /// falling through to the header's collapse/expand tap gesture.
    private var copyButton: some View {
        Button {
            copyResumeAll()
        } label: {
            Image(systemName: copied ? "checkmark" : "doc.on.clipboard")
                .font(.caption.weight(.semibold))
        }
        .buttonStyle(.plain)
        .help("Copy a tmux command that resumes all \(project) tickets")
    }

    /// Copies the resume-all command to the general pasteboard and flashes the
    /// checkmark for a moment. No terminal is spawned.
    private func copyResumeAll() {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(resumeAllCommand, forType: .string)
        copied = true
        Task {
            try? await Task.sleep(nanoseconds: 1_200_000_000)
            copied = false
        }
    }
}

/// A single ticket row in the menubar list: the title, the ticket id, the
/// branch (when present), and a hover-revealed button that
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
