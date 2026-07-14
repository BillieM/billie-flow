import Darwin
import Foundation

public struct WorkerLaunchConfiguration: Sendable, Equatable {
    public let executableURL: URL
    public let arguments: [String]
    public let environment: [String: String]?

    public init(executableURL: URL, arguments: [String] = [], environment: [String: String]? = nil) {
        self.executableURL = executableURL
        self.arguments = arguments
        self.environment = environment
    }

    public static func installed(fileManager: FileManager = .default) throws -> Self {
        let support = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let executable = support
            .appendingPathComponent("Billie Flow", isDirectory: true)
            .appendingPathComponent("runtime", isDirectory: true)
            .appendingPathComponent(".venv", isDirectory: true)
            .appendingPathComponent("bin", isDirectory: true)
            .appendingPathComponent("billie-flow-worker", isDirectory: false)
        return Self(executableURL: executable)
    }
}

public enum WorkerRuntimeInstallPhase: String, CaseIterable, Sendable {
    case preparingPython
    case installingRuntime
    case downloadingSpeechModel
    case downloadingCleanupModel
    case verifying
}

public enum WorkerRuntimeInstallStatus: Equatable, Sendable {
    case idle
    case installing(WorkerRuntimeInstallPhase)
    case installed
    case cancelled
    case failed(String)

    public var isInstalling: Bool {
        if case .installing = self { true } else { false }
    }
}

public struct WorkerRuntimeInstallCommand: Equatable, Sendable {
    public let executableURL: URL
    public let arguments: [String]
    public let environment: [String: String]

    public init(executableURL: URL, arguments: [String], environment: [String: String] = [:]) {
        self.executableURL = executableURL
        self.arguments = arguments
        self.environment = environment
    }
}

public protocol WorkerRuntimeInstallProcessRunning: Sendable {
    func run(_ command: WorkerRuntimeInstallCommand) async throws -> Int32
    func cancel() async
}

public protocol WorkerRuntimeInstallFileSystem: Sendable {
    func createDirectory(at url: URL) throws
    func fileExists(atPath path: String) -> Bool
    func isExecutableFile(atPath path: String) -> Bool
}

public struct LocalWorkerRuntimeInstallFileSystem: WorkerRuntimeInstallFileSystem {
    private let fileManager: FileManager

    public init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
    }

    public func createDirectory(at url: URL) throws {
        try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
    }

    public func isExecutableFile(atPath path: String) -> Bool {
        fileManager.isExecutableFile(atPath: path)
    }

    public func fileExists(atPath path: String) -> Bool {
        fileManager.fileExists(atPath: path)
    }
}

public enum WorkerRuntimeInstallError: LocalizedError, Equatable, Sendable {
    case setupAlreadyRunning
    case bundledUVIsMissing
    case bundledWorkerIsMissing
    case commandFailed(WorkerRuntimeInstallPhase, Int32)
    case verificationFailed

    public var errorDescription: String? {
        switch self {
        case .setupAlreadyRunning:
            "Local setup is already running."
        case .bundledUVIsMissing:
            "The app is missing its bundled setup helper. Download Billie Flow again."
        case .bundledWorkerIsMissing:
            "The app is missing its bundled local worker. Download Billie Flow again."
        case let .commandFailed(phase, _):
            "Local setup failed while \(phase.failureDescription). Check your connection and try again."
        case .verificationFailed:
            "Local setup finished, but the worker could not be verified. Try installing it again."
        }
    }
}

public struct WorkerRuntimeInstallConfiguration: Equatable, Sendable {
    public static let uvVersion = "0.11.28"

    public let uvURL: URL
    public let workerSourceURL: URL
    public let runtimeRootURL: URL

    public init(uvURL: URL, workerSourceURL: URL, runtimeRootURL: URL) {
        self.uvURL = uvURL
        self.workerSourceURL = workerSourceURL
        self.runtimeRootURL = runtimeRootURL
    }

    public var virtualEnvironmentURL: URL {
        runtimeRootURL.appendingPathComponent(".venv", isDirectory: true)
    }

    public var pythonURL: URL {
        virtualEnvironmentURL.appendingPathComponent("bin/python", isDirectory: false)
    }

    public var workerExecutableURL: URL {
        virtualEnvironmentURL.appendingPathComponent("bin/billie-flow-worker", isDirectory: false)
    }

    public var requirementsURL: URL {
        workerSourceURL.appendingPathComponent("requirements.lock", isDirectory: false)
    }

    public var pyprojectURL: URL {
        workerSourceURL.appendingPathComponent("pyproject.toml", isDirectory: false)
    }
}

public actor ProcessWorkerRuntimeInstallRunner: WorkerRuntimeInstallProcessRunning {
    private var process: Process?

    public init() {}

    public func run(_ command: WorkerRuntimeInstallCommand) async throws -> Int32 {
        guard process == nil else { throw WorkerRuntimeInstallError.setupAlreadyRunning }

        let child = Process()
        child.executableURL = command.executableURL
        child.arguments = command.arguments
        if !command.environment.isEmpty {
            child.environment = ProcessInfo.processInfo.environment.merging(command.environment) { _, override in override }
        }
        child.standardOutput = FileHandle.nullDevice
        child.standardError = FileHandle.nullDevice
        process = child
        defer { process = nil }

        let status = try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                child.terminationHandler = { terminated in
                    continuation.resume(returning: terminated.terminationStatus)
                }
                do {
                    try child.run()
                } catch {
                    child.terminationHandler = nil
                    continuation.resume(throwing: error)
                }
            }
        } onCancel: {
            if child.isRunning { child.terminate() }
        }
        child.terminationHandler = nil
        if Task.isCancelled { throw CancellationError() }
        return status
    }

    public func cancel() {
        guard let process, process.isRunning else { return }
        process.terminate()
    }
}

public actor WorkerRuntimeInstaller {
    private let configuration: WorkerRuntimeInstallConfiguration
    private let runner: any WorkerRuntimeInstallProcessRunning
    private let fileSystem: any WorkerRuntimeInstallFileSystem
    private var isRunning = false

    public init(
        configuration: WorkerRuntimeInstallConfiguration,
        runner: any WorkerRuntimeInstallProcessRunning = ProcessWorkerRuntimeInstallRunner(),
        fileSystem: any WorkerRuntimeInstallFileSystem = LocalWorkerRuntimeInstallFileSystem()
    ) {
        self.configuration = configuration
        self.runner = runner
        self.fileSystem = fileSystem
    }

    public func install(
        onPhase: @escaping @Sendable (WorkerRuntimeInstallPhase) -> Void = { _ in }
    ) async throws {
        guard !isRunning else { throw WorkerRuntimeInstallError.setupAlreadyRunning }
        guard fileSystem.isExecutableFile(atPath: configuration.uvURL.path) else {
            throw WorkerRuntimeInstallError.bundledUVIsMissing
        }
        guard fileSystem.fileExists(atPath: configuration.pyprojectURL.path),
              fileSystem.fileExists(atPath: configuration.requirementsURL.path)
        else { throw WorkerRuntimeInstallError.bundledWorkerIsMissing }

        isRunning = true
        defer { isRunning = false }
        try fileSystem.createDirectory(at: configuration.runtimeRootURL)

        try await withTaskCancellationHandler {
            for (phase, commands) in installSteps() {
                try Task.checkCancellation()
                onPhase(phase)
                for command in commands {
                    let status = try await runner.run(command)
                    guard status == 0 else {
                        throw WorkerRuntimeInstallError.commandFailed(phase, status)
                    }
                }
            }
        } onCancel: {
            Task { await self.runner.cancel() }
        }

        guard fileSystem.isExecutableFile(atPath: configuration.workerExecutableURL.path) else {
            throw WorkerRuntimeInstallError.verificationFailed
        }
    }

    public func cancel() async {
        await runner.cancel()
    }

    private func installSteps() -> [(WorkerRuntimeInstallPhase, [WorkerRuntimeInstallCommand])] {
        let uv = configuration.uvURL
        let python = configuration.pythonURL
        let environment = [
            "UV_NO_CACHE": "1",
            "UV_NO_PROGRESS": "1",
            "UV_PYTHON_INSTALL_DIR": configuration.runtimeRootURL
                .appendingPathComponent("python", isDirectory: true).path,
            "PYTHONDONTWRITEBYTECODE": "1",
        ]
        return [
            (
                .preparingPython,
                [WorkerRuntimeInstallCommand(
                    executableURL: uv,
                    arguments: [
                        "venv", "--clear", "--python", "3.12", "--seed",
                        configuration.virtualEnvironmentURL.path,
                    ],
                    environment: environment
                )]
            ),
            (
                .installingRuntime,
                [
                    WorkerRuntimeInstallCommand(
                        executableURL: uv,
                        arguments: [
                            "pip", "install", "--python", python.path,
                            "-r", configuration.requirementsURL.path,
                        ],
                        environment: environment
                    ),
                    WorkerRuntimeInstallCommand(
                        executableURL: uv,
                        arguments: [
                            "pip", "install", "--python", python.path,
                            "--no-deps", "--no-build-isolation", configuration.workerSourceURL.path,
                        ],
                        environment: environment
                    ),
                ]
            ),
            (
                .downloadingSpeechModel,
                [WorkerRuntimeInstallCommand(
                    executableURL: python,
                    arguments: [
                        "-m", "billie_flow_worker.prefetch", "--component", "asr",
                    ],
                    environment: environment
                )]
            ),
            (
                .downloadingCleanupModel,
                [WorkerRuntimeInstallCommand(
                    executableURL: python,
                    arguments: [
                        "-m", "billie_flow_worker.prefetch", "--component", "cleanup",
                    ],
                    environment: environment
                )]
            ),
            (
                .verifying,
                [WorkerRuntimeInstallCommand(
                    executableURL: python,
                    arguments: [
                        "-c",
                        "import sys, billie_flow_worker; assert sys.version_info[:2] == (3, 12)",
                    ],
                    environment: environment
                )]
            ),
        ]
    }
}

private extension WorkerRuntimeInstallPhase {
    var failureDescription: String {
        switch self {
        case .preparingPython: "preparing Python"
        case .installingRuntime: "installing the local runtime"
        case .downloadingSpeechModel: "downloading the speech model"
        case .downloadingCleanupModel: "downloading the cleanup model"
        case .verifying: "verifying the installation"
        }
    }
}

public enum WorkerProcessError: Error, Equatable, Sendable {
    case executableMissing(String)
    case launchFailed(String)
    case notRunning
    case terminated
    case unexpectedTerminal
    case transportFailure
}

public protocol WorkerServing: Sendable {
    func warmup(onPhase: @escaping @Sendable (WorkerPhase) -> Void) async throws
    func process(
        audioURL: URL,
        style: CleanupStyle,
        debug: Bool,
        onPhase: @escaping @Sendable (WorkerPhase) -> Void
    ) async throws -> ProcessResult
    func cancel() async
    func shutdown() async
}

public actor WorkerProcess: WorkerServing {
    private struct Pending {
        let continuation: CheckedContinuation<WorkerTerminal, any Error>
        let onPhase: @Sendable (WorkerPhase) -> Void
    }

    private let configuration: WorkerLaunchConfiguration
    private let fileManager: FileManager
    private var process: Process?
    private var input: FileHandle?
    private var readerTask: Task<Void, Never>?
    private var pending: [String: Pending] = [:]
    private var isReady = false
    private var isWarm = false

    public init(configuration: WorkerLaunchConfiguration, fileManager: FileManager = .default) {
        self.configuration = configuration
        self.fileManager = fileManager
    }

    public init(fileManager: FileManager = .default) throws {
        self.configuration = try .installed(fileManager: fileManager)
        self.fileManager = fileManager
    }

    deinit {
        readerTask?.cancel()
        if let process, process.isRunning {
            process.terminate()
        }
    }

    public func warmup(onPhase: @escaping @Sendable (WorkerPhase) -> Void = { _ in }) async throws {
        try await ensureStarted()
        if isWarm { return }
        let id = requestID(prefix: "warmup")
        let terminal = try await send(
            id: id,
            data: WorkerProtocol.warmup(id: id),
            onPhase: onPhase
        )
        guard terminal == .warmup else { throw WorkerProcessError.unexpectedTerminal }
        isWarm = true
    }

    public func process(
        audioURL: URL,
        style: CleanupStyle,
        debug: Bool = false,
        onPhase: @escaping @Sendable (WorkerPhase) -> Void = { _ in }
    ) async throws -> ProcessResult {
        try await warmup(onPhase: onPhase)
        let id = requestID(prefix: "process")
        let terminal = try await send(
            id: id,
            data: WorkerProtocol.process(
                id: id,
                audioPath: audioURL.path,
                style: style,
                debug: debug
            ),
            onPhase: onPhase
        )
        guard case let .process(result) = terminal else { throw WorkerProcessError.unexpectedTerminal }
        return result
    }

    public func shutdown() async {
        guard process?.isRunning == true, isReady else {
            await stopImmediately()
            return
        }
        do {
            let id = requestID(prefix: "shutdown")
            _ = try await send(id: id, data: WorkerProtocol.shutdown(id: id), onPhase: { _ in })
        } catch {
            // Graceful shutdown is best-effort; forced cleanup below is authoritative.
        }
        await stopImmediately()
    }

    public func cancel() async {
        await stopImmediately()
    }

    private func ensureStarted() async throws {
        if isReady, process?.isRunning == true { return }
        guard fileManager.isExecutableFile(atPath: configuration.executableURL.path) else {
            throw WorkerProcessError.executableMissing(configuration.executableURL.path)
        }

        let child = Process()
        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        child.executableURL = configuration.executableURL
        child.arguments = configuration.arguments
        if let environment = configuration.environment {
            child.environment = ProcessInfo.processInfo.environment.merging(environment) { _, override in override }
        }
        child.standardInput = stdinPipe
        child.standardOutput = stdoutPipe
        child.standardError = FileHandle.nullDevice

        do {
            try child.run()
        } catch {
            throw WorkerProcessError.launchFailed(error.localizedDescription)
        }

        process = child
        input = stdinPipe.fileHandleForWriting
        startReader(stdoutPipe.fileHandleForReading)

        let id = requestID(prefix: "hello")
        do {
            let terminal = try await send(
                id: id,
                data: WorkerProtocol.hello(id: id),
                onPhase: { _ in }
            )
            guard case .ready = terminal else { throw WorkerProcessError.unexpectedTerminal }
            isReady = true
        } catch {
            await stopImmediately()
            throw error
        }
    }

    private func send(
        id: String,
        data: Data,
        onPhase: @escaping @Sendable (WorkerPhase) -> Void
    ) async throws -> WorkerTerminal {
        guard let input, process?.isRunning == true else { throw WorkerProcessError.notRunning }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                pending[id] = Pending(continuation: continuation, onPhase: onPhase)
                do {
                    try input.write(contentsOf: data)
                } catch {
                    pending.removeValue(forKey: id)
                    continuation.resume(throwing: WorkerProcessError.transportFailure)
                }
            }
        } onCancel: {
            Task { await self.cancel() }
        }
    }

    private func startReader(_ output: FileHandle) {
        readerTask = Task.detached(priority: .userInitiated) { [weak self] in
            var buffer = Data()
            while !Task.isCancelled {
                let chunk = output.availableData
                if chunk.isEmpty { break }
                buffer.append(chunk)
                while let newline = buffer.firstIndex(of: 0x0A) {
                    let line = buffer[..<newline]
                    buffer.removeSubrange(...newline)
                    guard !line.isEmpty else {
                        await self?.transportFailed()
                        return
                    }
                    await self?.consume(Data(line))
                }
            }
            if !buffer.isEmpty { await self?.transportFailed() }
            await self?.readerEnded()
        }
    }

    private func consume(_ line: Data) {
        do {
            let event = try WorkerProtocol.decode(line: line)
            switch event {
            case let .phase(requestID, phase):
                pending[requestID]?.onPhase(phase)
            case let .terminal(requestID, terminal):
                pending.removeValue(forKey: requestID)?.continuation.resume(returning: terminal)
            case let .failure(requestID, payload):
                pending.removeValue(forKey: requestID)?.continuation.resume(throwing: payload)
            }
        } catch {
            transportFailed()
        }
    }

    private func readerEnded() {
        if !pending.isEmpty { failPending(with: WorkerProcessError.terminated) }
    }

    private func transportFailed() {
        failPending(with: WorkerProcessError.transportFailure)
        if let child = process, child.isRunning { child.terminate() }
        isReady = false
        isWarm = false
    }

    private func failPending(with error: any Error) {
        let requests = pending.values
        pending.removeAll()
        for request in requests { request.continuation.resume(throwing: error) }
    }

    private func stopImmediately() async {
        readerTask?.cancel()
        readerTask = nil
        input?.closeFile()
        input = nil
        failPending(with: CancellationError())

        if let child = process {
            if child.isRunning {
                child.terminate()
                try? await Task.sleep(for: .milliseconds(750))
                if child.isRunning { Darwin.kill(child.processIdentifier, SIGKILL) }
            }
            child.waitUntilExit()
        }
        process = nil
        isReady = false
        isWarm = false
    }

    private func requestID(prefix: String) -> String {
        "\(prefix)-\(UUID().uuidString.lowercased())"
    }
}
