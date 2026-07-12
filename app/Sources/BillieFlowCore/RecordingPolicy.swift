import Foundation
import CoreGraphics

public enum RecordingDisposition: Equatable, Sendable {
    case discardTooShort
    case submit
}

public enum RecordingPolicy {
    public static let minimumDuration: TimeInterval = 0.5
    public static let maximumDuration: TimeInterval = 5 * 60

    public static func disposition(for duration: TimeInterval) -> RecordingDisposition {
        duration < minimumDuration ? .discardTooShort : .submit
    }

    public static func normalizedLevel(decibels: Float) -> Double {
        Double(min(1, max(0, (decibels + 60) / 60)))
    }
}

public enum WorkerHealth: Equatable, Sendable {
    case executableMissing
    case executablePresent
    case connecting
    case ready
    case warm
    case failed(String)
}

public enum SettingsPolicy {
    public static let defaultStyle = CleanupStyle.lightCleanup

    public static func style(storedValue: String?) -> CleanupStyle {
        storedValue.flatMap(CleanupStyle.init(rawValue:)) ?? defaultStyle
    }

    public static func workerHealth(executableExists: Bool) -> WorkerHealth {
        executableExists ? .executablePresent : .executableMissing
    }
}

public enum ScreenSelection {
    public static func index(containing point: CGPoint, frames: [CGRect]) -> Int? {
        frames.firstIndex(where: { $0.contains(point) })
    }
}

public protocol StaleRecordingFileSystem: Sendable {
    func contentsOfDirectory(at URL: URL) throws -> [URL]
    func removeItem(at URL: URL) throws
}

extension FileManager: StaleRecordingFileSystem {
    public func contentsOfDirectory(at URL: URL) throws -> [URL] {
        try contentsOfDirectory(at: URL, includingPropertiesForKeys: nil)
    }
}

public enum RecordingStorage {
    public static func directory(fileManager: FileManager = .default) -> URL {
        fileManager.temporaryDirectory.appendingPathComponent("Billie Flow", isDirectory: true)
    }

    @discardableResult
    public static func removeStaleWAVs(
        in directory: URL,
        fileSystem: any StaleRecordingFileSystem = FileManager.default
    ) throws -> Int {
        var removed = 0
        for url in try fileSystem.contentsOfDirectory(at: directory) where url.pathExtension.lowercased() == "wav" {
            try fileSystem.removeItem(at: url)
            removed += 1
        }
        return removed
    }
}
