import AppKit
import Carbon
import Foundation

struct HotKey: Codable, Equatable {
    let keyCode: UInt32
    let modifiers: UInt32

    var hasRequiredModifier: Bool {
        modifiers & UInt32(cmdKey) != 0 || modifiers & UInt32(controlKey) != 0
    }

    var displayName: String {
        var parts: [String] = []
        if modifiers & UInt32(controlKey) != 0 { parts.append("⌃") }
        if modifiers & UInt32(optionKey) != 0 { parts.append("⌥") }
        if modifiers & UInt32(shiftKey) != 0 { parts.append("⇧") }
        if modifiers & UInt32(cmdKey) != 0 { parts.append("⌘") }
        parts.append(Self.keyName(keyCode))
        return parts.joined()
    }

    init?(event: NSEvent) {
        var carbonModifiers: UInt32 = 0
        if event.modifierFlags.contains(.command) { carbonModifiers |= UInt32(cmdKey) }
        if event.modifierFlags.contains(.control) { carbonModifiers |= UInt32(controlKey) }
        if event.modifierFlags.contains(.option) { carbonModifiers |= UInt32(optionKey) }
        if event.modifierFlags.contains(.shift) { carbonModifiers |= UInt32(shiftKey) }
        self.init(keyCode: UInt32(event.keyCode), modifiers: carbonModifiers)
        guard hasRequiredModifier else { return nil }
    }

    init(keyCode: UInt32, modifiers: UInt32) {
        self.keyCode = keyCode
        self.modifiers = modifiers
    }

    private static func keyName(_ code: UInt32) -> String {
        let names: [UInt32: String] = [
            0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z", 7: "X",
            8: "C", 9: "V", 11: "B", 12: "Q", 13: "W", 14: "E", 15: "R",
            16: "Y", 17: "T", 31: "O", 32: "U", 34: "I", 35: "P", 37: "L",
            38: "J", 40: "K", 45: "N", 46: "M", 49: "Space", 36: "Return",
        ]
        return names[code] ?? "Key \(code)"
    }
}

@MainActor
final class GlobalHotKey {
    enum RegistrationError: Error {
        case invalidModifiers
        case handlerInstallationFailed(OSStatus)
        case registrationFailed(OSStatus)
    }

    var onPressed: (() -> Void)?
    var onReleased: (() -> Void)?
    nonisolated(unsafe) private var hotKeyRef: EventHotKeyRef?
    nonisolated(unsafe) private var handlerRef: EventHandlerRef?
    private var registeredHotKey: HotKey?
    private var nextIdentifier: UInt32 = 1

    deinit {
        if let hotKeyRef { UnregisterEventHotKey(hotKeyRef) }
        if let handlerRef { RemoveEventHandler(handlerRef) }
    }

    func register(_ hotKey: HotKey) throws {
        guard hotKey.hasRequiredModifier else { throw RegistrationError.invalidModifiers }
        guard hotKey != registeredHotKey else { return }
        try installHandlerIfNeeded()

        let identifier = EventHotKeyID(signature: OSType(0x42464C57), id: nextIdentifier) // BFLW
        var candidateRef: EventHotKeyRef?
        let status = RegisterEventHotKey(
            hotKey.keyCode,
            hotKey.modifiers,
            identifier,
            GetApplicationEventTarget(),
            0,
            &candidateRef
        )
        guard status == noErr, let candidateRef else {
            if let candidateRef { UnregisterEventHotKey(candidateRef) }
            throw RegistrationError.registrationFailed(status)
        }

        let previousRef = hotKeyRef
        hotKeyRef = candidateRef
        registeredHotKey = hotKey
        nextIdentifier &+= 1
        if let previousRef { UnregisterEventHotKey(previousRef) }
    }

    private func installHandlerIfNeeded() throws {
        guard handlerRef == nil else { return }
        var types = [
            EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed)),
            EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyReleased)),
        ]
        var candidateRef: EventHandlerRef?
        let status = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, context in
                guard let event, let context else { return OSStatus(eventNotHandledErr) }
                let owner = Unmanaged<GlobalHotKey>.fromOpaque(context).takeUnretainedValue()
                Task { @MainActor in
                    switch GetEventKind(event) {
                    case UInt32(kEventHotKeyPressed): owner.onPressed?()
                    case UInt32(kEventHotKeyReleased): owner.onReleased?()
                    default: break
                    }
                }
                return noErr
            },
            types.count,
            &types,
            Unmanaged.passUnretained(self).toOpaque(),
            &candidateRef
        )
        guard status == noErr, let candidateRef else {
            if let candidateRef { RemoveEventHandler(candidateRef) }
            throw RegistrationError.handlerInstallationFailed(status)
        }
        handlerRef = candidateRef
    }
}
