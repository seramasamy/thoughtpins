import Foundation

public actor FileDraftStore {
    /// How many unsynced drafts may wait on the device at once.
    ///
    /// Reaching this refuses new captures rather than discarding old ones; see
    /// `enqueue(text:)`.
    public static let queueLimit = 250

    private let fileURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(directory: URL) {
        self.fileURL = directory.appendingPathComponent("thoughtpins-capture-drafts.json")
        // Fractional seconds, because createdAtUtc is what orders the queue.
        // Plain .iso8601 truncates to whole seconds, so a draft still held in
        // memory and the same draft read back from disk described the same
        // instant at two different precisions -- and update() passing an
        // in-memory draft therefore sorted it after everything on disk. Several
        // captures inside one second also became indistinguishable.
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            try container.encode(ISO8601DateFormatter.thoughtPinsPrecise.string(from: date))
        }
        decoder.dateDecodingStrategy = .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            // Accept the older whole-second form too, so a store written before
            // this change is read rather than quarantined.
            if let date = ISO8601DateFormatter.thoughtPinsPrecise.date(from: text)
                ?? ISO8601DateFormatter.thoughtPinsWholeSecond.date(from: text) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: try decoder.singleValueContainer(),
                debugDescription: "Not an ISO-8601 date: \(text)"
            )
        }
    }

    public func list() throws -> [CaptureDraft] {
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return []
        }
        // A read failure is left to throw. The file is written with
        // .completeFileProtection, so it is genuinely unreadable while the
        // device is locked, and that is transient and worth surfacing.
        let data = try Data(contentsOf: fileURL)
        do {
            return try decoder.decode([CaptureDraft].self, from: data)
        } catch {
            // A file we cannot decode is permanent, and rethrowing wedged
            // capture completely: enqueue() calls list() first, so one bad write
            // meant the person could never save another thought, and purge()
            // only runs on sign-out. They would have had to sign out -- throwing
            // away the very drafts that were stuck -- or delete the app.
            //
            // Move it aside rather than delete it. This is the person's journal
            // text: we could not parse it, which is not the same as it being
            // worthless, and a support request can still recover it.
            try? quarantine()
            return []
        }
    }

    public func enqueue(text: String) throws -> CaptureDraft {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= 50_000 else {
            throw DraftStoreError.invalidText
        }
        var drafts = try list()
        // Refuse, rather than make room. write() used to end in .suffix(250),
        // which silently deleted the oldest drafts to fit the newest -- in an
        // app whose whole premise is not losing what you wrote, and with no
        // sign to the person that anything had gone. Nothing already captured is
        // discarded now; the caller is told the queue is full and the text it
        // was handed is still in front of the person who typed it.
        guard drafts.count < Self.queueLimit else {
            throw DraftStoreError.queueFull(limit: Self.queueLimit)
        }
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
        var drafts = try list()
        // Replace in place. Filtering the draft out and appending it moved it to
        // the end, so the stored order became last-touched rather than created,
        // and a retry could reorder the queue under itself.
        if let index = drafts.firstIndex(where: { $0.id == draft.id }) {
            drafts[index] = draft
        } else {
            drafts.append(draft)
        }
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

    /// Move an undecodable store aside so capture can continue without it.
    private func quarantine() throws {
        let stamp = ISO8601DateFormatter.thoughtPinsFileStamp.string(from: Date())
        let destination = fileURL
            .deletingLastPathComponent()
            .appendingPathComponent("thoughtpins-capture-drafts.corrupt-\(stamp).json")
        try FileManager.default.moveItem(at: fileURL, to: destination)
    }

    private func write(_ drafts: [CaptureDraft]) throws {
        // Synced drafts are the drain: once the server has them the device copy
        // is redundant. Ordering is by creation so it does not depend on the
        // order things happened to be retried in.
        //
        // The sort is made stable by carrying the current position as a
        // tiebreaker. Dates are stored as ISO-8601 without fractional seconds,
        // so several drafts captured in the same second compare equal, and
        // Swift's sort is not stable -- left alone it reordered drafts that were
        // written seconds apart, which is the ordering bug this was meant to fix.
        let pending = drafts
            .filter { $0.status != .synced }
            .enumerated()
            .sorted { ($0.element.createdAtUtc, $0.offset) < ($1.element.createdAtUtc, $1.offset) }
            .map(\.element)
        let data = try encoder.encode(pending)
        try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: fileURL, options: [.atomic, .completeFileProtection])
    }
}

private extension ISO8601DateFormatter {
    /// Sub-second precision, so createdAtUtc can order the queue.
    static let thoughtPinsPrecise: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    /// What `.iso8601` produced before, kept so old stores still decode.
    static let thoughtPinsWholeSecond: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    /// Sortable, and legal in a filename on every filesystem iOS uses.
    static let thoughtPinsFileStamp: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withYear, .withMonth, .withDay, .withTime]
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter
    }()
}

public enum DraftStoreError: Error, Equatable {
    case invalidText
    /// The device is holding as many unsynced drafts as it will keep.
    case queueFull(limit: Int)
}
