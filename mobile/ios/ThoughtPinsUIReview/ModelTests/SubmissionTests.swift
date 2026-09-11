import Foundation
import XCTest
import ThoughtPinsApp
import ThoughtPinsCore

final class SubmissionTests: XCTestCase {
    private let base = URL(string: "http://127.0.0.1:8877")!
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws { try FileManager.default.removeItem(at: directory) }

    private func configure(failures: [String: [Int]] = [:], delays: [String: Int] = [:]) async throws {
        var request = URLRequest(url: base.appendingPathComponent("__review"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["failures": failures, "delays": delays])
        let (_, response) = try await URLSession.shared.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
    }

    private func count(_ key: String) async throws -> Int {
        let (data, _) = try await URLSession.shared.data(from: base.appendingPathComponent("__review"))
        let result = try JSONSerialization.jsonObject(with: data) as! [String: [String: Int]]
        return result["calls"]?[key] ?? 0
    }

    @MainActor func testFailedLocalPersistenceDoesNotClaimTheNoteWasSaved() async throws {
        try await configure(failures: ["POST /v1/entries": [503]])
        let file = directory.appendingPathComponent("blocked")
        try Data().write(to: file)
        let model = ThoughtPinsAppModel(baseURL: base, sessionStore: ReviewSessionStore(), draftDirectory: file)
        await model.bootstrap()
        let accepted = await model.saveJournal("Fictional note that must remain editable.")
        XCTAssertFalse(accepted)
        XCTAssertTrue(model.bannerIsProblem)
        XCTAssertTrue(model.banner?.contains("Keep a copy") == true)
        XCTAssertFalse(model.savingJournal)
        let retry = await model.saveJournal("Fictional note that must remain editable.")
        XCTAssertTrue(retry)
    }

    @MainActor func testOfflineAcceptanceRequiresAPersistedDraft() async throws {
        try await configure(failures: ["POST /v1/entries": [503]])
        let model = ThoughtPinsAppModel(baseURL: base, sessionStore: ReviewSessionStore(), draftDirectory: directory)
        await model.bootstrap()
        let accepted = await model.saveJournal("A fictional queued moment.")
        XCTAssertTrue(accepted)
        let queued = try await FileDraftStore(directory: directory.appendingPathComponent("ThoughtPins")).list()
        XCTAssertEqual(queued.map(\.text), ["A fictional queued moment."])
        XCTAssertEqual(model.draftCount, 1)
    }

    @MainActor func testOverlappingJournalAndLoginRequestsAreRejected() async throws {
        try await configure(delays: ["POST /v1/entries": 500, "POST /v1/auth/login": 500])
        let model = ThoughtPinsAppModel(baseURL: base, sessionStore: ReviewSessionStore(), draftDirectory: directory)
        await model.bootstrap()
        let first = Task { await model.saveJournal("A fictional note.") }
        for _ in 0..<100 where !model.savingJournal { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertTrue(model.savingJournal)
        let duplicate = await model.saveJournal("A fictional note.")
        XCTAssertFalse(duplicate)
        let saved = await first.value
        XCTAssertTrue(saved)
        let saves = try await count("POST /v1/entries")
        XCTAssertEqual(saves, 1)
        let login = Task { await model.login(identifier: "review@example.com", password: "fictional password") }
        for _ in 0..<100 where !model.authBusy { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertTrue(model.authBusy)
        await model.login(identifier: "review@example.com", password: "fictional password")
        await login.value
        let logins = try await count("POST /v1/auth/login")
        XCTAssertEqual(logins, 1)
        XCTAssertFalse(model.authBusy)
    }

    @MainActor func testInvalidInputAndFailedLinksRemainUnaccepted() async throws {
        try await configure(failures: ["POST /v1/library": [503]])
        let model = ThoughtPinsAppModel(baseURL: base, sessionStore: ReviewSessionStore(), draftDirectory: directory)
        await model.bootstrap()
        let blank = await model.saveJournal(" \n ")
        let invalid = await model.ingestLink("javascript:alert(1)")
        await model.login(identifier: "   ", password: "fictional password")
        XCTAssertFalse(blank)
        XCTAssertFalse(invalid)
        let saves = try await count("POST /v1/entries")
        let logins = try await count("POST /v1/auth/login")
        XCTAssertEqual(saves, 0)
        XCTAssertEqual(logins, 0)
        let failed = await model.ingestLink("https://example.com/fictional")
        XCTAssertFalse(failed)
        XCTAssertFalse(model.importingLink)
        let retry = await model.ingestLink("  https://example.com/fictional  ")
        XCTAssertTrue(retry)
    }
}

private final class ReviewSessionStore: SessionStore, @unchecked Sendable {
    private let lock = NSLock()
    private var session: ApiSession?
    func load() throws -> ApiSession? { lock.lock(); defer { lock.unlock() }; return session }
    func save(_ value: ApiSession?) throws { lock.lock(); defer { lock.unlock() }; session = value }
}
