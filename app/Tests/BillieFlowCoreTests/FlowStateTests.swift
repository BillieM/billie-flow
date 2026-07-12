import Foundation
import Testing
@testable import BillieFlowCore

@Suite("Flow lifecycle")
struct FlowStateTests {
    @Test func happyPathIncludesFrozenPhaseAndWarning() {
        var machine = FlowStateMachine(hasHotkey: true)
        #expect(machine.handle(.recordingStarted) == .recording)
        #expect(machine.handle(.recordingStopped) == .processing(nil))
        #expect(machine.handle(.phase(.transcribing)) == .processing(.transcribing))
        #expect(machine.handle(.completed(Self.fallback)) == .copied(warning: WorkerProtocol.cleanupFallbackWarning))
        #expect(machine.handle(.dismiss) == .idle)
    }

    @Test func invalidTransitionsDoNotStartWithoutHotkey() {
        var machine = FlowStateMachine(hasHotkey: false)
        #expect(machine.handle(.recordingStarted) == .needsHotkey)
        #expect(machine.handle(.hotkeyConfigured) == .idle)
    }

    @Test func cancelRestoresIdle() {
        var machine = FlowStateMachine(hasHotkey: true)
        machine.handle(.recordingStarted)
        #expect(machine.handle(.cancel) == .idle)
        machine.handle(.recordingStarted)
        machine.handle(.recordingStopped)
        #expect(machine.handle(.cancel) == .idle)
    }

    @Test func warningAndFailurePersistButAllowRecovery() {
        var warningMachine = FlowStateMachine(hasHotkey: true)
        warningMachine.handle(.recordingStarted)
        warningMachine.handle(.recordingStopped)
        let warning = warningMachine.handle(.completed(Self.fallback))
        #expect(warning.requiresExplicitDismissal)
        #expect(warning.allowsRecordingStart)
        #expect(warningMachine.handle(.recordingStarted) == .recording)

        var failureMachine = FlowStateMachine(hasHotkey: true)
        let failure = failureMachine.handle(.failed("Microphone denied."))
        #expect(failure.requiresExplicitDismissal)
        #expect(failure.allowsRecordingStart)
        #expect(failureMachine.handle(.dismiss) == .idle)
    }

    @Test func ordinarySuccessDoesNotRequireExplicitDismissal() {
        var machine = FlowStateMachine(hasHotkey: true)
        machine.handle(.recordingStarted)
        machine.handle(.recordingStopped)
        let copied = machine.handle(.completed(Self.success))
        #expect(!copied.requiresExplicitDismissal)
        #expect(copied.allowsRecordingStart)
    }

    @Test func temporaryAudioDeletesIdempotently() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try Data("audio".utf8).write(to: url)
        let audio = TemporaryAudio(url: url)
        #expect(FileManager.default.fileExists(atPath: url.path))
        try audio.delete()
        try audio.delete()
        #expect(!FileManager.default.fileExists(atPath: url.path))
    }

    @Test func temporaryAudioRetriesAfterInjectedRemovalFailure() throws {
        let fileSystem = FlakyFileSystem()
        let audio = TemporaryAudio(url: URL(fileURLWithPath: "/private/tmp/fake.wav"), fileSystem: fileSystem)
        #expect(throws: (any Error).self) { try audio.delete() }
        #expect(fileSystem.removalAttempts == 1)
        #expect(audio.deleteWithRetries(attempts: 2))
        #expect(fileSystem.removalAttempts == 2)
        #expect(!fileSystem.exists)
    }

    @Test func recordingDurationPolicyUsesApprovedBounds() {
        #expect(RecordingPolicy.disposition(for: 0.499) == .discardTooShort)
        #expect(RecordingPolicy.disposition(for: 0.5) == .submit)
        #expect(RecordingPolicy.maximumDuration == 300)
        #expect(RecordingPolicy.normalizedLevel(decibels: -60) == 0)
        #expect(RecordingPolicy.normalizedLevel(decibels: 0) == 1)
    }

    @Test func staleCleanupOnlyRemovesWAVs() throws {
        let fileSystem = StaleFileSystem(files: [
            URL(fileURLWithPath: "/tmp/one.wav"),
            URL(fileURLWithPath: "/tmp/TWO.WAV"),
            URL(fileURLWithPath: "/tmp/keep.txt"),
        ])
        let removed = try RecordingStorage.removeStaleWAVs(
            in: URL(fileURLWithPath: "/tmp"), fileSystem: fileSystem
        )
        #expect(removed == 2)
        #expect(fileSystem.remaining.map(\.lastPathComponent) == ["keep.txt"])
    }

    @Test func healthStatesAndPointerScreenSelectionAreDeterministic() {
        let states: [WorkerHealth] = [.executableMissing, .executablePresent, .connecting, .ready, .warm]
        #expect(states.count == 5)
        let frames = [CGRect(x: 0, y: 0, width: 100, height: 100), CGRect(x: 100, y: 0, width: 100, height: 100)]
        #expect(ScreenSelection.index(containing: CGPoint(x: 150, y: 50), frames: frames) == 1)
        #expect(ScreenSelection.index(containing: CGPoint(x: 250, y: 50), frames: frames) == nil)
    }

    private static let fallback = ProcessResult(
        rawASR: "Raw speech.", rawCleanup: nil, finalText: "Raw speech.", corrections: [],
        timings: WorkerTimings(
            loadingASRSeconds: 0, asrSeconds: 1, loadingCleanupSeconds: 0,
            cleanupSeconds: 0.1, correctionSeconds: 0, totalSeconds: 1.1
        ),
        asrModel: WorkerProtocol.asrModel,
        cleanupModel: WorkerProtocol.cleanupModel,
        style: .lightCleanup,
        warning: WorkerProtocol.cleanupFallbackWarning
    )

    private static let success = ProcessResult(
        rawASR: "Speech.", rawCleanup: "Speech.", finalText: "Speech.", corrections: [],
        timings: WorkerTimings(
            loadingASRSeconds: 0, asrSeconds: 1, loadingCleanupSeconds: 0,
            cleanupSeconds: 0.1, correctionSeconds: 0, totalSeconds: 1.1
        ),
        asrModel: WorkerProtocol.asrModel,
        cleanupModel: WorkerProtocol.cleanupModel,
        style: .lightCleanup,
        warning: nil
    )
}

private final class StaleFileSystem: StaleRecordingFileSystem, @unchecked Sendable {
    private let lock = NSLock()
    private var files: [URL]
    init(files: [URL]) { self.files = files }
    var remaining: [URL] { lock.withLock { files } }
    func contentsOfDirectory(at URL: URL) throws -> [URL] { lock.withLock { files } }
    func removeItem(at URL: URL) throws { lock.withLock { files.removeAll { $0 == URL } } }
}

private final class FlakyFileSystem: AudioFileSystem, @unchecked Sendable {
    private let lock = NSLock()
    private(set) var exists = true
    private(set) var removalAttempts = 0

    func fileExists(atPath path: String) -> Bool { lock.withLock { exists } }

    func removeItem(at URL: URL) throws {
        try lock.withLock {
            removalAttempts += 1
            if removalAttempts == 1 { throw TemporaryAudioError.deletionFailed }
            exists = false
        }
    }
}
