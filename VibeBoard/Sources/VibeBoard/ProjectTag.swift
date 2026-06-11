//
//  ProjectTag.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-11.
//

import SwiftUI
import VibeBoardCore

/// A small colored capsule showing which project (repository) a ticket belongs
/// to, so parked work is easy to spot at a glance. The color is derived
/// deterministically from the project name (see `ProjectColor`).
struct ProjectTag: View {

    /// The project / repository name to display.
    let project: String

    var body: some View {
        Text(project)
            .font(.caption2.weight(.semibold))
            .lineLimit(1)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(Capsule().fill(tagColor))
            .foregroundStyle(.white)
    }

    /// A vivid, stable color for this project, readable against white text.
    private var tagColor: Color {
        Color(hue: ProjectColor.hue(for: project), saturation: 0.58, brightness: 0.80)
    }
}
