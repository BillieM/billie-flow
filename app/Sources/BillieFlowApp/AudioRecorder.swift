@preconcurrency import AVFoundation
import BillieFlowCore
import Foundation

@MainActor
final class AudioRecorder {
    struct Recording {
        let audio: TemporaryAudio
        let duration: TimeInterval
    }

    var onMeter: ((TimeInterval, Double) -> Void)?
    enum RecorderError: LocalizedError {
        case microphoneDenied
        case formatUnavailable
        case recordingFailed(String)

        var errorDescription: String? {
            switch self {
            case .microphoneDenied: "Microphone access is required to record."
            case .formatUnavailable: "The microphone audio format is unavailable."
            case let .recordingFailed(message): message
            }
        }
    }

    private final class Capture: @unchecked Sendable {
        let writer: PCMRecordingWriter

        init(writer: PCMRecordingWriter) { self.writer = writer }

        func consume(_ input: AVAudioPCMBuffer) { writer.append(input) }

        func finish() throws -> TimeInterval { try writer.finish() }
    }

    private let engine = AVAudioEngine()
    private var capture: Capture?
    private var audio: TemporaryAudio?

    func start() async throws {
        guard capture == nil else { return }
        guard await requestMicrophoneAccess() else { throw RecorderError.microphoneDenied }

        let folder = RecordingStorage.directory()
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let audio = TemporaryAudio(url: folder.appendingPathComponent("\(UUID().uuidString).wav"))
        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0 else {
            throw RecorderError.formatUnavailable
        }

        do {
            let writer = try PCMRecordingWriter(outputURL: audio.url, inputFormat: inputFormat) { [weak self] elapsed, level in
                Task { @MainActor in self?.onMeter?(elapsed, level) }
            }
            let capture = Capture(writer: writer)
            Self.installRealtimeTap(
                on: input,
                inputFormat: inputFormat,
                capture: capture
            )
            engine.prepare()
            try engine.start()
            self.capture = capture
            self.audio = audio
        } catch {
            input.removeTap(onBus: 0)
            _ = audio.deleteWithRetries()
            throw RecorderError.recordingFailed(error.localizedDescription)
        }
    }

    func stop() throws -> Recording {
        guard let capture, let audio else { throw RecorderError.recordingFailed("No recording is active.") }
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        self.capture = nil
        self.audio = nil
        do {
            let duration = try capture.finish()
            return Recording(audio: audio, duration: duration)
        } catch {
            _ = audio.deleteWithRetries()
            throw error
        }
    }

    func cancel() {
        if capture != nil {
            engine.stop()
            engine.inputNode.removeTap(onBus: 0)
        }
        capture = nil
        _ = audio?.deleteWithRetries()
        audio = nil
    }

    /// AVAudioEngine invokes tap blocks on a realtime audio queue. Build the
    /// callback outside the recorder's MainActor isolation so Swift 6 does not
    /// install a main-executor precondition on every incoming audio buffer.
    nonisolated private static func installRealtimeTap(
        on input: AVAudioInputNode,
        inputFormat: AVAudioFormat,
        capture: Capture
    ) {
        input.installTap(onBus: 0, bufferSize: 2_048, format: inputFormat) { buffer, _ in
            capture.consume(buffer)
        }
    }

    private func requestMicrophoneAccess() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: true
        case .notDetermined: await AVCaptureDevice.requestAccess(for: .audio)
        default: false
        }
    }
}
