// swift-tools-version: 5.10
//
//  Package.swift
//  VibeBoard
//
//  Created by Claude on 2026-06-10.
//

import PackageDescription

let package = Package(
    name: "VibeBoard",
    platforms: [
        .macOS("26.0"),
    ],
    products: [
        .library(name: "VibeBoardCore", targets: ["VibeBoardCore"]),
        .executable(name: "VibeBoard", targets: ["VibeBoard"]),
        .executable(name: "FSEventsSpike", targets: ["FSEventsSpike"]),
    ],
    targets: [
        .target(name: "VibeBoardCore"),
        .executableTarget(name: "VibeBoard", dependencies: ["VibeBoardCore"]),
        .executableTarget(name: "FSEventsSpike", dependencies: ["VibeBoardCore"]),
        .testTarget(name: "VibeBoardCoreTests", dependencies: ["VibeBoardCore"]),
    ]
)
