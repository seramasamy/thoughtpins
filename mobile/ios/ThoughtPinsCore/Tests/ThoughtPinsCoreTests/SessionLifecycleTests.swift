import Foundation
import XCTest
@testable import ThoughtPinsCore

/// The four states a session can be in, and what each must produce.
///
/// | session | network | expected                                    |
/// |---------|---------|---------------------------------------------|
/// | none    | any     | signed out                                  |
/// | valid   | online  | request succeeds                            |
/// | valid   | offline | session kept, transport error surfaces      |
/// | expired | online  | session cleared, sessionExpired thrown      |
///
/// The offline row is the one that matters: a transport failure must never be
/// mistaken for being signed out, or a person on a plane loses the app.
final class ThoughtPinsSessionLifecycleTests: XCTestCase {
    override func tearDown() {
        URLProtocolStub.handler = nil
        super.tearDown()
    }

    private func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return URLSession(configuration: configuration)
    }

    private func client(_ store: TestSessionStore) -> ThoughtPinsAPIClient {
        ThoughtPinsAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            sessionStore: store,
            urlSession: makeSession()
        )
    }

    // MARK: none / any

    func testNoSessionIsSignedOutAndNeverRefreshes() async throws {
        let store = TestSessionStore()
        var refreshAttempts = 0
        URLProtocolStub.handler = { request in
            if request.url?.path.contains("refresh") == true { refreshAttempts += 1 }
            return try StubResponse.make(for: request, status: 401, body: ["error": ["message": "no"]])
        }

        do {
            _ = try await client(store).me()
            XCTFail("expected a failure")
        } catch {
            // A 401 with nothing stored is just a 401; there is nothing to expire.
            XCTAssertNotEqual(error as? APIClientError, .sessionExpired)
        }
        XCTAssertNil(try store.load())
        XCTAssertEqual(refreshAttempts, 0, "must not try to refresh a session it does not have")
    }

    // MARK: valid / online

    func testValidSessionOnlineSucceedsAndIsKept() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "access", refreshToken: "refresh"))
        URLProtocolStub.handler = { request in
            try StubResponse.make(for: request, status: 200, body: [
                "id": "u1", "email": "a@b.c", "is_admin": false, "auth_method": "password",
            ])
        }

        let me = try await client(store).me()

        XCTAssertEqual(me.id, "u1")
        XCTAssertEqual(try store.load()?.accessToken, "access", "a good session must survive a good call")
    }

    // MARK: valid / offline

    func testValidSessionOfflineKeepsTheSession() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "access", refreshToken: "refresh"))
        URLProtocolStub.handler = { _ in
            throw URLError(.notConnectedToInternet)
        }

        do {
            _ = try await client(store).me()
            XCTFail("expected a transport failure")
        } catch {
            // Being offline is not being signed out. This is the row that
            // decides whether the app opens on a plane.
            XCTAssertNotEqual(error as? APIClientError, .sessionExpired)
            XCTAssertEqual(ThoughtPinsAuthFailure(error), .unreachable)
        }
        XCTAssertEqual(try store.load()?.refreshToken, "refresh", "offline must never clear the session")
    }

    // MARK: expired / online

    func testExpiredSessionIsClearedSoItCannotBecomeAFailingShell() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "stale", refreshToken: "stale-refresh"))
        URLProtocolStub.handler = { request in
            // Everything is unauthorised, including the refresh itself.
            try StubResponse.make(for: request, status: 401, body: ["error": ["message": "expired"]])
        }

        do {
            _ = try await client(store).me()
            XCTFail("expected sessionExpired")
        } catch {
            XCTAssertEqual(error as? APIClientError, .sessionExpired)
        }
        XCTAssertNil(try store.load(), "a rejected session must be cleared, not left to fail every call")
    }

    func testAServerFailureDuringRefreshKeepsTheSession() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "access", refreshToken: "refresh"))
        URLProtocolStub.handler = { request in
            if request.url?.path.contains("refresh") == true {
                return try StubResponse.make(for: request, status: 503, body: ["error": ["message": "later"]])
            }
            return try StubResponse.make(for: request, status: 401, body: ["error": ["message": "no"]])
        }

        do {
            _ = try await client(store).me()
            XCTFail("expected a failure")
        } catch {
            XCTAssertNotEqual(error as? APIClientError, .sessionExpired)
        }
        // A 5xx is transient. Signing someone out over it would be wrong.
        XCTAssertEqual(try store.load()?.refreshToken, "refresh")
    }

    // MARK: the refresh race

    func testAConcurrentRefreshStoresTheNewTokenBeforeAnyWaiterRetries() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "old", refreshToken: "old-refresh"))
        let seenAuthorization = SeenHeaders()
        URLProtocolStub.handler = { request in
            if request.url?.path.contains("refresh") == true {
                return try StubResponse.make(for: request, status: 200, body: [
                    "access_token": "fresh", "refresh_token": "fresh-refresh",
                    "token_type": "bearer", "expires_in": 3600,
                ])
            }
            let header = request.value(forHTTPHeaderField: "Authorization") ?? ""
            seenAuthorization.record(header)
            // The first call from each caller carries the old token and 401s;
            // the retry must carry the refreshed one.
            if header.contains("old") {
                return try StubResponse.make(for: request, status: 401, body: ["error": ["message": "stale"]])
            }
            return try StubResponse.make(for: request, status: 200, body: [
                "id": "u1", "email": "a@b.c", "is_admin": false, "auth_method": "password",
            ])
        }

        let client = self.client(store)
        async let first = client.me()
        async let second = client.me()
        async let third = client.me()
        _ = try await (first, second, third)

        XCTAssertFalse(
            seenAuthorization.retriesUsedAStaleToken,
            "a waiter retried with the pre-refresh token, which cannot recover"
        )
        XCTAssertEqual(try store.load()?.accessToken, "fresh")
    }
}

/// Records Authorization headers across the URLProtocol callbacks.
private final class SeenHeaders: @unchecked Sendable {
    private let lock = NSLock()
    private var headers: [String] = []

    func record(_ header: String) {
        lock.lock(); defer { lock.unlock() }
        headers.append(header)
    }

    /// Every caller may send one stale request; more than that means a retry
    /// went out with the old token after the refresh had already completed.
    var retriesUsedAStaleToken: Bool {
        lock.lock(); defer { lock.unlock() }
        return headers.filter { $0.contains("old") }.count > 3
    }
}
