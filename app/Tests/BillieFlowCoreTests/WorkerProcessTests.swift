import Foundation
import Testing
@testable import BillieFlowCore

@Suite("Persistent worker process")
struct WorkerProcessTests {
    @Test func fakeWorkerHelloWarmupProcessShutdown() async throws {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: TestBundleMarker.self)
        #endif
        let fixture = try #require(bundle.url(
            forResource: "fake_worker", withExtension: "py", subdirectory: "Fixtures"
        ) ?? bundle.url(forResource: "fake_worker", withExtension: "py"))
        let worker = WorkerProcess(configuration: WorkerLaunchConfiguration(
            executableURL: URL(fileURLWithPath: "/usr/bin/python3"), arguments: [fixture.path]
        ))
        let phases = PhaseCollector()
        try await worker.warmup { phase in phases.append(phase) }

        let audio = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID()).wav")
        try Data("fake wave".utf8).write(to: audio)
        defer { try? FileManager.default.removeItem(at: audio) }
        let result = try await worker.process(audioURL: audio, style: .message, debug: false) {
            phase in phases.append(phase)
        }
        #expect(result.finalText == "Billie Flow fake result.")
        #expect(result.style == .message)
        #expect(phases.values == [.loadingASR, .loadingCleanup, .transcribing, .cleaning, .correcting])
        await worker.shutdown()
    }
}

private final class TestBundleMarker {}

private final class PhaseCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [WorkerPhase] = []
    var values: [WorkerPhase] { lock.withLock { storage } }
    func append(_ phase: WorkerPhase) { lock.withLock { storage.append(phase) } }
}
