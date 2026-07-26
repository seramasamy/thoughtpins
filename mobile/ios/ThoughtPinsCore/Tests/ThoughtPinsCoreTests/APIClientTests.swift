import Foundation
import XCTest
@testable import ThoughtPinsCore

final class ThoughtPinsAPIClientTests: XCTestCase {
    override func tearDown() {
        URLProtocolStub.handler = nil
        super.tearDown()
    }

    func testOAuthCarriesAppleAuthorizationCodeWithoutCaching() async throws {
        let store = TestSessionStore()
        let session = makeSession()
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-store")
            let body = try XCTUnwrap(request.httpBody)
            let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(payload["authorization_code"] as? String, "one-time-code")
            XCTAssertEqual(payload["id_token"] as? String, "identity-token")
            return Self.response(for: request, status: 200, body: [
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "token_type": "bearer",
                "expires_in": 3600,
            ])
        }

        let client = ThoughtPinsAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            sessionStore: store,
            urlSession: session
        )
        _ = try await client.oauthLogin(
            provider: "apple",
            idToken: "identity-token",
            authorizationCode: "one-time-code"
        )

        XCTAssertEqual(try store.load()?.refreshToken, "new-refresh")
    }

    func testLogoutClearsLocalSessionWhenServerIsUnavailable() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "access", refreshToken: "refresh"))
        URLProtocolStub.handler = { request in
            Self.response(for: request, status: 503, body: [
                "error": ["code": "maintenance", "message": "Try again later", "request_id": "req-1"]
            ])
        }
        let client = ThoughtPinsAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            sessionStore: store,
            urlSession: makeSession()
        )

        do {
            try await client.logout()
            XCTFail("Expected logout to surface the server failure")
        } catch {
            XCTAssertNil(try store.load())
        }
    }

    func testErrorUsesEnvelopeMessageInsteadOfReturningTheRawBody() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "access", refreshToken: "refresh"))
        URLProtocolStub.handler = { request in
            Self.response(for: request, status: 400, body: [
                "error": [
                    "code": "bad_request",
                    "message": "Safe message",
                    "request_id": "req-2",
                    "details": ["secret": "must-not-escape"],
                ]
            ])
        }
        let client = ThoughtPinsAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            sessionStore: store,
            urlSession: makeSession()
        )

        do {
            _ = try await client.me()
            XCTFail("Expected an API error")
        } catch APIClientError.httpStatus(let status, let message) {
            XCTAssertEqual(status, 400)
            XCTAssertEqual(message, "Safe message")
            XCTAssertFalse(message?.contains("must-not-escape") ?? true)
        }
    }

    private func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return URLSession(configuration: configuration)
    }

    private static func response(
        for request: URLRequest,
        status: Int,
        body: [String: Any]
    ) throws -> (HTTPURLResponse, Data) {
        let response = try XCTUnwrap(
            HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: status,
                httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )
        )
        return (response, try JSONSerialization.data(withJSONObject: body))
    }
}

private final class TestSessionStore: SessionStore, @unchecked Sendable {
    private let lock = NSLock()
    private var value: ApiSession?

    init(_ value: ApiSession? = nil) {
        self.value = value
    }

    func load() throws -> ApiSession? {
        lock.lock()
        defer { lock.unlock() }
        return value
    }

    func save(_ session: ApiSession?) throws {
        lock.lock()
        defer { lock.unlock() }
        value = session
    }
}

private final class URLProtocolStub: URLProtocol {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
