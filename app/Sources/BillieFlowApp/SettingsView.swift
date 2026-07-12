import AppKit
import BillieFlowCore
import SwiftUI

struct SettingsView: View {
    @ObservedObject var model: AppModel

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
                if model.workerHealth == .executableMissing {
                    Text("Install the local runtime from the repository in Terminal:")
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Text("scripts/bootstrap_worker.sh").font(.system(.caption, design: .monospaced))
                        Spacer()
                        Button("Copy") {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString("scripts/bootstrap_worker.sh", forType: .string)
                        }
                    }
                }
            }
        }
        .formStyle(.grouped)
        .padding()
        .frame(width: 470, height: 500)
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
