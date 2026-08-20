// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ThoughtPinsApp",
    platforms: [.iOS(.v17)],
    products: [
        .library(name: "ThoughtPinsApp", targets: ["ThoughtPinsApp"])
    ],
    dependencies: [
        .package(path: "../ThoughtPinsCore")
    ],
    targets: [
        .target(
            name: "ThoughtPinsApp",
            dependencies: ["ThoughtPinsCore"]
        )
    ]
)
