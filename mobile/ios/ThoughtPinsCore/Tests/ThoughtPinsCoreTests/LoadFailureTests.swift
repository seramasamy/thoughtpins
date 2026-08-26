import XCTest

@testable import ThoughtPinsCore

/// The detail screens told everyone to check their connection, whatever went
/// wrong. These pin the distinctions that message was hiding.
final class LoadFailureTests: XCTestCase {
    func testATransportFailureIsOffline() {
        let failure = ThoughtPinsLoadFailure(URLError(.notConnectedToInternet))
        XCTAssertEqual(failure, .offline)
        XCTAssertTrue(failure.isWorthRetrying)
        XCTAssertTrue(failure.message(subject: "this card").contains("offline"))
    }

    func testATimeoutIsNotFoldedIntoOffline() {
        XCTAssertEqual(ThoughtPinsLoadFailure(URLError(.timedOut)), .timedOut)
    }

    func testAMissingRecordIsGoneAndNotWorthRetrying() {
        let failure = ThoughtPinsLoadFailure(APIClientError.httpStatus(404, nil))
        XCTAssertEqual(failure, .gone)
        XCTAssertFalse(failure.isWorthRetrying, "a deleted record does not come back from a retry")
    }

    func testAServerFaultDoesNotBlameTheConnection() {
        let message = ThoughtPinsLoadFailure(APIClientError.httpStatus(500, nil)).message(subject: "this card")
        XCTAssertEqual(ThoughtPinsLoadFailure(APIClientError.httpStatus(500, nil)), .serverUnavailable)
        XCTAssertTrue(
            message.contains("Nothing is wrong with your connection"),
            "a 500 must not send someone to check their wifi: \(message)"
        )
    }

    func testEveryFiveHundredRangeStatusIsServerUnavailable() {
        for status in [500, 502, 503, 504, 599] {
            XCTAssertEqual(ThoughtPinsLoadFailure(APIClientError.httpStatus(status, nil)), .serverUnavailable, "\(status)")
        }
    }

    func testAClearedSessionSaysSoRatherThanBlamingTheNetwork() {
        let failure = ThoughtPinsLoadFailure(APIClientError.sessionExpired)
        XCTAssertEqual(failure, .signedOut)
        XCTAssertFalse(failure.isWorthRetrying)
        XCTAssertTrue(failure.message(subject: "this card").contains("Sign in again"))
    }

    func testAnUnauthorisedStatusIsAlsoSignedOut() {
        XCTAssertEqual(ThoughtPinsLoadFailure(APIClientError.httpStatus(401, nil)), .signedOut)
        XCTAssertEqual(ThoughtPinsLoadFailure(APIClientError.httpStatus(403, nil)), .signedOut)
    }

    func testAnUnknownErrorFallsBackWithoutClaimingACause() {
        struct Odd: Error {}
        let failure = ThoughtPinsLoadFailure(Odd())
        XCTAssertEqual(failure, .unexpected)
        let message = failure.message(subject: "this card")
        XCTAssertFalse(message.contains("offline"), "must not invent a cause: \(message)")
        XCTAssertFalse(message.contains("connection"), "must not invent a cause: \(message)")
    }

    func testTheServerEnvelopeMessageIsNeverShown() {
        // A read failure has no safe server-authored sentence, and the envelope
        // for a memory card could carry journal text.
        let failure = ThoughtPinsLoadFailure(APIClientError.httpStatus(418, "secret journal fragment"))
        XCTAssertFalse(failure.message(subject: "this card").contains("secret journal fragment"))
    }

    func testTheSubjectIsUsedSoTheSentenceNamesWhatFailed() {
        let message = ThoughtPinsLoadFailure(URLError(.notConnectedToInternet)).message(subject: "the full details")
        XCTAssertTrue(message.contains("the full details"))
    }
}
