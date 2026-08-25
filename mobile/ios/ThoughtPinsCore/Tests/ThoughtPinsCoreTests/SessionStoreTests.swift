import Foundation
import XCTest
@testable import ThoughtPinsCore

/// A session blob we cannot read must not lock someone out of the app.
final class ThoughtPinsSessionStoreTests: XCTestCase {
    /// Stands in for the Keychain, which answers an unsigned test bundle with
    /// errSecMissingEntitlement and so cannot be used here.
    private final class FakeBlobStore: SessionBlobStore, @unchecked Sendable {
        var stored: Data?
        var readError: Error?
        var writeError: Error?
        private(set) var writes: [Data?] = []

        init(stored: Data? = nil) { self.stored = stored }

        func read() throws -> Data? {
            if let readError { throw readError }
            return stored
        }

        func write(_ data: Data?) throws {
            writes.append(data)
            if let writeError { throw writeError }
            stored = data
        }
    }

    func testAGoodSessionRoundTrips() throws {
        let blobs = FakeBlobStore()
        let store = KeychainSessionStore(blobs: blobs)
        let session = ApiSession(accessToken: "access", refreshToken: "refresh")

        try store.save(session)
        XCTAssertEqual(try store.load(), session)
    }

    func testNothingStoredReadsAsSignedOut() throws {
        XCTAssertNil(try KeychainSessionStore(blobs: FakeBlobStore()).load())
    }

    func testACorruptBlobReadsAsSignedOutInsteadOfThrowingForever() throws {
        let blobs = FakeBlobStore(stored: Data("this is not a session".utf8))
        let store = KeychainSessionStore(blobs: blobs)

        // Before this change the decode error was rethrown on every launch.
        XCTAssertNil(try store.load())
    }

    func testACorruptBlobIsClearedSoTheNextLaunchIsNotTheSameLaunch() throws {
        let blobs = FakeBlobStore(stored: Data("{\"accessToken\":".utf8))
        let store = KeychainSessionStore(blobs: blobs)

        XCTAssertNil(try store.load())

        XCTAssertEqual(blobs.writes, [nil], "the unreadable item must be cleared")
        XCTAssertNil(blobs.stored)
        // And the person can sign in again on top of it.
        let session = ApiSession(accessToken: "new", refreshToken: "new-refresh")
        try store.save(session)
        XCTAssertEqual(try store.load(), session)
    }

    /// The distinction that must not be lost.
    func testAKeychainFailureStillThrows() {
        let blobs = FakeBlobStore()
        blobs.readError = SessionStoreError.keychain(errSecInteractionNotAllowed)
        let store = KeychainSessionStore(blobs: blobs)

        XCTAssertThrowsError(try store.load()) { error in
            XCTAssertEqual(error as? SessionStoreError, .keychain(errSecInteractionNotAllowed))
        }
        XCTAssertTrue(blobs.writes.isEmpty, "a Keychain failure must not clear the session")
    }

    /// Healing is best effort: if the clear also fails, the person still lands
    /// on sign-in rather than behind an error they cannot get past.
    func testAFailedClearStillReportsSignedOut() throws {
        let blobs = FakeBlobStore(stored: Data("not a session".utf8))
        blobs.writeError = SessionStoreError.keychain(errSecInteractionNotAllowed)
        let store = KeychainSessionStore(blobs: blobs)

        XCTAssertNil(try store.load())
    }

    func testSavingNilClearsTheItem() throws {
        let blobs = FakeBlobStore(stored: Data("x".utf8))
        try KeychainSessionStore(blobs: blobs).save(nil)
        XCTAssertNil(blobs.stored)
    }
}
