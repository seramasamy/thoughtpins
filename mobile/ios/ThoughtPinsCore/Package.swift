// swift-tools-version: 5.9
//
// 5.9, not 5.10, and the difference is not cosmetic. A manifest declaring 5.10
// cannot be *parsed* by a 5.9 toolchain — it fails with "using Swift tools
// version 5.10.0 but the installed version is 5.9.x" before compiling a line.
// Xcode 15.2 is the newest Xcode macOS 13 Ventura can install, and it ships
// Swift 5.9, so 5.10 locked this package out of the only machine available to
// build it. Nothing in the manifest below needs 5.10: .iOS(.v17) and
// .macOS(.v14) both landed in 5.9. Newer toolchains build older tools versions
// happily, so this is strictly more portable, not a downgrade.

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
