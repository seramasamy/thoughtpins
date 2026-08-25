import Foundation
import XCTest
@testable import ThoughtPinsCore

/// The draft file is keyed by device, not by account.
///
/// `syncQueuedDrafts` posts whatever it finds under whichever session is
/// current, so anything surviving sign-out or account deletion is journal text
/// belonging to one person that the next person to use the device uploads as
/// their own.
final class ThoughtPinsDraftStoreTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("thoughtpins-draft-tests-\(UUID().uuidString)", isDirectory: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    func testPurgeLeavesNothingForTheNextAccountToSync() async throws {
        let store = FileDraftStore(directory: directory)
        _ = try await store.enqueue(text: "A private note the first account never sent.")
        _ = try await store.enqueue(text: "A second unsent note.")
        let queued = try await store.list()
        XCTAssertEqual(queued.count, 2, "the drafts must exist before purge can be proven to remove them")

        try await store.purge()

        let remaining = try await store.list()
        XCTAssertTrue(remaining.isEmpty, "a signed-out account's drafts must not survive for the next session to upload")
    }

    func testPurgeOnAnEmptyStoreIsNotAnError() async throws {
        let store = FileDraftStore(directory: directory)

        // Sign-out runs on accounts that never drafted anything offline. If
        // this threw, the caller would surface a deletion failure for an
        // account that was in fact deleted.
        try await store.purge()

        let remaining = try await store.list()
        XCTAssertTrue(remaining.isEmpty)
    }

    func testTheStoreIsUsableAgainAfterPurge() async throws {
        let store = FileDraftStore(directory: directory)
        _ = try await store.enqueue(text: "First account note.")
        try await store.purge()

        // Purge removes the file; the next enqueue has to recreate it rather
        // than fail against a missing path.
        let draft = try await store.enqueue(text: "Second account note.")

        let remaining = try await store.list()
        XCTAssertEqual(remaining.map(\.text), ["Second account note."])
        XCTAssertEqual(draft.status, .queued)
    }
}

/// A store that cannot be read must not be able to stop someone capturing.
final class ThoughtPinsDraftStoreResilienceTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("draft-resilience-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private var storeFile: URL {
        directory.appendingPathComponent("thoughtpins-capture-drafts.json")
    }

    private func corruptFiles() throws -> [URL] {
        try FileManager.default
            .contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.contains("corrupt") }
    }

    func testACorruptStoreIsMovedAsideAndCaptureKeepsWorking() async throws {
        try Data("this is not json".utf8).write(to: storeFile)
        let store = FileDraftStore(directory: directory)

        // list() must not throw, or enqueue() -- which calls it first -- can
        // never run again.
        let listed = try await store.list()
        XCTAssertEqual(listed, [])

        let saved = try await store.enqueue(text: "a thought that must survive")
        XCTAssertEqual(saved.text, "a thought that must survive")
        let after = try await store.list()
        XCTAssertEqual(after.count, 1)
    }

    func testTheCorruptFileIsKeptRatherThanDeleted() async throws {
        let original = "this is not json, but it is someone's journal"
        try Data(original.utf8).write(to: storeFile)
        let store = FileDraftStore(directory: directory)

        _ = try await store.list()

        let quarantined = try corruptFiles()
        XCTAssertEqual(quarantined.count, 1, "the unreadable file must be kept, not deleted")
        XCTAssertEqual(try String(contentsOf: quarantined[0], encoding: .utf8), original)
    }

    func testAFullQueueRefusesRatherThanDiscardingTheOldest() async throws {
        let store = FileDraftStore(directory: directory)
        for index in 0..<FileDraftStore.queueLimit {
            _ = try await store.enqueue(text: "draft \(index)")
        }
        let full = try await store.list()
        XCTAssertEqual(full.count, FileDraftStore.queueLimit)

        do {
            _ = try await store.enqueue(text: "one too many")
            XCTFail("Expected the queue to refuse")
        } catch DraftStoreError.queueFull(let limit) {
            XCTAssertEqual(limit, FileDraftStore.queueLimit)
        }

        // The point of refusing: the oldest is still there.
        let drafts = try await store.list()
        XCTAssertEqual(drafts.count, FileDraftStore.queueLimit)
        XCTAssertEqual(drafts.first?.text, "draft 0")
        XCTAssertFalse(drafts.contains { $0.text == "one too many" })
    }

    func testUpdateKeepsCreationOrderInsteadOfMovingTheDraftToTheEnd() async throws {
        let store = FileDraftStore(directory: directory)
        let first = try await store.enqueue(text: "first")
        _ = try await store.enqueue(text: "second")
        _ = try await store.enqueue(text: "third")

        var retried = first
        retried.status = .failed
        retried.attemptCount = 1
        retried.updatedAtUtc = Date().addingTimeInterval(60)
        try await store.update(retried)

        let texts = try await store.list().map(\.text)
        XCTAssertEqual(texts, ["first", "second", "third"], "order must follow creation, not last touch")
    }

    func testSyncedDraftsDrainOnWrite() async throws {
        let store = FileDraftStore(directory: directory)
        let draft = try await store.enqueue(text: "sent")
        var done = draft
        done.status = .synced
        try await store.update(done)

        let remaining = try await store.list()
        XCTAssertEqual(remaining, [])
    }
}
