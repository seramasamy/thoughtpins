import Foundation

/// Voice recordings whose upload failed, kept on this device until they reach
/// the server.
///
/// `FileDraftStore` is the text sibling. Before this store existed, the upload
/// failure banner said "Your draft remains on this device" while the recorder
/// had already deleted the only copy in a `defer` — the audio was gone and the
/// message was a lie. Now the bytes are written here first, with the same
/// `.completeFileProtection` policy the text drafts use, and the app retries
/// them on the next launch sync.
public actor VoiceRetryStore {
    /// How many unsent recordings may wait on the device at once.
    ///
    /// Voice notes are megabytes each, not bytes, so this is far lower than
    /// the text queue's 250. Reaching it refuses the new recording rather
    /// than silently discarding an old one; the caller must say so honestly.
    public static let queueLimit = 25

    public enum StoreError: Error {
        case queueFull
    }

    private let directory: URL

    public init(directory: URL) {
        self.directory = directory
    }

    /// Persist a failed upload's audio. Returns the file it now lives in.
    public func keep(_ data: Data) throws -> URL {
        if try pending().count >= Self.queueLimit {
            throw StoreError.queueFull
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        // The filename carries a zero-padded capture timestamp so `pending()`
        // can order the queue by name alone. Reading each file's creation date
        // instead would pull in the file-timestamp required-reason API and a
        // privacy-manifest declaration, for information the filename can hold.
        let stamp = String(format: "%016.0f", Date().timeIntervalSince1970 * 1000)
        let url = directory.appendingPathComponent("voice-\(stamp)-\(UUID().uuidString).m4a")
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        return url
    }

    /// Recordings still waiting, oldest first so retries preserve capture order.
    ///
    /// Ordered by the timestamp prefix in the filename, which sorts
    /// chronologically because it is fixed-width and zero-padded.
    public func pending() throws -> [URL] {
        guard FileManager.default.fileExists(atPath: directory.path) else { return [] }
        let contents = try FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )
        return contents
            .filter { $0.pathExtension == "m4a" }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    /// The recording reached the server (or its account is gone); drop it.
    public func discard(_ url: URL) {
        try? FileManager.default.removeItem(at: url)
    }

    /// Sign-out and account deletion call this: recordings queued for one
    /// account must never upload into the next account on this device.
    public func purge() {
        try? FileManager.default.removeItem(at: directory)
    }
}
