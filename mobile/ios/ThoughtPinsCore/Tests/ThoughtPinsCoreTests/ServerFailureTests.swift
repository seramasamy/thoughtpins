import Foundation
import XCTest
@testable import ThoughtPinsCore

/// What the client does when the server misbehaves. The rule under test is
/// that nothing is reported as success that was not, and every failure carries
/// something true for the app to show.
final class ThoughtPinsServerFailureTests: XCTestCase {
    override func tearDown() {
        URLProtocolStub.handler = nil
        super.tearDown()
    }

    private func client(_ store: TestSessionStore = TestSessionStore(ApiSession(accessToken: "a", refreshToken: "r"))) -> ThoughtPinsAPIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return ThoughtPinsAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            sessionStore: store,
            urlSession: URLSession(configuration: configuration)
        )
    }

    func testRateLimitSurfacesTheServersOwnExplanation() async throws {
        URLProtocolStub.handler = { request in
            try StubResponse.make(for: request, status: 429, body: [
                "error": ["code": "rate_limited", "message": "Too many requests. Try again in a minute."]
            ])
        }
        do {
            _ = try await client().me()
            XCTFail("a 429 must not read as success")
        } catch APIClientError.httpStatus(let status, let message) {
            XCTAssertEqual(status, 429)
            XCTAssertEqual(message, "Too many requests. Try again in a minute.")
        }
    }

    func testServerErrorSurfacesAsAServerFailureNotAsSignedOut() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "a", refreshToken: "r"))
        URLProtocolStub.handler = { request in
            try StubResponse.make(for: request, status: 500, body: [
                "error": ["code": "internal", "message": "Something went wrong."]
            ])
        }
        do {
            _ = try await client(store).me()
            XCTFail("a 500 must not read as success")
        } catch APIClientError.httpStatus(let status, _) {
            XCTAssertEqual(status, 500)
            XCTAssertEqual(ThoughtPinsAuthFailure(APIClientError.httpStatus(status, nil)), .serverUnavailable)
        }
        XCTAssertNotNil(try store.load(), "a server fault must not sign anyone out")
    }

    func testATimeoutIsReportedAsATimeoutRatherThanHangingForever() async throws {
        URLProtocolStub.handler = { _ in throw URLError(.timedOut) }
        do {
            _ = try await client().me()
            XCTFail("expected a timeout")
        } catch {
            XCTAssertEqual(ThoughtPinsAuthFailure(error), .timedOut)
        }
    }

    /// The sanitiser exists so a server can never push arbitrary detail into
    /// the UI. Worth pinning, because these messages are shown verbatim.
    func testOnlyTheEnvelopeMessageReachesTheApp() async throws {
        URLProtocolStub.handler = { request in
            try StubResponse.make(for: request, status: 400, body: [
                "error": [
                    "code": "bad_request",
                    "message": "That link could not be read.",
                    "details": ["internal_trace": "do-not-show-this"],
                ]
            ])
        }
        do {
            _ = try await client().me()
            XCTFail("expected a failure")
        } catch APIClientError.httpStatus(_, let message) {
            XCTAssertEqual(message, "That link could not be read.")
            XCTAssertFalse(message?.contains("do-not-show-this") ?? true)
        }
    }

    func testAnEmptyBodyDoesNotInventAMessage() async throws {
        URLProtocolStub.handler = { request in
            let response = try XCTUnwrap(HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 503,
                httpVersion: "HTTP/1.1", headerFields: nil
            ))
            return (response, Data())
        }
        do {
            _ = try await client().me()
            XCTFail("expected a failure")
        } catch APIClientError.httpStatus(let status, let message) {
            XCTAssertEqual(status, 503)
            XCTAssertNil(message, "no body means no message; do not fabricate one")
        }
    }
}
