@preconcurrency import AVFoundation
import Carbon
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
        #expect(RecordingPolicy.disposition(for: 0) == .discardTooShort)
        #expect(RecordingPolicy.disposition(for: 0.499) == .discardTooShort)
        #expect(RecordingPolicy.disposition(for: 0.5) == .submit)
        #expect(RecordingPolicy.disposition(for: RecordingPolicy.maximumDuration) == .submit)
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

    @Test func productionConverterFinalizes16kMonoInt16WAV() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID()).wav")
        defer { try? FileManager.default.removeItem(at: url) }
        let inputFormat = try #require(AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: 48_000,
            channels: 2,
            interleaved: false
        ))
        let meters = MeterCollector()
        let writer = try PCMRecordingWriter(outputURL: url, inputFormat: inputFormat) {
            elapsed, level in meters.append(elapsed: elapsed, level: level)
        }

        let framesPerBuffer: AVAudioFrameCount = 4_800
        for chunk in 0..<10 {
            let buffer = try #require(AVAudioPCMBuffer(
                pcmFormat: inputFormat,
                frameCapacity: framesPerBuffer
            ))
            buffer.frameLength = framesPerBuffer
            let channels = try #require(buffer.floatChannelData)
            for frame in 0..<Int(framesPerBuffer) {
                let sampleIndex = chunk * Int(framesPerBuffer) + frame
                let sample = Float(sin(2 * Double.pi * 440 * Double(sampleIndex) / 48_000) * 0.25)
                channels[0][frame] = sample
                channels[1][frame] = sample * 0.5
            }
            writer.append(buffer)
        }

        let duration = try writer.finish()
        #expect(abs(duration - 1) < 0.02)
        let wav = try AVAudioFile(forReading: url)
        #expect(wav.fileFormat.sampleRate == PCMRecordingWriter.sampleRate)
        #expect(wav.fileFormat.channelCount == PCMRecordingWriter.channelCount)
        #expect(wav.fileFormat.commonFormat == .pcmFormatInt16)
        #expect(wav.fileFormat.isInterleaved)
        #expect(abs(Double(wav.length) / wav.fileFormat.sampleRate - duration) < 0.001)
        #expect(meters.values.count == 10)
        #expect(meters.values.allSatisfy { $0.level > 0 && $0.level <= 1 })
        #expect(meters.values.last?.elapsed == duration)
    }

    @Test func cancellationCannotBypassTemporaryAudioDeletion() async throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID()).wav")
        try Data("audio".utf8).write(to: url)
        let audio = TemporaryAudio(url: url)
        let operation = Task {
            try await audio.deletingAfter {
                try await Task.sleep(for: .seconds(30))
                return true
            }
        }
        operation.cancel()
        do {
            _ = try await operation.value
            Issue.record("Cancelled audio operation unexpectedly completed.")
        } catch is CancellationError {
            // Expected: deletion happens before cancellation is rethrown.
        }
        #expect(!FileManager.default.fileExists(atPath: url.path))
    }

    @Test func clipboardPreservesExistingContentOnEmptyOrFailureAndCopiesFallback() {
        #expect(ClipboardPolicy.decision(for: .success(Self.success)) == .copy("Speech.", warning: nil))
        #expect(
            ClipboardPolicy.decision(for: .success(Self.fallback))
                == .copy("Raw speech.", warning: WorkerProtocol.cleanupFallbackWarning)
        )
        let empty = ProcessResult(
            rawASR: "", rawCleanup: nil, finalText: " \n ", corrections: [],
            timings: Self.success.timings,
            asrModel: WorkerProtocol.asrModel,
            cleanupModel: WorkerProtocol.cleanupModel,
            style: .lightCleanup,
            warning: nil
        )
        #expect(ClipboardPolicy.decision(for: .success(empty)) == .preserve)
        #expect(ClipboardPolicy.decision(for: .failure(TestFailure.expected)) == .preserve)
    }

    @Test func hotKeyValidationAndRebindingAreTransactional() throws {
        let commandA = HotKey(keyCode: 0, modifiers: UInt32(cmdKey))
        let controlSpace = HotKey(keyCode: 49, modifiers: UInt32(controlKey))
        let optionOnly = HotKey(keyCode: 49, modifiers: UInt32(optionKey))
        #expect(commandA.hasRequiredModifier)
        #expect(controlSpace.hasRequiredModifier)
        #expect(!optionOnly.hasRequiredModifier)
        #expect(controlSpace.displayName == "⌃Space")
        let encoded = try JSONEncoder().encode(controlSpace)
        #expect(try JSONDecoder().decode(HotKey.self, from: encoded) == controlSpace)

        var binding = HotKeyBinding(current: commandA)
        #expect(throws: HotKeyBindingError.invalidModifiers) {
            try binding.rebind(to: optionOnly) { _ in Issue.record("Invalid shortcut was registered.") }
        }
        #expect(binding.current == commandA)
        #expect(throws: TestFailure.conflict) {
            try binding.rebind(to: controlSpace) { _ in throw TestFailure.conflict }
        }
        #expect(binding.current == commandA)

        var registrations = 0
        #expect(try binding.rebind(to: controlSpace) { _ in registrations += 1 })
        #expect(binding.current == controlSpace)
        #expect(!(try binding.rebind(to: controlSpace) { _ in registrations += 1 }))
        #expect(registrations == 1)
    }

    @Test func settingsDefaultsAndWorkerHealthAreStable() {
        #expect(SettingsPolicy.style(storedValue: nil) == .lightCleanup)
        #expect(SettingsPolicy.style(storedValue: "unknown") == .lightCleanup)
        #expect(SettingsPolicy.style(storedValue: CleanupStyle.message.rawValue) == .message)
        #expect(SettingsPolicy.workerHealth(executableExists: true) == .executablePresent)
        #expect(SettingsPolicy.workerHealth(executableExists: false) == .executableMissing)
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

private enum TestFailure: Error, Equatable {
    case expected
    case conflict
}

private final class MeterCollector: @unchecked Sendable {
    struct Value { let elapsed: TimeInterval; let level: Double }
    private let lock = NSLock()
    private var storage: [Value] = []
    var values: [Value] { lock.withLock { storage } }
    func append(elapsed: TimeInterval, level: Double) {
        lock.withLock { storage.append(Value(elapsed: elapsed, level: level)) }
    }
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
