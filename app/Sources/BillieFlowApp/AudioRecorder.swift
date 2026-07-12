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
        case conversionFailed
        case recordingFailed(String)

        var errorDescription: String? {
            switch self {
            case .microphoneDenied: "Microphone access is required to record."
            case .formatUnavailable: "The microphone audio format is unavailable."
            case .conversionFailed: "Audio could not be converted to 16 kHz mono."
            case let .recordingFailed(message): message
            }
        }
    }

    private final class Capture: @unchecked Sendable {
        private final class ConverterInput: @unchecked Sendable {
            let buffer: AVAudioPCMBuffer
            var supplied = false

            init(_ buffer: AVAudioPCMBuffer) { self.buffer = buffer }

            func next(_ status: UnsafeMutablePointer<AVAudioConverterInputStatus>) -> AVAudioBuffer? {
                if supplied {
                    status.pointee = .noDataNow
                    return nil
                }
                supplied = true
                status.pointee = .haveData
                return buffer
            }
        }

        let lock = NSLock()
        var file: AVAudioFile?
        var converter: AVAudioConverter?
        var error: (any Error)?
        var duration: TimeInterval = 0
        let onMeter: @Sendable (TimeInterval, Double) -> Void

        init(file: AVAudioFile, converter: AVAudioConverter, onMeter: @escaping @Sendable (TimeInterval, Double) -> Void) {
            self.file = file
            self.converter = converter
            self.onMeter = onMeter
        }

        func consume(_ input: AVAudioPCMBuffer, outputFormat: AVAudioFormat) {
            lock.lock()
            defer { lock.unlock() }
            guard error == nil, let file, let converter else { return }

            let ratio = outputFormat.sampleRate / input.format.sampleRate
            let capacity = AVAudioFrameCount(ceil(Double(input.frameLength) * ratio)) + 32
            guard let output = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
                error = RecorderError.conversionFailed
                return
            }

            let provider = ConverterInput(input)
            var conversionError: NSError?
            let status = converter.convert(to: output, error: &conversionError) { _, status in
                provider.next(status)
            }
            guard status == .haveData || status == .inputRanDry else {
                error = conversionError ?? RecorderError.conversionFailed
                return
            }
            guard output.frameLength > 0 else { return }
            do {
                try file.write(from: output)
                duration += Double(output.frameLength) / outputFormat.sampleRate
                onMeter(duration, Self.level(of: input))
            } catch { self.error = error }
        }

        private static func level(of buffer: AVAudioPCMBuffer) -> Double {
            guard let channel = buffer.floatChannelData?[0], buffer.frameLength > 0 else { return 0 }
            var sum: Float = 0
            for index in 0..<Int(buffer.frameLength) { sum += channel[index] * channel[index] }
            let rms = sqrt(sum / Float(buffer.frameLength))
            let decibels = rms > 0 ? 20 * log10(rms) : -60
            return RecordingPolicy.normalizedLevel(decibels: decibels)
        }

        func finish() throws {
            lock.lock()
            defer { lock.unlock() }
            file = nil
            converter = nil
            if let error { throw error }
        }
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
        let outputFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: 16_000,
            channels: 1,
            interleaved: true
        )!
        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0,
              let converter = AVAudioConverter(from: inputFormat, to: outputFormat)
        else { throw RecorderError.formatUnavailable }

        do {
            let file = try AVAudioFile(forWriting: audio.url, settings: outputFormat.settings)
            let capture = Capture(file: file, converter: converter) { [weak self] elapsed, level in
                Task { @MainActor in self?.onMeter?(elapsed, level) }
            }
            input.installTap(onBus: 0, bufferSize: 2_048, format: inputFormat) { buffer, _ in
                capture.consume(buffer, outputFormat: outputFormat)
            }
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
            try capture.finish()
            return Recording(audio: audio, duration: capture.duration)
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

    private func requestMicrophoneAccess() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: true
        case .notDetermined: await AVCaptureDevice.requestAccess(for: .audio)
        default: false
        }
    }
}
