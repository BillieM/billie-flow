import Foundation
import Testing
@testable import BillieFlowCore

@Suite("Worker protocol v1")
struct WorkerProtocolTests {
    @Test func helloUsesCurrentAppVersionWithoutChangingProtocolV1() throws {
        let data = try WorkerProtocol.hello(id: "hello-1")
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(object["protocol_version"] as? Int == 1)
        let payload = try #require(object["payload"] as? [String: Any])
        #expect(payload["client_version"] as? String == "0.2.1")
    }

    @Test func processCommandContainsFrozenV1Fields() throws {
        let data = try WorkerProtocol.process(
            id: "process-1", audioPath: "/tmp/recording.wav", style: .lightCleanup, debug: false
        )
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(object["protocol_version"] as? Int == 1)
        #expect(object["id"] as? String == "process-1")
        #expect(object["command"] as? String == "process")
        let payload = try #require(object["payload"] as? [String: Any])
        #expect(Set(payload.keys) == ["audio_path", "style", "debug"])
        #expect(payload["style"] as? String == "light-cleanup")
        #expect(payload["debug"] as? Bool == false)
        #expect(data.last == 0x0A)
    }

    @Test func allFiveFrozenPhasesDecode() throws {
        let names = ["loading_asr", "transcribing", "loading_cleanup", "cleaning", "correcting"]
        var decoded: [WorkerPhase] = []
        for name in names {
            let line = Data(#"{"protocol_version":1,"request_id":"p","event":"phase","payload":{"phase":"\#(name)"}}"#.utf8)
            guard case let .phase(_, phase) = try WorkerProtocol.decode(line: line) else {
                Issue.record("Expected phase")
                continue
            }
            decoded.append(phase)
        }
        #expect(decoded == WorkerPhase.allCases)
    }

    @Test func fullProcessResultDecodes() throws {
        let line = Data(#"{"protocol_version":1,"request_id":"process-1","event":"result","payload":{"kind":"process","raw_asr":"Billy Flow is ready.","raw_cleanup":"Billy Flow is ready.","final_text":"Billie Flow is ready.","corrections":[{"from":"Billy Flow","to":"Billie Flow","count":1}],"timings":{"loading_asr_seconds":0.0,"asr_seconds":1.2,"loading_cleanup_seconds":0.0,"cleanup_seconds":0.8,"correction_seconds":0.001,"total_seconds":2.001},"asr_model":"mlx-community/whisper-large-v3-turbo","cleanup_model":"mlx-community/Qwen2.5-1.5B-Instruct-4bit","style":"light-cleanup","warning":null}}"#.utf8)
        guard case let .terminal(requestID, .process(result)) = try WorkerProtocol.decode(line: line) else {
            Issue.record("Expected process result")
            return
        }
        #expect(requestID == "process-1")
        #expect(result.rawASR == "Billy Flow is ready.")
        #expect(result.rawCleanup == "Billy Flow is ready.")
        #expect(result.finalText == "Billie Flow is ready.")
        #expect(result.corrections == [Correction(from: "Billy Flow", to: "Billie Flow", count: 1)])
        #expect(result.timings.totalSeconds == 2.001)
        #expect(result.asrModel == WorkerProtocol.asrModel)
        #expect(result.cleanupModel == WorkerProtocol.cleanupModel)
        #expect(result.style == .lightCleanup)
        #expect(result.warning == nil)
    }

    @Test func rawASRFallbackIsAccepted() throws {
        let line = Data(#"{"protocol_version":1,"request_id":"process-2","event":"result","payload":{"kind":"process","raw_asr":"Raw speech.","raw_cleanup":null,"final_text":"Raw speech.","corrections":[],"timings":{"loading_asr_seconds":0,"asr_seconds":1,"loading_cleanup_seconds":0,"cleanup_seconds":0.1,"correction_seconds":0,"total_seconds":1.1},"asr_model":"mlx-community/whisper-large-v3-turbo","cleanup_model":"mlx-community/Qwen2.5-1.5B-Instruct-4bit","style":"message","warning":"cleanup_failed_raw_asr"}}"#.utf8)
        guard case let .terminal(_, .process(result)) = try WorkerProtocol.decode(line: line) else {
            Issue.record("Expected process result")
            return
        }
        #expect(result.usedRawASRFallback)
        #expect(ClipboardPolicy.decision(for: .success(result)) == .copy("Raw speech.", warning: "cleanup_failed_raw_asr"))
    }

    @Test func malformedFallbackAndUnknownFieldsAreRejected() {
        let invalidFallback = Data(#"{"protocol_version":1,"request_id":"p","event":"result","payload":{"kind":"process","raw_asr":"Raw","raw_cleanup":null,"final_text":"Changed","corrections":[],"timings":{"loading_asr_seconds":0,"asr_seconds":1,"loading_cleanup_seconds":0,"cleanup_seconds":0,"correction_seconds":0,"total_seconds":1},"asr_model":"mlx-community/whisper-large-v3-turbo","cleanup_model":"mlx-community/Qwen2.5-1.5B-Instruct-4bit","style":"message","warning":"cleanup_failed_raw_asr"}}"#.utf8)
        #expect(throws: (any Error).self) { try WorkerProtocol.decode(line: invalidFallback) }

        let unknownField = Data(#"{"protocol_version":1,"request_id":"p","event":"phase","payload":{"phase":"cleaning","extra":true}}"#.utf8)
        #expect(throws: (any Error).self) { try WorkerProtocol.decode(line: unknownField) }

        let longID = String(repeating: "x", count: 129)
        let oversizedRequestID = Data(#"{"protocol_version":1,"request_id":"\#(longID)","event":"phase","payload":{"phase":"cleaning"}}"#.utf8)
        #expect(throws: (any Error).self) { try WorkerProtocol.decode(line: oversizedRequestID) }
    }

    @Test func errorDecodesAndPreservesClipboard() throws {
        let line = Data(#"{"protocol_version":1,"request_id":"p","event":"error","payload":{"code":"empty_transcript","message":"No speech was detected.","recoverable":true}}"#.utf8)
        guard case let .failure(_, error) = try WorkerProtocol.decode(line: line) else {
            Issue.record("Expected failure")
            return
        }
        #expect(error.code == .emptyTranscript)
        let result: Result<ProcessResult, any Error> = .failure(error)
        #expect(ClipboardPolicy.decision(for: result) == .preserve)
    }
}
