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
