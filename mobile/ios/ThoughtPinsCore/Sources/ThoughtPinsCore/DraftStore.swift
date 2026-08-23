import Foundation

public actor FileDraftStore {
    private let fileURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(directory: URL) {
        self.fileURL = directory.appendingPathComponent("thoughtpins-capture-drafts.json")
        encoder.dateEncodingStrategy = .iso8601
        decoder.dateDecodingStrategy = .iso8601
    }

    public func list() throws -> [CaptureDraft] {
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return []
        }
        return try decoder.decode([CaptureDraft].self, from: Data(contentsOf: fileURL))
    }

    public func enqueue(text: String) throws -> CaptureDraft {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= 50_000 else {
            throw DraftStoreError.invalidText
        }
        var drafts = try list()
        let now = Date()
        let draft = CaptureDraft(
            id: UUID().uuidString,
            text: trimmed,
            status: .queued,
            createdAtUtc: now,
            updatedAtUtc: now,
            attemptCount: 0
        )
        drafts.append(draft)
        try write(drafts)
        return draft
    }

    public func update(_ draft: CaptureDraft) throws {
        var drafts = try list().filter { $0.id != draft.id }
        drafts.append(draft)
        try write(drafts)
    }

    /// Deletes every stored draft.
    ///
    /// The store is keyed by device, not by account, and `syncQueuedDrafts`
    /// uploads whatever it finds under whichever session is current. Sign-out
    /// and account deletion both call this, because a draft left behind is raw
    /// journal text that the next account to bootstrap on this device would
    /// post as its own.
    public func purge() throws {
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return
        }
        try FileManager.default.removeItem(at: fileURL)
    }

    private func write(_ drafts: [CaptureDraft]) throws {
        let data = try encoder.encode(drafts.filter { $0.status != .synced }.suffix(250))
        try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: fileURL, options: [.atomic, .completeFileProtection])
    }
}

public enum DraftStoreError: Error, Equatable {
    case invalidText
}
