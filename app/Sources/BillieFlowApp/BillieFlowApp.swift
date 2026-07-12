import BillieFlowCore
import AppKit
import SwiftUI

@main
struct BillieFlowApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var model = AppModel()

    var body: some Scene {
        MenuBarExtra("Billie Flow", systemImage: menuIcon) {
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

@MainActor
private final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        guard UserDefaults.standard.data(forKey: "recordHotKey") == nil else { return }
        DispatchQueue.main.async {
            NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        }
    }
}
