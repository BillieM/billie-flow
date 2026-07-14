import Darwin
import Foundation
import Testing
@testable import BillieFlowCore

@Suite("Persistent worker process")
struct WorkerProcessTests {
    @Test func installerProcessRunnerHandlesAnImmediateExit() async throws {
        let runner = ProcessWorkerRuntimeInstallRunner()
        let command = WorkerRuntimeInstallCommand(
            executableURL: URL(fileURLWithPath: "/usr/bin/true"),
            arguments: [],
            environment: [:]
        )

        #expect(try await runner.run(command) == 0)
    }

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

    @Test func installerRunsPinnedLocalSetupPhasesWithoutModels() async throws {
        let configuration = installConfiguration()
        let runner = RecordingInstallRunner()
        let fileSystem = FakeInstallFileSystem(configuration: configuration)
        let installer = WorkerRuntimeInstaller(
            configuration: configuration,
            runner: runner,
            fileSystem: fileSystem
        )
        let phases = InstallPhaseCollector()

        try await installer.install { phases.append($0) }

        #expect(phases.values == WorkerRuntimeInstallPhase.allCases)
        let commands = await runner.commands
        #expect(commands.count == 6)
        #expect(commands[0].executableURL == configuration.uvURL)
        #expect(commands[0].arguments == [
            "venv", "--clear", "--python", "3.12", "--seed",
            configuration.virtualEnvironmentURL.path,
        ])
        #expect(commands[0].environment["UV_NO_CACHE"] == "1")
        #expect(commands[0].environment["UV_PYTHON_INSTALL_DIR"] == configuration.runtimeRootURL.appendingPathComponent("python").path)
        #expect(commands[1].arguments.contains(configuration.requirementsURL.path))
        #expect(commands[2].arguments.contains(configuration.workerSourceURL.path))
        #expect(commands[3].arguments == ["-m", "billie_flow_worker.prefetch", "--component", "asr"])
        #expect(commands[4].arguments == ["-m", "billie_flow_worker.prefetch", "--component", "cleanup"])
        #expect(commands[5].arguments.joined(separator: " ").contains("billie_flow_worker"))
        #expect(WorkerRuntimeInstallConfiguration.uvVersion == "0.11.28")
    }

    @Test func installerReportsTheFailingPhaseAndCanRetry() async throws {
        let configuration = installConfiguration()
        let runner = RecordingInstallRunner(exitStatuses: [0, 23])
        let installer = WorkerRuntimeInstaller(
            configuration: configuration,
            runner: runner,
            fileSystem: FakeInstallFileSystem(configuration: configuration)
        )

        do {
            try await installer.install()
            Issue.record("Installer unexpectedly passed a failed uv command.")
        } catch let error as WorkerRuntimeInstallError {
            #expect(error == .commandFailed(.installingRuntime, 23))
        }

        await runner.replaceExitStatuses(with: Array(repeating: 0, count: 6))
        try await installer.install()
        #expect(await runner.commands.count == 8)
    }

    @Test func installerCancellationStopsTheActiveProcess() async throws {
        let configuration = installConfiguration()
        let runner = RecordingInstallRunner(blockFirstCommand: true)
        let installer = WorkerRuntimeInstaller(
            configuration: configuration,
            runner: runner,
            fileSystem: FakeInstallFileSystem(configuration: configuration)
        )
        let installation = Task { try await installer.install() }
        try await waitUntilAsync { await runner.hasStarted }

        installation.cancel()
        do {
            try await installation.value
            Issue.record("Cancelled installation unexpectedly completed.")
        } catch is CancellationError {
            // Cancellation is the public contract.
        }
        try await waitUntilAsync { await runner.wasCancelled }
        #expect(await runner.wasCancelled)
    }
}

private final class TestBundleMarker {}

private final class PhaseCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [WorkerPhase] = []
    var values: [WorkerPhase] { lock.withLock { storage } }
    func append(_ phase: WorkerPhase) { lock.withLock { storage.append(phase) } }
}

private final class InstallPhaseCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [WorkerRuntimeInstallPhase] = []
    var values: [WorkerRuntimeInstallPhase] { lock.withLock { storage } }
    func append(_ phase: WorkerRuntimeInstallPhase) { lock.withLock { storage.append(phase) } }
}

private actor RecordingInstallRunner: WorkerRuntimeInstallProcessRunning {
    private(set) var commands: [WorkerRuntimeInstallCommand] = []
    private var exitStatuses: [Int32]
    private let blockFirstCommand: Bool
    private(set) var wasCancelled = false

    init(exitStatuses: [Int32] = [], blockFirstCommand: Bool = false) {
        self.exitStatuses = exitStatuses
        self.blockFirstCommand = blockFirstCommand
    }

    var hasStarted: Bool { !commands.isEmpty }

    func run(_ command: WorkerRuntimeInstallCommand) async throws -> Int32 {
        commands.append(command)
        if blockFirstCommand, commands.count == 1 {
            try await Task.sleep(for: .seconds(30))
        }
        return exitStatuses.isEmpty ? 0 : exitStatuses.removeFirst()
    }

    func cancel() async {
        wasCancelled = true
    }

    func replaceExitStatuses(with values: [Int32]) {
        exitStatuses = values
    }
}

private struct FakeInstallFileSystem: WorkerRuntimeInstallFileSystem {
    let configuration: WorkerRuntimeInstallConfiguration

    func createDirectory(at url: URL) throws {}

    func fileExists(atPath path: String) -> Bool {
        path == configuration.pyprojectURL.path || path == configuration.requirementsURL.path
    }

    func isExecutableFile(atPath path: String) -> Bool {
        path == configuration.uvURL.path || path == configuration.workerExecutableURL.path
    }
}

private func installConfiguration() -> WorkerRuntimeInstallConfiguration {
    WorkerRuntimeInstallConfiguration(
        uvURL: URL(fileURLWithPath: "/bundle/Bootstrap/uv"),
        workerSourceURL: URL(fileURLWithPath: "/bundle/Bootstrap/worker", isDirectory: true),
        runtimeRootURL: URL(fileURLWithPath: "/home/Library/Application Support/Billie Flow/runtime", isDirectory: true)
    )
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

private func waitUntilAsync(
    timeout: Duration = .seconds(5),
    condition: @escaping @Sendable () async -> Bool
) async throws {
    let clock = ContinuousClock()
    let deadline = clock.now.advanced(by: timeout)
    while !(await condition()) {
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
