import BillieFlowCore
import AppKit
import SwiftUI

@main
struct BillieFlowApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        MenuBarExtra {
            if let hotKey = model.hotKey {
                Text("Hold \(hotKey.displayName) to record")
            } else {
                Text("Choose a record shortcut to begin")
            }

            Picker("Style", selection: $model.style) {
                ForEach(CleanupStyle.allCases, id: \.self) { style in
                    Text(style.displayName).tag(style)
                }
            }

            if model.state.isBusy {
                Button("Cancel", role: .destructive) { model.cancelCurrent() }
            }

            if model.state.requiresExplicitDismissal {
                Button("Dismiss Warning") { model.resetStatus() }
            }

            Divider()
            SettingsLink { Text(model.hotKey == nil ? "Set Up…" : "Settings…") }
            Button("Quit Billie Flow") { model.quit() }
        } label: {
            MenuBarLabel(
                systemImage: menuIcon,
                opensSettingsOnLaunch: model.hotKey == nil || model.workerHealth == .executableMissing
            )
        }

        Settings {
            SettingsView(model: model)
        }
    }

    private var menuIcon: String {
        switch model.state {
        case .recording: "waveform.circle.fill"
        case .processing: "ellipsis.circle"
        case .copied: "checkmark.circle"
        case .failed: "exclamationmark.circle"
        default: "waveform.circle"
        }
    }
}

private struct MenuBarLabel: View {
    @Environment(\.openSettings) private var openSettings
    @State private var openedSettingsOnLaunch = false

    let systemImage: String
    let opensSettingsOnLaunch: Bool

    var body: some View {
        Image(systemName: systemImage)
            .accessibilityLabel("Billie Flow")
            .task {
                guard opensSettingsOnLaunch, !openedSettingsOnLaunch else { return }
                openedSettingsOnLaunch = true
                await Task.yield()
                await MainActor.run {
                    NSApp.activate(ignoringOtherApps: true)
                    openSettings()
                }
            }
    }
}
