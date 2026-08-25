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
            let body = try XCTUnwrap(request.bodyData)
            let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(payload["authorization_code"] as? String, "one-time-code")
            XCTAssertEqual(payload["id_token"] as? String, "identity-token")
            return try Self.response(for: request, status: 200, body: [
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
            try Self.response(for: request, status: 503, body: [
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
            try Self.response(for: request, status: 400, body: [
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

    // The client's decoder sets .convertFromSnakeCase, so a model must NOT also
    // declare snake_case CodingKeys: the strategy rewrites "app_name" to
    // "appName" and then looks for a key spelled "appName", which an explicit
    // `case appName = "app_name"` does not provide. Four models used to carry
    // such enums, which made every one of them undecodable. These two tests
    // pin both directions of that boundary.
    func testSnakeCasedResponseFieldsDecodeThroughTheConversionStrategy() async throws {
        URLProtocolStub.handler = { request in
            try Self.response(for: request, status: 200, body: [
                "app_name": "Thought Pins",
                "api_version": "v1",
                "auth_required": true,
                "registration_locked": false,
                "oauth_google_enabled": true,
                "privacy_policy_url": "https://example.com/privacy",
                "minimum_supported_clients": ["ios": "1.0.0"],
                "recommended_clients": ["ios": "1.2.0"],
                "store_urls": ["ios": "https://example.com/app"],
                "maintenance_mode": false,
                "maintenance_allow_reads": true,
            ])
        }
        let client = ThoughtPinsAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            sessionStore: TestSessionStore(),
            urlSession: makeSession()
        )

        let config = try await client.clientConfig()

        XCTAssertEqual(config.appName, "Thought Pins")
        XCTAssertEqual(config.apiVersion, "v1")
        XCTAssertTrue(config.authRequired)
        XCTAssertFalse(config.registrationLocked)
        XCTAssertEqual(config.oauthGoogleEnabled, true)
        XCTAssertEqual(config.privacyPolicyUrl, "https://example.com/privacy")
        XCTAssertEqual(config.minimumSupportedClients["ios"], "1.0.0")
        XCTAssertTrue(config.maintenanceAllowReads)
    }

    func testDeviceRegistrationIsPostedWithSnakeCasedKeys() async throws {
        URLProtocolStub.handler = { request in
            let body = try XCTUnwrap(request.bodyData)
            let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(payload["installation_id"] as? String, "install-1")
            XCTAssertEqual(payload["app_version"] as? String, "1.0.0")
            XCTAssertEqual(payload["notifications_enabled"] as? Bool, true)
            XCTAssertNil(payload["installationId"])
            return try Self.response(for: request, status: 200, body: [
                "id": "device-1",
                "installation_id": "install-1",
                "platform": "ios",
                "push_token_present": false,
                "notifications_enabled": true,
            ])
        }
        let client = ThoughtPinsAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            sessionStore: TestSessionStore(ApiSession(accessToken: "access", refreshToken: "refresh")),
            urlSession: makeSession()
        )

        let device = try await client.registerDevice(
            DeviceRegistration(
                installationId: "install-1",
                deviceName: "iPhone",
                appVersion: "1.0.0",
                buildNumber: "42",
                osVersion: "17.2",
                locale: "en_US",
                timezone: "America/New_York",
                pushProvider: nil,
                pushToken: nil,
                notificationsEnabled: true
            )
        )

        XCTAssertEqual(device.installationId, "install-1")
        XCTAssertFalse(device.pushTokenPresent)
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

private extension URLRequest {
    /// The request body as URLProtocol actually receives it.
    ///
    /// URLSession converts httpBody into httpBodyStream before handing the
    /// request to a protocol, so reading httpBody here always returns nil and
    /// the assertion about the posted payload could never have passed.
    var bodyData: Data? {
        if let httpBody { return httpBody }
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let capacity = 4096
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: capacity)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let read = stream.read(buffer, maxLength: capacity)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }
}
