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
