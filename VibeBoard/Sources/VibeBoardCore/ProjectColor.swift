//
//  ProjectColor.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import Foundation

/// Maps a project (repository) name to a stable hue, so each project gets a
/// consistent tag color across launches and machines.
///
/// The hue is derived from a deterministic FNV-1a hash of the name's UTF-8
/// bytes — Swift's built-in `Hasher` is randomized per process and would give
/// a different color every launch, so it must not be used here. The view layer
/// turns the hue into a `Color`; this stays Foundation-only and unit-testable.
public enum ProjectColor {

    /// A stable hue in the range `0..<1` for a project name.
    ///
    /// - Parameter project: The repository / project name (e.g. `Bezel`).
    /// - Returns: A deterministic hue; the same name always yields the same value.
    public static func hue(for project: String) -> Double {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325 // FNV-1a 64-bit offset basis
        let prime: UInt64 = 0x0000_0100_0000_01b3
        for byte in project.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* prime
        }
        // Map the low 16 bits onto [0, 1) — plenty of spread for distinct hues.
        return Double(hash & 0xffff) / Double(0x1_0000)
    }
}
