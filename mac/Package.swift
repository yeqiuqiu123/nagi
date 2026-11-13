// swift-tools-version: 5.9
import PackageDescription

// NagiCore holds the pure, testable rules (links, owner proofs, tray label,
// notification delivery, panel geometry). Nagi is the AppKit menu-bar shell.
// Run the tests with ./test.sh: it adds the Swift Testing paths that a
// Command-Line-Tools-only Mac needs (with Xcode it is plain `swift test`).
let package = Package(
    name: "Nagi",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "Nagi", targets: ["Nagi"])],
    targets: [
        .target(name: "NagiCore"),
        .executableTarget(name: "Nagi", dependencies: ["NagiCore"]),
        .testTarget(name: "NagiCoreTests", dependencies: ["NagiCore"]),
    ]
)
