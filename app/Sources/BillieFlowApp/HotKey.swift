import AppKit
import BillieFlowCore
import Carbon
import Foundation

extension HotKey {
    init?(event: NSEvent) {
        var carbonModifiers: UInt32 = 0
        if event.modifierFlags.contains(.command) { carbonModifiers |= UInt32(cmdKey) }
        if event.modifierFlags.contains(.control) { carbonModifiers |= UInt32(controlKey) }
        if event.modifierFlags.contains(.option) { carbonModifiers |= UInt32(optionKey) }
        if event.modifierFlags.contains(.shift) { carbonModifiers |= UInt32(shiftKey) }
        self.init(keyCode: UInt32(event.keyCode), modifiers: carbonModifiers)
        guard hasRequiredModifier else { return nil }
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
    private var binding = HotKeyBinding()
    private var nextIdentifier: UInt32 = 1

    deinit {
        if let hotKeyRef { UnregisterEventHotKey(hotKeyRef) }
        if let handlerRef { RemoveEventHandler(handlerRef) }
    }

    func register(_ hotKey: HotKey) throws {
        var candidateBinding = binding
        do {
            try candidateBinding.rebind(to: hotKey) { [self] hotKey in
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
                nextIdentifier &+= 1
                if let previousRef { UnregisterEventHotKey(previousRef) }
            }
            binding = candidateBinding
        } catch HotKeyBindingError.invalidModifiers {
            throw RegistrationError.invalidModifiers
        }
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
