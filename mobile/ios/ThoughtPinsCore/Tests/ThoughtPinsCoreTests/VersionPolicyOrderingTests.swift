import XCTest

@testable import ThoughtPinsCore

/// Version ordering, and the day-one nag it nearly caused.
///
/// The fixture below is production's actual `/v1/client-config` response,
/// captured 2026-08-26, rather than a hand-written one -- a hand-written
/// fixture is exactly where a decoding assumption hides.
final class VersionPolicyOrderingTests: XCTestCase {
    private static let liveConfigJSON = """
{
  "app_name": "Thought Pins",
  "api_version": "1.0.0-rc.1",
  "environment": "production",
  "auth_required": true,
  "registration_locked": false,
  "oauth_google_enabled": true,
  "oauth_apple_enabled": false,
  "oauth_google_client_id": "575558925583-caitcd8mght6ei1kp5vptl2bff3co6tg.apps.googleusercontent.com",
  "oauth_apple_client_id": null,
  "magic_link_enabled": true,
  "invite_required": false,
  "invite_request_email": "invite@thoughtpins.com",
  "voice_archive_enabled": false,
  "ai_processing": "configured",
  "memory_context_mode": "smart",
  "privacy_policy_url": "https://thoughtpins.com/privacy",
  "terms_url": "https://thoughtpins.com/terms",
  "support_url": "https://thoughtpins.com/support",
  "account_deletion_url": "https://thoughtpins.com/account/delete",
  "ai_disclosure_url": "https://thoughtpins.com/ai-disclosure",
  "legal_document_version": "2026-07-13",
  "minimum_supported_clients": {
    "ios": "0.0.0",
    "android": "0.0.0",
    "web": "0.0.0"
  },
  "recommended_clients": {
    "ios": "1.0.0-rc.1",
    "android": "1.0.0-rc.1",
    "web": "1.0.0-rc.1"
  },
  "store_urls": {
    "ios": null,
    "android": null,
    "web": "https://thoughtpins.com/app"
  },
  "maintenance_mode": false,
  "maintenance_message": null,
  "maintenance_retry_after_seconds": null,
  "maintenance_allow_reads": true
}
"""

    private func liveConfig(minimum: String? = nil, recommended: String? = nil, storeURL: String? = nil) throws -> ClientConfig {
        var object = try JSONSerialization.jsonObject(with: Data(Self.liveConfigJSON.utf8)) as! [String: Any]
        if let minimum { object["minimum_supported_clients"] = ["ios": minimum, "android": minimum, "web": minimum] }
        if let recommended { object["recommended_clients"] = ["ios": recommended, "android": recommended, "web": recommended] }
        if let storeURL { object["store_urls"] = ["ios": storeURL, "android": NSNull(), "web": NSNull()] }
        let data = try JSONSerialization.data(withJSONObject: object)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(ClientConfig.self, from: data)
    }

    func testAPreReleaseSortsBelowItsRelease() {
        // The defect: "1.0.0-rc.1" parsed as [1,0,0,1] and so compared *greater*
        // than "1.0.0". Production advertises exactly that string as the
        // recommended iOS version, so the shipping build would have been told
        // to update to a version that does not exist.
        XCTAssertEqual(compareVersions("1.0.0", "1.0.0-rc.1"), 1)
        XCTAssertEqual(compareVersions("1.0.0-rc.1", "1.0.0"), -1)
        XCTAssertEqual(compareVersions("1.0.0-rc.1", "1.0.0-rc.1"), 0)
    }

    func testOrdinaryOrderingIsUnchanged() {
        XCTAssertEqual(compareVersions("1.0.0", "1.0.0"), 0)
        XCTAssertEqual(compareVersions("1.0.1", "1.0.0"), 1)
        XCTAssertEqual(compareVersions("1.0.0", "1.0.1"), -1)
        XCTAssertEqual(compareVersions("2.0.0", "1.9.9"), 1)
        XCTAssertEqual(compareVersions("1.2", "1.2.0"), 0, "a missing patch is zero")
        XCTAssertEqual(compareVersions("1.10.0", "1.9.0"), 1, "components are numbers, not text")
    }

    func testBuildMetadataDoesNotAffectPrecedence() {
        XCTAssertEqual(compareVersions("1.0.0+abc123", "1.0.0"), 0)
        XCTAssertEqual(compareVersions("1.0.0+999", "1.0.0"), 0, "build metadata is not a fourth component")
    }

    func testTheShippingBuildIsSupportedAgainstProductionsCurrentConfig() throws {
        let decision = evaluateClientVersion(config: try liveConfig(), currentVersion: "1.0.0")
        XCTAssertEqual(decision.status, .supported, "1.0.0 must not be nagged to update to 1.0.0-rc.1")
    }

    func testABuildBelowTheMinimumIsBlockedAndCarriesTheStoreURL() throws {
        let config = try liveConfig(minimum: "1.1.0", recommended: "1.1.0", storeURL: "https://apps.apple.com/app/id123")
        let decision = evaluateClientVersion(config: config, currentVersion: "1.0.0")
        XCTAssertEqual(decision.status, .blocked)
        XCTAssertEqual(decision.minimum, "1.1.0")
        XCTAssertEqual(decision.storeURL, "https://apps.apple.com/app/id123")
    }

    func testBlockedWithNoStoreURLStillDecidesToBlock() throws {
        // Production's store_urls.ios is null today, so this is the shape the
        // gate would actually fire in. The view must not depend on the link.
        let config = try liveConfig(minimum: "9.9.9")
        let decision = evaluateClientVersion(config: config, currentVersion: "1.0.0")
        XCTAssertEqual(decision.status, .blocked)
        XCTAssertNil(decision.storeURL)
    }
}
