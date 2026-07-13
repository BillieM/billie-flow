import AppKit
import BillieFlowCore
import Combine
import Foundation
import ServiceManagement

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var state: FlowState
    @Published var style: CleanupStyle {
        didSet { defaults.set(style.rawValue, forKey: Keys.style) }
    }
    @Published private(set) var hotKey: HotKey?
    @Published private(set) var hotKeyError: String?
    @Published private(set) var workerHealth: WorkerHealth
    @Published private(set) var workerInstallStatus: WorkerRuntimeInstallStatus = .idle
    @Published var launchAtLogin: Bool {
        didSet {
            guard launchAtLogin != oldValue, !isUpdatingLogin else { return }
            updateLaunchAtLogin()
        }
    }

    private enum Keys {
        static let style = "cleanupStyle"
        static let hotKey = "recordHotKey"
    }

    private let defaults: UserDefaults
    private let recorder = AudioRecorder()
    private let worker: WorkerProcess
    private let workerExecutableURL: URL
    private let workerInstaller: WorkerRuntimeInstaller?
    private let globalHotKey = GlobalHotKey()
    private let hud = HUDPanelController()
    private var machine: FlowStateMachine
    private var pressHeld = false
    private var recordingStartTask: Task<Void, Never>?
    private var warmupTask: Task<Void, any Error>?
    private var processingTask: Task<Void, Never>?
    private var workerInstallTask: Task<Void, Never>?
    private var dismissalTask: Task<Void, Never>?
    private var maximumDurationTask: Task<Void, Never>?
    private var isUpdatingLogin = false

    init(
        defaults: UserDefaults = .standard,
        workerConfiguration: WorkerLaunchConfiguration? = nil,
        workerInstaller: WorkerRuntimeInstaller? = nil
    ) {
        self.defaults = defaults
        let storedStyle = SettingsPolicy.style(storedValue: defaults.string(forKey: Keys.style))
        style = storedStyle
        let loadedHotKey = Self.loadHotKey(defaults: defaults)
        hotKey = loadedHotKey
        launchAtLogin = SMAppService.mainApp.status == .enabled
        machine = FlowStateMachine(hasHotkey: loadedHotKey != nil)
        state = machine.state

        let configuration = workerConfiguration ?? Self.defaultWorkerConfiguration()
        workerExecutableURL = configuration.executableURL
        workerHealth = SettingsPolicy.workerHealth(
            executableExists: FileManager.default.isExecutableFile(atPath: configuration.executableURL.path)
        )
        worker = WorkerProcess(configuration: configuration)
        self.workerInstaller = workerInstaller ?? Self.defaultWorkerInstaller()
        let staleDirectory = RecordingStorage.directory()
        if FileManager.default.fileExists(atPath: staleDirectory.path) {
            _ = try? RecordingStorage.removeStaleWAVs(in: staleDirectory)
        }
        recorder.onMeter = { [weak self] elapsed, level in
            self?.hud.updateRecording(elapsed: elapsed, level: level)
        }
        globalHotKey.onPressed = { [weak self] in self?.hotKeyPressed() }
        globalHotKey.onReleased = { [weak self] in self?.hotKeyReleased() }
        if let hotKey {
            do {
                try globalHotKey.register(hotKey)
            } catch {
                self.hotKey = nil
                defaults.removeObject(forKey: Keys.hotKey)
                machine = FlowStateMachine(hasHotkey: false)
                state = machine.state
                hotKeyError = "Your saved shortcut is no longer available. Choose another with Command or Control."
            }
        }
    }

    func configureHotKey(_ newValue: HotKey) {
        do {
            try globalHotKey.register(newValue)
            let data = try JSONEncoder().encode(newValue)
            defaults.set(data, forKey: Keys.hotKey)
            hotKey = newValue
            hotKeyError = nil
            transition(.hotkeyConfigured)
        } catch {
            hotKeyError = "That shortcut could not be registered. Choose another with Command or Control."
        }
    }

    func cancelCurrent() {
        guard state.isBusy else { return }
        pressHeld = false
        recordingStartTask?.cancel()
        recordingStartTask = nil
        warmupTask?.cancel()
        warmupTask = nil
        processingTask?.cancel()
        processingTask = nil
        maximumDurationTask?.cancel()
        maximumDurationTask = nil
        recorder.cancel()
        transition(.cancel)
        workerHealth = SettingsPolicy.workerHealth(
            executableExists: FileManager.default.isExecutableFile(atPath: workerExecutableURL.path)
        )
        Task { await worker.cancel() }
    }

    func installWorker() {
        guard workerInstallTask == nil else { return }
        guard let workerInstaller else {
            workerInstallStatus = .failed("The app is missing its bundled setup files. Download Billie Flow again.")
            return
        }

        warmupTask = nil
        workerHealth = .connecting
        workerInstallStatus = .installing(.preparingPython)
        workerInstallTask = Task { [weak self, workerInstaller] in
            do {
                try await workerInstaller.install { [weak self] phase in
                    Task { @MainActor in
                        self?.workerInstallStatus = .installing(phase)
                    }
                }
                guard let self else { return }
                let installed = FileManager.default.isExecutableFile(atPath: workerExecutableURL.path)
                workerHealth = SettingsPolicy.workerHealth(executableExists: installed)
                workerInstallStatus = installed
                    ? .installed
                    : .failed("The local runtime could not be verified. Try installing it again.")
                workerInstallTask = nil
            } catch is CancellationError {
                guard let self else { return }
                workerHealth = SettingsPolicy.workerHealth(
                    executableExists: FileManager.default.isExecutableFile(atPath: workerExecutableURL.path)
                )
                workerInstallStatus = .cancelled
                workerInstallTask = nil
            } catch {
                guard let self else { return }
                workerHealth = .failed(error.localizedDescription)
                workerInstallStatus = .failed(error.localizedDescription)
                workerInstallTask = nil
            }
        }
    }

    func cancelWorkerInstallation() {
        guard workerInstallTask != nil else { return }
        workerInstallTask?.cancel()
        Task { [workerInstaller] in await workerInstaller?.cancel() }
    }

    func resetStatus() {
        guard state.requiresExplicitDismissal else { return }
        transition(.dismiss)
    }

    func quit() {
        pressHeld = false
        recordingStartTask?.cancel()
        warmupTask?.cancel()
        let taskOwningTemporaryAudio = processingTask
        taskOwningTemporaryAudio?.cancel()
        processingTask = nil
        workerInstallTask?.cancel()
        maximumDurationTask?.cancel()
        recorder.cancel()
        Task { [worker, workerInstaller] in
            await workerInstaller?.cancel()
            await worker.cancel()
            await taskOwningTemporaryAudio?.value
            NSApp.terminate(nil)
        }
    }

    private func hotKeyPressed() {
        guard !pressHeld, state.allowsRecordingStart else { return }
        guard !workerInstallStatus.isInstalling else {
            transition(.failed("Finish local setup before recording."))
            return
        }
        pressHeld = true
        hud.beginRecordingOnPointerScreen()
        startWarmupIfNeeded()
        recordingStartTask = Task { [weak self] in
            guard let self else { return }
            do {
                try await recorder.start()
                guard pressHeld, !Task.isCancelled else {
                    recorder.cancel()
                    return
                }
                transition(.recordingStarted)
                maximumDurationTask = Task { [weak self] in
                    try? await Task.sleep(for: .seconds(RecordingPolicy.maximumDuration))
                    guard !Task.isCancelled else { return }
                    self?.finishRecording()
                }
            } catch is CancellationError {
                recorder.cancel()
            } catch {
                pressHeld = false
                transition(.failed(error.localizedDescription))
            }
        }
    }

    private func hotKeyReleased() {
        guard pressHeld else { return }
        pressHeld = false
        finishRecording()
    }

    private func finishRecording() {
        guard state == .recording else {
            recordingStartTask?.cancel()
            return
        }
        pressHeld = false
        maximumDurationTask?.cancel()
        maximumDurationTask = nil
        do {
            let recording = try recorder.stop()
            guard RecordingPolicy.disposition(for: recording.duration) == .submit else {
                _ = recording.audio.deleteWithRetries()
                transition(.failed("Recording was too short."))
                return
            }
            transition(.recordingStopped)
            process(recording.audio)
        } catch {
            recorder.cancel()
            transition(.failed(error.localizedDescription))
        }
    }

    private func startWarmupIfNeeded() {
        guard warmupTask == nil else { return }
        workerHealth = .connecting
        warmupTask = Task { [worker] in
            do {
                try await worker.warmup { [weak self] phase in
                    Task { @MainActor in
                        guard let self else { return }
                        if self.workerHealth == .connecting { self.workerHealth = .ready }
                        if case .processing = self.state { self.transition(.phase(phase)) }
                    }
                }
                await MainActor.run { [weak self] in self?.workerHealth = .warm }
            } catch {
                await MainActor.run { [weak self] in self?.workerHealth = .failed(error.localizedDescription) }
                throw error
            }
        }
    }

    private func process(_ audio: TemporaryAudio) {
        let warmup = warmupTask
        let style = style
        processingTask = Task { [weak self, worker] in
            guard let self else { return }
            do {
                let result = try await audio.deletingAfter {
                    try await warmup?.value
                    return try await worker.process(
                        audioURL: audio.url,
                        style: style,
                        debug: false
                    ) { [weak self] phase in
                        Task { @MainActor in self?.transition(.phase(phase)) }
                    }
                }
                guard !Task.isCancelled else { return }
                switch ClipboardPolicy.decision(for: .success(result)) {
                case let .copy(text, _):
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(text, forType: .string)
                    transition(.completed(result))
                case .preserve:
                    transition(.failed("No speech was detected."))
                }
            } catch is CancellationError {
                // cancelCurrent already restored idle and killed the worker.
            } catch let error as WorkerErrorPayload {
                transition(.failed(error.message))
            } catch {
                warmupTask = nil
                transition(.failed(error.localizedDescription))
            }
        }
    }

    private func transition(_ event: FlowEvent) {
        state = machine.handle(event)
        hud.update(state: state, style: style)
        dismissalTask?.cancel()
        switch state {
        case .copied(warning: nil):
            scheduleDismiss(after: .seconds(1.5))
        default: break
        }
    }

    private func scheduleDismiss(after duration: Duration) {
        dismissalTask = Task { [weak self] in
            try? await Task.sleep(for: duration)
            guard !Task.isCancelled else { return }
            self?.transition(.dismiss)
        }
    }

    private func updateLaunchAtLogin() {
        do {
            if launchAtLogin {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
        } catch {
            isUpdatingLogin = true
            launchAtLogin = SMAppService.mainApp.status == .enabled
            isUpdatingLogin = false
            hotKeyError = "Launch at login could not be changed: \(error.localizedDescription)"
        }
    }

    private static func loadHotKey(defaults: UserDefaults) -> HotKey? {
        guard let data = defaults.data(forKey: Keys.hotKey) else { return nil }
        return try? JSONDecoder().decode(HotKey.self, from: data)
    }

    private static func defaultWorkerConfiguration() -> WorkerLaunchConfiguration {
        let environment = ProcessInfo.processInfo.environment
        if let path = environment["BILLIE_FLOW_WORKER_EXECUTABLE"] {
            let arguments = environment["BILLIE_FLOW_WORKER_ARGUMENTS"]?
                .split(separator: " ").map(String.init) ?? []
            return WorkerLaunchConfiguration(executableURL: URL(fileURLWithPath: path), arguments: arguments)
        }
        return (try? .installed()) ?? WorkerLaunchConfiguration(
            executableURL: FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/Billie Flow/runtime/.venv/bin/billie-flow-worker")
        )
    }

    private static func defaultWorkerInstaller() -> WorkerRuntimeInstaller? {
        guard let resourceURL = Bundle.main.resourceURL else { return nil }
        let bootstrap = resourceURL.appendingPathComponent("Bootstrap", isDirectory: true)
        let uv = bootstrap.appendingPathComponent("uv", isDirectory: false)
        let worker = bootstrap.appendingPathComponent("worker", isDirectory: true)
        let runtimeRoot = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Billie Flow/runtime", isDirectory: true)
        return WorkerRuntimeInstaller(configuration: WorkerRuntimeInstallConfiguration(
            uvURL: uv,
            workerSourceURL: worker,
            runtimeRootURL: runtimeRoot
        ))
    }
}
