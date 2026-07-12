import Darwin
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

    @Test func cancellationKillsWorkerAndNextRequestStartsFreshProcess() async throws {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: TestBundleMarker.self)
        #endif
        let fixture = try #require(bundle.url(
            forResource: "fake_worker", withExtension: "py", subdirectory: "Fixtures"
        ) ?? bundle.url(forResource: "fake_worker", withExtension: "py"))
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("BillieFlowWorkerTest-\(UUID())", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let pidFile = directory.appendingPathComponent("pids.txt")
        let delayMarker = directory.appendingPathComponent("delay-once")
        let audio = directory.appendingPathComponent("audio.wav")
        try Data("fake wave".utf8).write(to: audio)

        let worker = WorkerProcess(configuration: WorkerLaunchConfiguration(
            executableURL: URL(fileURLWithPath: "/usr/bin/python3"),
            arguments: [fixture.path],
            environment: [
                "BILLIE_FLOW_FAKE_PID_FILE": pidFile.path,
                "BILLIE_FLOW_FAKE_DELAY_ONCE_FILE": delayMarker.path,
                "BILLIE_FLOW_FAKE_PROCESS_DELAY": "30",
            ]
        ))
        let phases = PhaseCollector()
        let firstRequest = Task {
            try await worker.process(audioURL: audio, style: .lightCleanup, debug: false) {
                phase in phases.append(phase)
            }
        }
        try await waitUntil { phases.values.contains(.transcribing) }
        let firstPID = try #require(readPIDs(from: pidFile).first)

        await worker.cancel()
        do {
            _ = try await firstRequest.value
            Issue.record("Cancelled worker request unexpectedly completed.")
        } catch is CancellationError {
            // WorkerProcess resumes all pending requests with cancellation.
        }
        #expect(!processExists(firstPID))

        let result = try await worker.process(audioURL: audio, style: .message, debug: false)
        #expect(result.finalText == "Billie Flow fake result.")
        let restartedPIDs = readPIDs(from: pidFile)
        #expect(restartedPIDs.count == 2)
        #expect(restartedPIDs.first != restartedPIDs.last)
        let secondPID = try #require(restartedPIDs.last)
        #expect(processExists(secondPID))

        await worker.shutdown()
        #expect(!processExists(secondPID))
    }
}

private final class TestBundleMarker {}

private final class PhaseCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [WorkerPhase] = []
    var values: [WorkerPhase] { lock.withLock { storage } }
    func append(_ phase: WorkerPhase) { lock.withLock { storage.append(phase) } }
}

private enum WaitError: Error { case timedOut }

private func waitUntil(
    timeout: Duration = .seconds(5),
    condition: @escaping @Sendable () -> Bool
) async throws {
    let clock = ContinuousClock()
    let deadline = clock.now.advanced(by: timeout)
    while !condition() {
        guard clock.now < deadline else { throw WaitError.timedOut }
        try await Task.sleep(for: .milliseconds(20))
    }
}

private func readPIDs(from url: URL) -> [pid_t] {
    guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
    return text.split(whereSeparator: \.isNewline).compactMap { pid_t($0) }
}

private func processExists(_ pid: pid_t) -> Bool {
    Darwin.kill(pid, 0) == 0
}
