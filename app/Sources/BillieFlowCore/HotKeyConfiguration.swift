import Carbon
import Foundation

public struct HotKey: Codable, Equatable, Sendable {
    public let keyCode: UInt32
    public let modifiers: UInt32

    public init(keyCode: UInt32, modifiers: UInt32) {
        self.keyCode = keyCode
        self.modifiers = modifiers
    }

    public var hasRequiredModifier: Bool {
        modifiers & UInt32(cmdKey) != 0 || modifiers & UInt32(controlKey) != 0
    }

    public var displayName: String {
        var parts: [String] = []
        if modifiers & UInt32(controlKey) != 0 { parts.append("⌃") }
        if modifiers & UInt32(optionKey) != 0 { parts.append("⌥") }
        if modifiers & UInt32(shiftKey) != 0 { parts.append("⇧") }
        if modifiers & UInt32(cmdKey) != 0 { parts.append("⌘") }
        parts.append(Self.keyName(keyCode))
        return parts.joined()
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

public enum HotKeyBindingError: Error, Equatable, Sendable {
    case invalidModifiers
}

/// Transactional selection state: the previous binding remains authoritative
/// unless registering the candidate succeeds.
public struct HotKeyBinding: Sendable {
    public private(set) var current: HotKey?

    public init(current: HotKey? = nil) { self.current = current }

    @discardableResult
    public mutating func rebind(
        to candidate: HotKey,
        registration: (HotKey) throws -> Void
    ) throws -> Bool {
        guard candidate.hasRequiredModifier else { throw HotKeyBindingError.invalidModifiers }
        guard candidate != current else { return false }
        try registration(candidate)
        current = candidate
        return true
    }
}
