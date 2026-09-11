import Foundation
import XCTest
@testable import ThoughtPinsCore

final class SessionBoundaryTests: XCTestCase {
    override func tearDown() {
        URLProtocolStub.handler = nil
        super.tearDown()
    }

    func testRefreshCannotRestoreASignedOutAccount() async throws {
        try await checkRefreshBoundary(replacement: nil, status: 200)
    }

    func testRefreshCannotOverwriteAnotherAccount() async throws {
        try await checkRefreshBoundary(replacement: otherAccount, status: 200)
    }

    func testRejectedRefreshCannotClearAnotherAccount() async throws {
        try await checkRefreshBoundary(replacement: otherAccount, status: 401)
    }

    func testLogoutCannotClearALaterLogin() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "old", refreshToken: "old-refresh"))
        let next = otherAccount
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/auth/logout")
            XCTAssertNil(try store.load(), "Local sign-out happens before the network wait")
            try store.save(next)
            return try StubResponse.make(for: request, status: 200, body: ["status": "ok"])
        }
        try await makeClient(store).logout()
        XCTAssertEqual(try store.load(), next)
    }

    func testLogoutStillRevokesRemotelyWhenKeychainRefusesToClear() async throws {
        let store = RefusingClearSessionStore()
        var revoked = false
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/auth/logout")
            revoked = true
            return try StubResponse.make(for: request, status: 200, body: ["status": "ok"])
        }
        do {
            try await makeClient(store).logout()
            XCTFail("The local persistence failure must be visible")
        } catch {
            XCTAssertEqual(error as? SessionStoreError, .keychain(-1))
        }
        XCTAssertTrue(revoked)
    }

    private func makeClient(_ store: any SessionStore) -> ThoughtPinsAPIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return ThoughtPinsAPIClient(baseURL: URL(string: "https://api.example.com")!,
            sessionStore: store, urlSession: URLSession(configuration: configuration))
    }

    private var otherAccount: ApiSession {
        ApiSession(accessToken: "other-account", refreshToken: "other-refresh")
    }

    private func checkRefreshBoundary(replacement: ApiSession?, status: Int) async throws {
        let store = TestSessionStore(ApiSession(accessToken: "old", refreshToken: "old-refresh"))
        let client = makeClient(store)
        URLProtocolStub.handler = { request in
            if request.url?.path == "/v1/auth/refresh" {
                // A sign-out or another login completes while renewal is in flight.
                try store.save(replacement)
                return try StubResponse.make(for: request, status: status, body: status == 200 ? [
                    "access_token": "renewed-old", "refresh_token": "renewed-old-refresh",
                    "token_type": "bearer", "expires_in": 3600,
                ] : ["error": ["message": "Rejected old session"]])
            }
            if request.value(forHTTPHeaderField: "Authorization") == "Bearer old" {
                return try StubResponse.make(for: request, status: 401, body: ["error": ["message": "Expired"]])
            }
            return try StubResponse.make(for: request, status: 200, body: [
                "id": "old-user", "email": "review@example.com", "is_admin": false, "auth_method": "password",
            ])
        }
        do {
            _ = try await client.me()
            XCTFail("A request from a replaced session must be cancelled")
        } catch {
            XCTAssertTrue(error is CancellationError, "A superseded request must not sign out the current user")
        }
        XCTAssertEqual(try store.load(), replacement)
    }
}

private final class RefusingClearSessionStore: SessionStore {
    func load() throws -> ApiSession? { ApiSession(accessToken: "old", refreshToken: "old-refresh") }
    func save(_ session: ApiSession?) throws { throw SessionStoreError.keychain(-1) }
}
