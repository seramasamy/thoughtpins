import Foundation
import XCTest
@testable import ThoughtPinsCore

final class ThoughtPinsAuthFailureTests: XCTestCase {
    func testTransportFailuresAreDistinguishedFromRejectedCredentials() {
        XCTAssertEqual(ThoughtPinsAuthFailure(URLError(.notConnectedToInternet)), .unreachable)
        XCTAssertEqual(ThoughtPinsAuthFailure(URLError(.networkConnectionLost)), .unreachable)
        XCTAssertEqual(ThoughtPinsAuthFailure(URLError(.cannotFindHost)), .unreachable)
        XCTAssertEqual(ThoughtPinsAuthFailure(URLError(.timedOut)), .timedOut)
    }

    func testServerStatusesMapToDistinctCauses() {
        XCTAssertEqual(ThoughtPinsAuthFailure(APIClientError.httpStatus(401, "nope")), .badCredentials)
        XCTAssertEqual(ThoughtPinsAuthFailure(APIClientError.httpStatus(403, nil)), .badCredentials)
        XCTAssertEqual(ThoughtPinsAuthFailure(APIClientError.httpStatus(429, nil)), .rateLimited)
        XCTAssertEqual(ThoughtPinsAuthFailure(APIClientError.httpStatus(500, "boom")), .serverUnavailable)
        XCTAssertEqual(ThoughtPinsAuthFailure(APIClientError.httpStatus(503, nil)), .serverUnavailable)
    }

    func testAnExplainedRejectionCarriesTheServerMessage() {
        XCTAssertEqual(
            ThoughtPinsAuthFailure(APIClientError.httpStatus(400, "That email is already registered.")),
            .rejected("That email is already registered.")
        )
        // No message to pass on, so do not invent one.
        XCTAssertEqual(ThoughtPinsAuthFailure(APIClientError.httpStatus(400, nil)), .unexpected)
        XCTAssertEqual(ThoughtPinsAuthFailure(APIClientError.httpStatus(400, "")), .unexpected)
    }

    /// The failure that cost a Mac session an hour: the network call succeeded
    /// and the password was right, but the Keychain refused the write, and the
    /// app said "Sign in failed."
    func testARefusedKeychainWriteIsNotReportedAsBadCredentials() {
        let failure = ThoughtPinsAuthFailure(SessionStoreError.keychain(-34018))
        XCTAssertEqual(failure, .sessionNotStored)
        XCTAssertNotEqual(failure, .badCredentials)
        XCTAssertTrue(failure.signInMessage.contains("would not save the session"))
    }

    func testAnUndecodableResponseCarriesNoDetailThrough() {
        struct Key: CodingKey {
            var stringValue: String
            var intValue: Int? { nil }
            init(stringValue: String) { self.stringValue = stringValue }
            init?(intValue: Int) { nil }
        }
        let decoding = DecodingError.keyNotFound(
            Key(stringValue: "access_token"),
            .init(codingPath: [], debugDescription: "access_token was here")
        )
        let failure = ThoughtPinsAuthFailure(decoding)
        XCTAssertEqual(failure, .unexpected)
        XCTAssertFalse(failure.signInMessage.contains("access_token"))
        XCTAssertFalse(failure.registrationMessage.contains("access_token"))
    }

    func testEveryCauseProducesADistinctActionableSentence() {
        let causes: [ThoughtPinsAuthFailure] = [
            .unreachable, .timedOut, .badCredentials, .rateLimited,
            .serverUnavailable, .sessionNotStored, .unexpected,
        ]
        let signIn = causes.map(\.signInMessage)
        XCTAssertEqual(Set(signIn).count, causes.count, "Two causes share a sign-in message")
        let registration = causes.map(\.registrationMessage)
        XCTAssertEqual(Set(registration).count, causes.count, "Two causes share a registration message")
        for message in signIn + registration {
            XCTAssertFalse(message.isEmpty)
            XCTAssertTrue(message.hasSuffix("."), "\(message) should read as a sentence")
        }
    }
}
