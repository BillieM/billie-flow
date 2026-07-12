import Foundation

public enum CleanupStyle: String, Codable, CaseIterable, Sendable {
    case verbatimContextCorrected = "verbatim-context-corrected"
    case lightCleanup = "light-cleanup"
    case message

    public var displayName: String {
        switch self {
        case .verbatimContextCorrected: "Verbatim"
        case .lightCleanup: "Light cleanup"
        case .message: "Message"
        }
    }
}

public enum WorkerPhase: String, Codable, CaseIterable, Sendable {
    case loadingASR = "loading_asr"
    case transcribing
    case loadingCleanup = "loading_cleanup"
    case cleaning
    case correcting
}

public struct Correction: Codable, Equatable, Sendable {
    public let from: String
    public let to: String
    public let count: Int

    public init(from: String, to: String, count: Int) {
        self.from = from
        self.to = to
        self.count = count
    }
}

public struct WorkerTimings: Codable, Equatable, Sendable {
    public let loadingASRSeconds: Double
    public let asrSeconds: Double
    public let loadingCleanupSeconds: Double
    public let cleanupSeconds: Double
    public let correctionSeconds: Double
    public let totalSeconds: Double

    enum CodingKeys: String, CodingKey {
        case loadingASRSeconds = "loading_asr_seconds"
        case asrSeconds = "asr_seconds"
        case loadingCleanupSeconds = "loading_cleanup_seconds"
        case cleanupSeconds = "cleanup_seconds"
        case correctionSeconds = "correction_seconds"
        case totalSeconds = "total_seconds"
    }

    public init(
        loadingASRSeconds: Double,
        asrSeconds: Double,
        loadingCleanupSeconds: Double,
        cleanupSeconds: Double,
        correctionSeconds: Double,
        totalSeconds: Double
    ) {
        self.loadingASRSeconds = loadingASRSeconds
        self.asrSeconds = asrSeconds
        self.loadingCleanupSeconds = loadingCleanupSeconds
        self.cleanupSeconds = cleanupSeconds
        self.correctionSeconds = correctionSeconds
        self.totalSeconds = totalSeconds
    }
}

public struct ReadyPayload: Codable, Equatable, Sendable {
    public let workerVersion: String
    public let asrModel: String
    public let cleanupModel: String
    public let language: String
    public let correctionsVersion: String

    enum CodingKeys: String, CodingKey {
        case workerVersion = "worker_version"
        case asrModel = "asr_model"
        case cleanupModel = "cleanup_model"
        case language
        case correctionsVersion = "corrections_version"
    }
}

public struct ProcessResult: Codable, Equatable, Sendable {
    public let kind: String
    public let rawASR: String
    public let rawCleanup: String?
    public let finalText: String
    public let corrections: [Correction]
    public let timings: WorkerTimings
    public let asrModel: String
    public let cleanupModel: String
    public let style: CleanupStyle
    public let warning: String?

    enum CodingKeys: String, CodingKey {
        case kind
        case rawASR = "raw_asr"
        case rawCleanup = "raw_cleanup"
        case finalText = "final_text"
        case corrections, timings
        case asrModel = "asr_model"
        case cleanupModel = "cleanup_model"
        case style, warning
    }

    public init(
        kind: String = "process",
        rawASR: String,
        rawCleanup: String?,
        finalText: String,
        corrections: [Correction],
        timings: WorkerTimings,
        asrModel: String,
        cleanupModel: String,
        style: CleanupStyle,
        warning: String?
    ) {
        self.kind = kind
        self.rawASR = rawASR
        self.rawCleanup = rawCleanup
        self.finalText = finalText
        self.corrections = corrections
        self.timings = timings
        self.asrModel = asrModel
        self.cleanupModel = cleanupModel
        self.style = style
        self.warning = warning
    }

    public var usedRawASRFallback: Bool {
        warning == WorkerProtocol.cleanupFallbackWarning && rawCleanup == nil && finalText == rawASR
    }
}

public struct WorkerErrorPayload: Codable, Equatable, Error, Sendable {
    public let code: WorkerErrorCode
    public let message: String
    public let recoverable: Bool

    public init(code: WorkerErrorCode, message: String, recoverable: Bool) {
        self.code = code
        self.message = message
        self.recoverable = recoverable
    }
}

public enum WorkerErrorCode: String, Codable, Sendable {
    case invalidRequest = "invalid_request"
    case protocolMismatch = "protocol_mismatch"
    case notReady = "not_ready"
    case audioInvalid = "audio_invalid"
    case asrFailed = "asr_failed"
    case emptyTranscript = "empty_transcript"
    case internalError = "internal_error"
}

public enum WorkerTerminal: Equatable, Sendable {
    case ready(ReadyPayload)
    case warmup
    case process(ProcessResult)
    case shutdown
}

public enum WorkerEvent: Equatable, Sendable {
    case phase(requestID: String, WorkerPhase)
    case terminal(requestID: String, WorkerTerminal)
    case failure(requestID: String, WorkerErrorPayload)
}

public enum WorkerProtocolError: Error, Equatable, Sendable {
    case malformedLine
    case unsupportedVersion(Int)
    case unknownEvent(String)
    case invalidPayload(String)
    case invalidModel(String)
    case invalidWarning
}

public enum WorkerProtocol {
    public static let version = 1
    public static let asrModel = "mlx-community/whisper-large-v3-turbo"
    public static let cleanupModel = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
    public static let cleanupFallbackWarning = "cleanup_failed_raw_asr"

    public static func hello(id: String, clientVersion: String = "0.1.0") throws -> Data {
        try command(id: id, command: "hello", payload: [
            "client_name": "Billie Flow",
            "client_version": clientVersion,
        ])
    }

    public static func warmup(id: String) throws -> Data {
        try command(id: id, command: "warmup", payload: [:])
    }

    public static func process(id: String, audioPath: String, style: CleanupStyle, debug: Bool) throws -> Data {
        try command(id: id, command: "process", payload: [
            "audio_path": audioPath,
            "style": style.rawValue,
            "debug": debug,
        ])
    }

    public static func shutdown(id: String) throws -> Data {
        try command(id: id, command: "shutdown", payload: [:])
    }

    private static func command(id: String, command: String, payload: [String: Any]) throws -> Data {
        guard !id.isEmpty, id.utf8.count <= 128 else { throw WorkerProtocolError.invalidPayload("id") }
        let object: [String: Any] = [
            "protocol_version": version,
            "id": id,
            "command": command,
            "payload": payload,
        ]
        var data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        data.append(0x0A)
        return data
    }

    public static func decode(line: Data) throws -> WorkerEvent {
        guard
            let object = try JSONSerialization.jsonObject(with: line) as? [String: Any],
            Set(object.keys) == ["protocol_version", "request_id", "event", "payload"],
            let version = object["protocol_version"] as? Int,
            let requestID = object["request_id"] as? String,
            !requestID.isEmpty, requestID.utf8.count <= 128,
            let event = object["event"] as? String,
            let payload = object["payload"] as? [String: Any]
        else { throw WorkerProtocolError.malformedLine }
        guard version == self.version else { throw WorkerProtocolError.unsupportedVersion(version) }

        let payloadData = try JSONSerialization.data(withJSONObject: payload)
        let decoder = JSONDecoder()
        switch event {
        case "ready":
            try requireKeys(payload, ["worker_version", "asr_model", "cleanup_model", "language", "corrections_version"])
            let ready = try decoder.decode(ReadyPayload.self, from: payloadData)
            guard ready.asrModel == asrModel, ready.cleanupModel == cleanupModel,
                  ready.language == "en", ready.correctionsVersion == "1"
            else { throw WorkerProtocolError.invalidModel(ready.asrModel) }
            return .terminal(requestID: requestID, .ready(ready))
        case "phase":
            try requireKeys(payload, ["phase"])
            guard let raw = payload["phase"] as? String, let phase = WorkerPhase(rawValue: raw) else {
                throw WorkerProtocolError.invalidPayload("phase")
            }
            return .phase(requestID: requestID, phase)
        case "result":
            guard let kind = payload["kind"] as? String else { throw WorkerProtocolError.invalidPayload("kind") }
            switch kind {
            case "warmup":
                try requireKeys(payload, ["kind", "warmed"])
                guard payload["warmed"] as? Bool == true else { throw WorkerProtocolError.invalidPayload("warmed") }
                return .terminal(requestID: requestID, .warmup)
            case "shutdown":
                try requireKeys(payload, ["kind"])
                return .terminal(requestID: requestID, .shutdown)
            case "process":
                try requireKeys(payload, ["kind", "raw_asr", "raw_cleanup", "final_text", "corrections", "timings", "asr_model", "cleanup_model", "style", "warning"])
                let result = try decoder.decode(ProcessResult.self, from: payloadData)
                try validate(result)
                return .terminal(requestID: requestID, .process(result))
            default:
                throw WorkerProtocolError.invalidPayload("kind")
            }
        case "error":
            try requireKeys(payload, ["code", "message", "recoverable"])
            return .failure(requestID: requestID, try decoder.decode(WorkerErrorPayload.self, from: payloadData))
        default:
            throw WorkerProtocolError.unknownEvent(event)
        }
    }

    private static func requireKeys(_ object: [String: Any], _ keys: Set<String>) throws {
        guard Set(object.keys) == keys else { throw WorkerProtocolError.invalidPayload("unknown_or_missing_field") }
    }

    private static func validate(_ result: ProcessResult) throws {
        guard result.kind == "process", !result.rawASR.isEmpty, !result.finalText.isEmpty else {
            throw WorkerProtocolError.invalidPayload("process")
        }
        guard result.asrModel == asrModel, result.cleanupModel == cleanupModel else {
            throw WorkerProtocolError.invalidModel(result.asrModel)
        }
        let values = [
            result.timings.loadingASRSeconds, result.timings.asrSeconds,
            result.timings.loadingCleanupSeconds, result.timings.cleanupSeconds,
            result.timings.correctionSeconds, result.timings.totalSeconds,
        ]
        guard values.allSatisfy({ $0 >= 0 && $0.isFinite }),
              result.corrections.allSatisfy({ !$0.from.isEmpty && !$0.to.isEmpty && $0.count >= 1 })
        else { throw WorkerProtocolError.invalidPayload("process_values") }
        if let warning = result.warning {
            guard warning == cleanupFallbackWarning, result.usedRawASRFallback, result.corrections.isEmpty else {
                throw WorkerProtocolError.invalidWarning
            }
        }
    }
}
