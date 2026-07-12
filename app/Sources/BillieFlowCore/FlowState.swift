import Foundation

public enum FlowState: Equatable, Sendable {
    case needsHotkey
    case idle
    case recording
    case processing(WorkerPhase?)
    case copied(warning: String?)
    case failed(message: String)

    public var isBusy: Bool {
        switch self {
        case .recording, .processing: true
        default: false
        }
    }
}

public enum FlowEvent: Equatable, Sendable {
    case hotkeyConfigured
    case recordingStarted
    case recordingStopped
    case phase(WorkerPhase)
    case completed(ProcessResult)
    case failed(String)
    case cancel
    case dismiss
}

public struct FlowStateMachine: Sendable {
    public private(set) var state: FlowState

    public init(hasHotkey: Bool) {
        state = hasHotkey ? .idle : .needsHotkey
    }

    @discardableResult
    public mutating func handle(_ event: FlowEvent) -> FlowState {
        switch (state, event) {
        case (.needsHotkey, .hotkeyConfigured): state = .idle
        case (.idle, .recordingStarted): state = .recording
        case (.recording, .recordingStopped): state = .processing(nil)
        case (.processing, let .phase(phase)): state = .processing(phase)
        case (.processing, let .completed(result)):
            state = .copied(warning: result.warning)
        case (_, let .failed(message)): state = .failed(message: message)
        case (.recording, .cancel), (.processing, .cancel): state = .idle
        case (.copied, .dismiss), (.failed, .dismiss): state = .idle
        default: break
        }
        return state
    }
}

public enum ClipboardDecision: Equatable, Sendable {
    case copy(String, warning: String?)
    case preserve
}

public enum ClipboardPolicy {
    public static func decision(for result: Result<ProcessResult, any Error>) -> ClipboardDecision {
        switch result {
        case let .success(value) where !value.finalText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty:
            return .copy(value.finalText, warning: value.warning)
        default:
            return .preserve
        }
    }
}

public protocol AudioFileSystem: Sendable {
    func fileExists(atPath path: String) -> Bool
    func removeItem(at URL: URL) throws
}

extension FileManager: AudioFileSystem {}

public enum TemporaryAudioError: Error, Equatable, Sendable {
    case deletionFailed
}

public final class TemporaryAudio: @unchecked Sendable {
    public let url: URL
    private let fileSystem: any AudioFileSystem
    private let lock = NSLock()
    private var deleted = false

    public init(url: URL, fileSystem: any AudioFileSystem = FileManager.default) {
        self.url = url
        self.fileSystem = fileSystem
    }

    deinit { _ = deleteWithRetries() }

    public func delete() throws {
        lock.lock()
        defer { lock.unlock() }
        guard !deleted else { return }
        if !fileSystem.fileExists(atPath: url.path) {
            deleted = true
            return
        }
        try fileSystem.removeItem(at: url)
        guard !fileSystem.fileExists(atPath: url.path) else {
            throw TemporaryAudioError.deletionFailed
        }
        deleted = true
    }

    @discardableResult
    public func deleteWithRetries(attempts: Int = 5) -> Bool {
        for attempt in 0..<max(1, attempts) {
            do {
                try delete()
                return true
            } catch {
                if attempt + 1 < attempts {
                    Thread.sleep(forTimeInterval: 0.02 * Double(attempt + 1))
                }
            }
        }
        return false
    }
}
