//
//  ProjectColorTests.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import XCTest
@testable import VibeBoardCore

/// Tests that project tag colors are stable and well-distributed.
final class ProjectColorTests: XCTestCase {

    /// The same project name must always map to the same hue (no per-process
    /// randomness — that is the whole point of the tag color).
    func testHueIsDeterministic() {
        XCTAssertEqual(ProjectColor.hue(for: "Bezel"), ProjectColor.hue(for: "Bezel"))
        XCTAssertEqual(ProjectColor.hue(for: "vibe"), ProjectColor.hue(for: "vibe"))
    }

    /// Hue is always a valid `0..<1` value for `Color(hue:saturation:brightness:)`.
    func testHueInUnitRange() {
        for name in ["Bezel", "vibe", "", "a-very-long-project-name", "X"] {
            let hue = ProjectColor.hue(for: name)
            XCTAssertGreaterThanOrEqual(hue, 0.0)
            XCTAssertLessThan(hue, 1.0)
        }
    }

    /// Distinct project names should generally get distinct hues.
    func testDistinctProjectsDifferInHue() {
        XCTAssertNotEqual(ProjectColor.hue(for: "Bezel"), ProjectColor.hue(for: "vibe"))
    }
}
