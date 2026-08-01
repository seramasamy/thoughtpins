// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "ThoughtPinsCore",
    // The app ships for iOS, but `swift test` on a Mac builds for macOS, which
    // falls back to a deployment target so old that async/await and Task are
    // unavailable. Naming macOS here keeps the package testable on CI without
    // changing what the app itself targets.
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "ThoughtPinsCore", targets: ["ThoughtPinsCore"])
    ],
    targets: [
        .target(name: "ThoughtPinsCore"),
        .testTarget(name: "ThoughtPinsCoreTests", dependencies: ["ThoughtPinsCore"])
    ]
)
