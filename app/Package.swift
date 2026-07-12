// swift-tools-version: 6.2

import PackageDescription

let package = Package(
    name: "BillieFlow",
    platforms: [.macOS(.v26)],
    products: [
        .library(name: "BillieFlowCore", targets: ["BillieFlowCore"]),
        .executable(name: "BillieFlow", targets: ["BillieFlowApp"]),
    ],
    targets: [
        .target(name: "BillieFlowCore"),
        .executableTarget(
            name: "BillieFlowApp",
            dependencies: ["BillieFlowCore"],
            resources: [.process("Resources")]
        ),
        .testTarget(
            name: "BillieFlowCoreTests",
            dependencies: ["BillieFlowCore"],
            resources: [.copy("Fixtures")]
        ),
    ],
    swiftLanguageModes: [.v6]
)
