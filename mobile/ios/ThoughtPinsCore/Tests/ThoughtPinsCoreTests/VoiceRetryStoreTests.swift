import XCTest

@testable import ThoughtPinsCore

/// The failure banner promised "Your draft remains on this device" while the
/// recorder had already deleted the only copy. This store is what makes that
/// sentence true; these tests are what keep it true.
final class VoiceRetryStoreTests: XCTestCase {
    private var directory: URL!
    private var store: VoiceRetryStore!

    override func setUp() {
        super.setUp()
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("voice-retry-tests-\(UUID().uuidString)", isDirectory: true)
        store = VoiceRetryStore(directory: directory)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: directory)
        super.tearDown()
    }

    func testAKeptRecordingSurvivesAndRoundTrips() async throws {
        let audio = Data("not really audio, but bytes are bytes".utf8)
        let url = try await store.keep(audio)
        let pending = try await store.pending()
        // Compare by filename: `keep` returns a URL under the temp dir as
        // given, while `pending` reads it back through the directory listing,
        // which resolves the /var -> /private/var symlink on macOS. Same file,
        // different string.
        XCTAssertEqual(pending.map(\.lastPathComponent), [url.lastPathComponent])
        XCTAssertEqual(try Data(contentsOf: url), audio, "the kept file must be the recording, byte for byte")
    }

    func testDiscardRemovesExactlyTheDeliveredRecording() async throws {
        let first = try await store.keep(Data("one".utf8))
        let second = try await store.keep(Data("two".utf8))
        await store.discard(first)
        let pending = try await store.pending()
        XCTAssertEqual(
            pending.map(\.lastPathComponent),
            [second.lastPathComponent],
            "discarding one recording must not touch another"
        )
    }

    func testTheQueueRefusesRatherThanSilentlyDropping() async throws {
        for index in 0..<VoiceRetryStore.queueLimit {
            _ = try await store.keep(Data("recording \(index)".utf8))
        }
        do {
            _ = try await store.keep(Data("one too many".utf8))
            XCTFail("a full queue must refuse, or old recordings get displaced silently")
        } catch VoiceRetryStore.StoreError.queueFull {
            // The caller shows an honest message instead.
        }
        let pending = try await store.pending()
        XCTAssertEqual(pending.count, VoiceRetryStore.queueLimit)
    }

    func testPurgeLeavesNothingForTheNextAccount() async throws {
        _ = try await store.keep(Data("private to the signed-out account".utf8))
        await store.purge()
        let pending = try await store.pending()
        XCTAssertTrue(pending.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.path))
    }

    func testAnEmptyStoreReportsEmptyRatherThanThrowing() async throws {
        let pending = try await store.pending()
        XCTAssertTrue(pending.isEmpty)
    }
}
