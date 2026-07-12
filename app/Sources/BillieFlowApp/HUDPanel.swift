import AppKit
import BillieFlowCore
import SwiftUI

@MainActor
final class HUDPanelController {
    private let panel: NSPanel
    private let host = NSHostingView(rootView: HUDView(state: .idle, style: .lightCleanup, elapsed: 0, level: 0))
    private var pinnedScreen: NSScreen?
    private var state: FlowState = .idle
    private var style: CleanupStyle = .lightCleanup
    private var elapsed: TimeInterval = 0
    private var level: Double = 0

    init() {
        panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 290, height: 72),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: true
        )
        panel.level = .floating
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]

        let glass = NSGlassEffectView(frame: panel.contentView?.bounds ?? .zero)
        glass.autoresizingMask = [.width, .height]
        glass.cornerRadius = 24
        glass.style = .regular
        host.frame = glass.bounds
        host.autoresizingMask = [.width, .height]
        glass.contentView = host
        panel.contentView = glass
    }

    func update(state: FlowState, style: CleanupStyle) {
        self.state = state
        self.style = style
        render()
        switch state {
        case .recording, .processing, .copied, .failed:
            position()
            panel.orderFrontRegardless()
        case .idle, .needsHotkey:
            panel.orderOut(nil)
        }
    }

    func beginRecordingOnPointerScreen() {
        let location = NSEvent.mouseLocation
        pinnedScreen = ScreenSelection.index(containing: location, frames: NSScreen.screens.map(\.frame))
            .map { NSScreen.screens[$0] }
        elapsed = 0
        level = 0
    }

    func updateRecording(elapsed: TimeInterval, level: Double) {
        self.elapsed = elapsed
        self.level = level
        render()
    }

    private func render() {
        host.rootView = HUDView(state: state, style: style, elapsed: elapsed, level: level)
    }

    private func position() {
        guard let frame = (pinnedScreen ?? NSScreen.main)?.visibleFrame else { return }
        let x = frame.midX - panel.frame.width / 2
        panel.setFrameOrigin(NSPoint(x: x, y: frame.minY + 52))
    }
}

private struct HUDView: View {
    let state: FlowState
    let style: CleanupStyle
    let elapsed: TimeInterval
    let level: Double

    var body: some View {
        HStack(spacing: 12) {
            if state == .recording {
                HStack(alignment: .center, spacing: 2) {
                    ForEach(0..<5) { index in
                        Capsule().frame(width: 3, height: CGFloat(7 + (level * Double(index + 2) * 3).clamped(to: 0...20)))
                    }
                }
                .frame(width: 24)
            } else {
                Image(systemName: icon).font(.system(size: 20, weight: .semibold))
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                Text(subtitle).font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 20)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var icon: String {
        switch state {
        case .recording: "waveform"
        case .processing: "ellipsis"
        case .copied: "doc.on.clipboard"
        case .failed: "exclamationmark.triangle"
        default: "mic"
        }
    }

    private var title: String {
        switch state {
        case .recording: "Recording"
        case let .processing(phase): phase.map(phaseTitle) ?? "Preparing"
        case .copied(nil): "Copied"
        case .copied: "Copied raw transcript"
        case .failed: "Couldn’t transcribe"
        default: "Billie Flow"
        }
    }

    private var subtitle: String {
        switch state {
        case .recording: "\(Self.time(elapsed)) · release to finish"
        case .processing: style.displayName
        case .copied(nil): "Ready on the clipboard"
        case .copied: "Cleanup failed — ASR copied"
        case let .failed(message): message
        default: style.displayName
        }
    }

    private static func time(_ interval: TimeInterval) -> String {
        let seconds = max(0, Int(interval))
        return String(format: "%d:%02d", seconds / 60, seconds % 60)
    }

    private func phaseTitle(_ phase: WorkerPhase) -> String {
        switch phase {
        case .loadingASR: "Loading speech model"
        case .transcribing: "Transcribing"
        case .loadingCleanup: "Loading cleanup model"
        case .cleaning: "Cleaning up"
        case .correcting: "Correcting vocabulary"
        }
    }
}

private extension Double {
    func clamped(to range: ClosedRange<Double>) -> Double { min(range.upperBound, max(range.lowerBound, self)) }
}
