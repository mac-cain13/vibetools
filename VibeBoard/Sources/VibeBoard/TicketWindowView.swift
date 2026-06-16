//
//  TicketWindowView.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-11.
//

import SwiftUI
import AppKit
import VibeBoardCore

/// The content of the floating ticket window: resolves the ticket from the
/// store by id and hosts the read/comment editor, or a small placeholder when
/// the ticket no longer exists (it was resumed away or deleted). The hosting
/// `WindowGroup` applies `.windowLevel(.floating)`.
struct TicketWindowView: View {

    @EnvironmentObject private var store: TicketStore

    /// The ticket id this window is keyed by, or `nil` when the scene opened
    /// without a value.
    let ticketID: String?

    var body: some View {
        Group {
            if let ticket = resolvedTicket {
                TicketEditorView(ticket: ticket)
            } else {
                missingState
            }
        }
        .frame(minWidth: 520, minHeight: 480)
    }

    /// The current ticket for this window's id, freshly resolved from the store
    /// so it tracks on-disk reloads.
    private var resolvedTicket: Ticket? {
        guard let ticketID else { return nil }
        return store.tickets.first { $0.id == ticketID }
    }

    /// Placeholder shown when the ticket id no longer resolves to a ticket.
    private var missingState: some View {
        VStack(spacing: 8) {
            Image(systemName: "tray")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("This ticket no longer exists.")
                .font(.headline)
            Text("It may have been resumed or removed from the store.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// The editor body for a resolved ticket: the colored project tag, an editable
/// title, the ticket id and branch, a git context line (info only), the body
/// rendered as Markdown, and an editable comment area that saves through the
/// conflict-guarded body writer. The window title is the ticket title; a button
/// copies the `vibe resume <id>` command.
struct TicketEditorView: View {

    @EnvironmentObject private var store: TicketStore

    /// The current ticket snapshot from the store.
    let ticket: Ticket

    @State private var titleText: String
    @State private var bodyText: String
    @State private var editingNotes = false
    @State private var copiedToClipboard = false

    /// The title as last persisted, so only real edits are written back.
    @State private var savedTitle: String

    /// The body the comment editor is based on (window-open snapshot, refreshed
    /// after each successful save). Saving compares this against the on-disk
    /// body so a concurrent writer's content is never silently overwritten.
    @State private var savedBodySnapshot: String

    /// Whether the "ticket changed on disk" conflict alert is showing.
    @State private var showBodyConflict = false

    /// Lazily loaded git context for the ticket's worktree, when one exists.
    @State private var gitContext: GitContext?

    /// Creates the editor, seeding the editable state from the ticket.
    ///
    /// - Parameter ticket: The ticket to show and edit.
    init(ticket: Ticket) {
        self.ticket = ticket
        _titleText = State(initialValue: ticket.title)
        _savedTitle = State(initialValue: ticket.title)
        _bodyText = State(initialValue: ticket.body)
        _savedBodySnapshot = State(initialValue: ticket.body)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            bodyArea
            footer
        }
        .padding(16)
        .navigationTitle(savedTitle)
        .task(id: ticket.worktreePath) { await loadGitContext() }
        .alert("Ticket changed on disk", isPresented: $showBodyConflict) {
            Button("Overwrite", role: .destructive) {
                if store.saveBody(bodyText, forTicketID: ticket.id) == .saved {
                    savedBodySnapshot = bodyText
                    editingNotes = false
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("""
            The notes were changed by another writer (for example a park \
            updating "## Next step") while you were editing. Saving now would \
            replace those changes with your version.
            """)
        }
    }

    /// Editable title, project tag, id, branch, and the git context line.
    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                TextField("Title", text: $titleText)
                    .textFieldStyle(.plain)
                    .font(.title2.weight(.semibold))
                    .onSubmit { commitTitle() }
                Spacer()
                ProjectTag(project: ticket.repo)
            }
            HStack(spacing: 12) {
                Text(ticket.ticketID)
                    .font(.callout.monospaced())
                    .foregroundStyle(.secondary)
                if let branch = ticket.branch {
                    Label(branch, systemImage: "arrow.triangle.branch")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
            if let contextLine = gitContext?.summaryLine {
                Label(contextLine, systemImage: "info.circle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
    }

    /// The body area: in read mode, the park-owned Braindump and Next step
    /// sections as distinct cards plus the freeform notes; in edit mode, the
    /// whole raw Markdown body in a plain-text editor. The Edit toggle swaps
    /// between them.
    private var bodyArea: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(editingNotes ? "Edit body" : "Details")
                    .font(.headline)
                Spacer()
                Toggle("Edit", isOn: $editingNotes)
                    .toggleStyle(.switch)
                    .controlSize(.small)
            }
            if editingNotes {
                TextEditor(text: $bodyText)
                    .font(.body.monospaced())
                    .frame(minHeight: 220)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.3))
                    )
            } else {
                readModeSections
            }
        }
        .frame(maxHeight: .infinity)
    }

    /// Read-mode body: the human braindump and agent next-step cards (each shown
    /// only when present), followed by the freeform notes. Falls back to a
    /// placeholder when the ticket has no body content at all.
    private var readModeSections: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let braindump = ticket.braindump {
                    TicketSectionCard(title: "Braindump", attribution: "you",
                                      systemImage: "person.fill", accent: .blue,
                                      content: Self.renderMarkdown(braindump))
                }
                if let nextStep = ticket.nextStep {
                    TicketSectionCard(title: "Next step", attribution: "AI",
                                      systemImage: "sparkles", accent: .purple,
                                      content: Self.renderMarkdown(nextStep))
                }
                let notes = ticket.freeformNotes
                if notes != nil || ticket.braindump == nil && ticket.nextStep == nil {
                    TicketSectionCard(title: "Notes", attribution: nil,
                                      systemImage: "note.text", accent: .secondary,
                                      content: Self.renderMarkdown(notes ?? "No notes yet."))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.bottom, 4)
        }
        .frame(minHeight: 220)
    }

    /// The action row: copy resume command, and save-notes when editing.
    private var footer: some View {
        HStack {
            Button {
                copyResumeCommand()
            } label: {
                Label("Copy resume command", systemImage: "doc.on.clipboard")
            }
            if copiedToClipboard {
                Text("Copied")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if editingNotes {
                Button("Save notes") { saveNotes() }
                    .keyboardShortcut("s", modifiers: .command)
                    .disabled(bodyText == savedBodySnapshot)
            }
        }
    }

    /// Renders Markdown text to an `AttributedString`, falling back to plain
    /// text when it cannot be parsed.
    ///
    /// - Parameter text: The Markdown source.
    /// - Returns: The rendered attributed string.
    static func renderMarkdown(_ text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
        return (try? AttributedString(markdown: text, options: options)) ?? AttributedString(text)
    }

    /// Loads git context for the ticket's worktree off the main actor and
    /// publishes it. Cleared first so a moved/edited ticket never shows stale
    /// context.
    private func loadGitContext() async {
        gitContext = nil
        guard let worktree = ticket.worktreePath else { return }
        gitContext = await GitContextLoader.load(worktreePath: worktree)
    }

    /// Saves the edited notes, guarded against a concurrent body change: the
    /// store refuses the write when the on-disk body no longer matches the
    /// snapshot this edit started from, and a conflict alert is shown instead
    /// of silently overwriting another writer's content.
    private func saveNotes() {
        switch store.saveBody(bodyText, forTicketID: ticket.id, ifBodyMatches: savedBodySnapshot) {
        case .saved:
            savedBodySnapshot = bodyText
            editingNotes = false
        case .conflict:
            showBodyConflict = true
        case .failed:
            break // store.lastError records the failure.
        }
    }

    /// Writes the edited title back to the ticket when it actually changed.
    /// Empty titles are rejected and the field reverts to the saved value.
    private func commitTitle() {
        let trimmed = titleText.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else {
            titleText = savedTitle
            return
        }
        guard trimmed != savedTitle else { return }
        store.setTitle(trimmed, forTicketID: ticket.id)
        savedTitle = trimmed
        titleText = trimmed
    }

    /// Puts `vibe resume <id>` on the general pasteboard. No terminal is
    /// spawned — pasting into iTerm is the user's move.
    private func copyResumeCommand() {
        let command = ResumeCommand.command(forTicketID: ticket.ticketID)
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(command, forType: .string)
        copiedToClipboard = true
    }
}

/// A titled card for one part of a ticket's body — the human braindump, the
/// agent's next step, or the freeform notes. Shows an icon, a title, an optional
/// "you"/"AI" attribution tag, and the rendered Markdown content, framed so the
/// two park-owned sections read as distinct blocks.
struct TicketSectionCard: View {

    /// The card's title (e.g. "Braindump", "Next step", "Notes").
    let title: String

    /// Who authored this section ("you" / "AI"), or `nil` to omit the tag.
    let attribution: String?

    /// SF Symbol shown beside the title.
    let systemImage: String

    /// Accent color for the icon, title, and attribution tag.
    let accent: Color

    /// The rendered Markdown body of the section.
    let content: AttributedString

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Label(title, systemImage: systemImage)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(accent)
                if let attribution {
                    Text(attribution)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(accent)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .background(Capsule().fill(accent.opacity(0.15)))
                }
                Spacer()
            }
            Text(content)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(nsColor: .textBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(accent.opacity(0.25))
        )
    }
}
