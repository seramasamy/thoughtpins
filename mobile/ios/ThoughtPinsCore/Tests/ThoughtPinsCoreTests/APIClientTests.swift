import Foundation
import XCTest
@testable import ThoughtPinsCore

final class ThoughtPinsAPIClientTests: XCTestCase {
    override func tearDown() {
        URLProtocolStub.handler = nil
        super.tearDown()
    }

    func testUploadsAllowTimeForExtractionAndDecodeTheBackgroundJob() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/uploads")
            XCTAssertEqual(request.timeoutInterval, 120)
            let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(request.bodyData)) as? [String: Any])
            XCTAssertEqual(payload["surface"] as? String, "ios")
            XCTAssertEqual(payload["destination"] as? String, "library")
            return try StubResponse.make(for: request, status: 200, body: [
                "status": "processed", "route_type": "library_upload", "filename": "fixture.txt",
                "media_kind": "document", "destination": "library", "extraction_status": "processed",
                "extracted_chars": 7, "attachment_saved": true,
                "document_id": "source-fixture", "job_id": "enrichment-fixture",
            ])
        }
        let client = ThoughtPinsAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            sessionStore: TestSessionStore(ApiSession(accessToken: "access", refreshToken: "refresh")),
            urlSession: makeSession()
        )
        let response = try await client.uploadFile(
            filename: "fixture.txt", contentBase64: Data("fixture".utf8).base64EncodedString(),
            mediaType: "text/plain", destination: "library"
        )
        XCTAssertEqual(response.documentId, "source-fixture")
        XCTAssertEqual(response.jobId, "enrichment-fixture")
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
            return try StubResponse.make(for: request, status: 200, body: [
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
            try StubResponse.make(for: request, status: 503, body: [
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
            try StubResponse.make(for: request, status: 400, body: [
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
            try StubResponse.make(for: request, status: 200, body: [
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
            return try StubResponse.make(for: request, status: 200, body: [
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

    /// The fourth model that used to carry a snake_case CodingKeys enum. The
    /// other three are covered by the two tests above and the OAuth test.
    func testIngestResponseDecodesThroughTheConversionStrategy() async throws {
        URLProtocolStub.handler = { request in
            let body = try XCTUnwrap(request.bodyData)
            let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(payload["user_importance"] as? Int, 4)
            XCTAssertEqual(payload["text"] as? String, "a note")
            XCTAssertNil(payload["userImportance"])
            return try StubResponse.make(for: request, status: 200, body: [
                "status": "queued",
                "entry_id": "entry-1",
                "job_id": "job-1",
                "user_importance": 4,
            ])
        }
        let client = ThoughtPinsAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            sessionStore: TestSessionStore(ApiSession(accessToken: "access", refreshToken: "refresh")),
            urlSession: makeSession()
        )

        let response = try await client.ingest(text: "a note", userImportance: 4)

        XCTAssertEqual(response.status, "queued")
        XCTAssertEqual(response.entryId, "entry-1")
        XCTAssertEqual(response.jobId, "job-1")
        XCTAssertEqual(response.userImportance, 4)
    }

}
