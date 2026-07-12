@preconcurrency import AVFoundation
import Foundation

/// Production audio conversion and WAV writing path used by `AudioRecorder`.
public final class PCMRecordingWriter: @unchecked Sendable {
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

    public enum WriterError: LocalizedError {
        case formatUnavailable
        case conversionFailed
        case alreadyFinished

        public var errorDescription: String? {
            switch self {
            case .formatUnavailable: "The microphone audio format is unavailable."
            case .conversionFailed: "Audio could not be converted to 16 kHz mono."
            case .alreadyFinished: "The recording has already finished."
            }
        }
    }

    public static let sampleRate: Double = 16_000
    public static let channelCount: AVAudioChannelCount = 1

    private let lock = NSLock()
    private let outputFormat: AVAudioFormat
    private var file: AVAudioFile?
    private var converter: AVAudioConverter?
    private var storedError: (any Error)?
    private var storedDuration: TimeInterval = 0
    private let onMeter: @Sendable (TimeInterval, Double) -> Void

    public init(
        outputURL: URL,
        inputFormat: AVAudioFormat,
        onMeter: @escaping @Sendable (TimeInterval, Double) -> Void = { _, _ in }
    ) throws {
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0,
              let outputFormat = AVAudioFormat(
                  commonFormat: .pcmFormatInt16,
                  sampleRate: Self.sampleRate,
                  channels: Self.channelCount,
                  interleaved: true
              ),
              let converter = AVAudioConverter(from: inputFormat, to: outputFormat)
        else { throw WriterError.formatUnavailable }

        self.outputFormat = outputFormat
        self.converter = converter
        self.onMeter = onMeter
        file = try AVAudioFile(
            forWriting: outputURL,
            settings: outputFormat.settings,
            commonFormat: outputFormat.commonFormat,
            interleaved: outputFormat.isInterleaved
        )
    }

    public func append(_ input: AVAudioPCMBuffer) {
        lock.lock()
        defer { lock.unlock() }
        guard storedError == nil else { return }
        guard let file, let converter else {
            storedError = WriterError.alreadyFinished
            return
        }

        let ratio = outputFormat.sampleRate / input.format.sampleRate
        let capacity = AVAudioFrameCount(ceil(Double(input.frameLength) * ratio)) + 32
        guard let output = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
            storedError = WriterError.conversionFailed
            return
        }

        let provider = ConverterInput(input)
        var conversionError: NSError?
        let status = converter.convert(to: output, error: &conversionError) { _, status in
            provider.next(status)
        }
        guard status == .haveData || status == .inputRanDry else {
            storedError = conversionError ?? WriterError.conversionFailed
            return
        }
        guard output.frameLength > 0 else { return }
        do {
            try file.write(from: output)
            storedDuration += Double(output.frameLength) / outputFormat.sampleRate
            onMeter(storedDuration, Self.level(of: input))
        } catch {
            storedError = error
        }
    }

    @discardableResult
    public func finish() throws -> TimeInterval {
        lock.lock()
        defer { lock.unlock() }
        file = nil
        converter = nil
        if let storedError { throw storedError }
        return storedDuration
    }

    private static func level(of buffer: AVAudioPCMBuffer) -> Double {
        guard let channel = buffer.floatChannelData?[0], buffer.frameLength > 0 else { return 0 }
        var sum: Float = 0
        for index in 0..<Int(buffer.frameLength) { sum += channel[index] * channel[index] }
        let rms = sqrt(sum / Float(buffer.frameLength))
        let decibels = rms > 0 ? 20 * log10(rms) : -60
        return RecordingPolicy.normalizedLevel(decibels: decibels)
    }
}
