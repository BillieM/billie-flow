import AppKit
import BillieFlowCore
import SwiftUI

struct SettingsView: View {
    @ObservedObject var model: AppModel
    @State private var showingInstallConsent = false

    var body: some View {
        Form {
            Section("Record shortcut") {
                HotKeyRecorder(value: model.hotKey, onChange: model.configureHotKey)
                    .frame(height: 34)
                Text("Hold the shortcut to record, then release it to transcribe. Command or Control is required.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let error = model.hotKeyError {
                    Text(error).font(.caption).foregroundStyle(.red)
                }
            }

            Section("Cleanup") {
                Picker("Style", selection: $model.style) {
                    ForEach(CleanupStyle.allCases, id: \.self) { style in
                        Text(style.displayName).tag(style)
                    }
                }
                Text(styleDescription).font(.caption).foregroundStyle(.secondary)
            }

            Section("General") {
                Toggle("Launch Billie Flow at login", isOn: $model.launchAtLogin)
                Text("Recordings are temporary and are deleted after every success, failure, cancellation, and quit. Billie Flow keeps no transcript history.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Local worker") {
                LabeledContent("Status", value: healthText)
                workerSetupControls
            }
        }
        .alert("Install local speech models?", isPresented: $showingInstallConsent) {
            Button("Cancel", role: .cancel) {}
            Button("Install") { model.installWorker() }
        } message: {
            Text("Billie Flow will download about 3.5 GB, including fixed models from Hugging Face. English speech and inference stay local. Setup requires Apple Silicon and macOS 26.")
        }
        .formStyle(.grouped)
        .padding()
        .frame(width: 470, height: 500)
    }

    @ViewBuilder
    private var workerSetupControls: some View {
        switch model.workerInstallStatus {
        case let .installing(phase):
            HStack(spacing: 10) {
                ProgressView().controlSize(.small)
                Text(phaseText(phase))
            }
            Text("Keep Billie Flow open while setup finishes. Nothing is sent to a transcription service.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Button("Cancel setup", role: .destructive) { model.cancelWorkerInstallation() }
        case let .failed(message):
            Text(message).font(.caption).foregroundStyle(.red)
            Button("Retry installation…") { showingInstallConsent = true }
        case .cancelled:
            Text("Setup was cancelled. No recording can start until the local runtime is installed.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Button("Retry installation…") { showingInstallConsent = true }
        case .installed:
            Text("The fixed speech and cleanup models are installed locally.")
                .font(.caption)
                .foregroundStyle(.secondary)
        case .idle:
            switch model.workerHealth {
            case .executableMissing:
                Text("Setup downloads about 3.5 GB, including models from Hugging Face. English-only inference stays local. Requires Apple Silicon and macOS 26.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Install local models…") { showingInstallConsent = true }
            case .failed:
                Text("The local runtime could not start. Reinstalling keeps setup local and restores the fixed model environment.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Reinstall local models…") { showingInstallConsent = true }
            default:
                Text("The local runtime is installed. Models load on the first recording.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func phaseText(_ phase: WorkerRuntimeInstallPhase) -> String {
        switch phase {
        case .preparingPython: "Preparing Python"
        case .installingRuntime: "Installing local runtime"
        case .downloadingSpeechModel: "Downloading speech model"
        case .downloadingCleanupModel: "Downloading cleanup model"
        case .verifying: "Verifying setup"
        }
    }

    private var styleDescription: String {
        switch model.style {
        case .verbatimContextCorrected: "Preserves wording while correcting context and known vocabulary."
        case .lightCleanup: "Default. Removes small dictation rough edges without rewriting your voice."
        case .message: "Shapes speech into a concise, sendable message."
        }
    }

    private var healthText: String {
        switch model.workerHealth {
        case .executableMissing: "Missing"
        case .executablePresent: "Installed, not started"
        case .connecting: "Starting"
        case .ready: "Protocol ready"
        case .warm: "Models warm"
        case let .failed(message): "Error: \(message)"
        }
    }
}

private struct HotKeyRecorder: NSViewRepresentable {
    let value: HotKey?
    let onChange: (HotKey) -> Void

    func makeNSView(context: Context) -> RecorderView {
        let view = RecorderView()
        view.onChange = onChange
        view.value = value
        DispatchQueue.main.async { view.window?.makeFirstResponder(view) }
        return view
    }

    func updateNSView(_ view: RecorderView, context: Context) {
        view.onChange = onChange
        view.value = value
    }

    final class RecorderView: NSView {
        var onChange: ((HotKey) -> Void)?
        var value: HotKey? { didSet { needsDisplay = true } }
        override var acceptsFirstResponder: Bool { true }

        override func mouseDown(with event: NSEvent) {
            window?.makeFirstResponder(self)
        }

        override func keyDown(with event: NSEvent) {
            guard let hotKey = HotKey(event: event) else {
                NSSound.beep()
                return
            }
            onChange?(hotKey)
        }

        override func draw(_ dirtyRect: NSRect) {
            let bounds = bounds.insetBy(dx: 1, dy: 1)
            NSColor.controlBackgroundColor.setFill()
            NSBezierPath(roundedRect: bounds, xRadius: 7, yRadius: 7).fill()
            (window?.firstResponder === self ? NSColor.controlAccentColor : NSColor.separatorColor).setStroke()
            NSBezierPath(roundedRect: bounds, xRadius: 7, yRadius: 7).stroke()
            let text = value?.displayName ?? "Click, then press your shortcut"
            let attributes: [NSAttributedString.Key: Any] = [
                .font: NSFont.systemFont(ofSize: 13, weight: value == nil ? .regular : .medium),
                .foregroundColor: value == nil ? NSColor.secondaryLabelColor : NSColor.labelColor,
            ]
            let size = text.size(withAttributes: attributes)
            text.draw(
                at: NSPoint(x: bounds.midX - size.width / 2, y: bounds.midY - size.height / 2),
                withAttributes: attributes
            )
        }
    }
}
