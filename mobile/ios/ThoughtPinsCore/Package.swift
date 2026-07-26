// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "ThoughtPinsCore",
    platforms: [.iOS(.v17)],
    products: [
        .library(name: "ThoughtPinsCore", targets: ["ThoughtPinsCore"])
    ],
    targets: [
        .target(name: "ThoughtPinsCore"),
        .testTarget(name: "ThoughtPinsCoreTests", dependencies: ["ThoughtPinsCore"])
    ]
)
