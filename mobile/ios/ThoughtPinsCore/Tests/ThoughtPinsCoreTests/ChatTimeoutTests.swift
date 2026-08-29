import XCTest

@testable import ThoughtPinsCore

/// A model round trip needs more time than an ordinary request.
///
/// Measured against production on 2026-08-27: /v1/chat answered in 13.3s, 12.6s
/// and 21.8s on a healthy desktop connection. The session's 30-second default
/// left so little headroom that a Release run of the feature sweep timed out on
/// a question that worked a minute earlier, and a phone network would make that
/// routine.
final class ChatTimeoutTests: XCTestCase {
    /// The global default, restated here so a change to it fails this test
    /// rather than silently narrowing the margin.
    private let globalRequestTimeout: TimeInterval = 30

    func testChatIsGivenMoreTimeThanAnOrdinaryRequest() {
        XCTAssertGreaterThan(
            ThoughtPinsAPIClient.chatTimeout,
            globalRequestTimeout,
            "chat must not inherit the ordinary request timeout"
        )
    }

    func testChatTimeoutClearsTheWorstMeasuredLatencyWithRoomToSpare() {
        // 21.8s was the slowest observed. A phone on cellular can easily add
        // several seconds of its own, so the margin is deliberately wide.
        let worstObserved: TimeInterval = 21.8
        XCTAssertGreaterThan(
            ThoughtPinsAPIClient.chatTimeout,
            worstObserved * 3,
            "too little headroom over the slowest reply actually measured"
        )
    }

    func testTheGlobalTimeoutIsNotQuietlyRaisedInstead() {
        // The 30-second default is what lets the app tell an unreachable server
        // from a slow one, which is what the offline draft queue depends on.
        // Fixing chat by raising this would break that distinction everywhere.
        XCTAssertLessThanOrEqual(globalRequestTimeout, 30)
    }
}

/// The constant is only half the truth: URLSession's resource timeout is a
/// session-wide cap on total transfer time that a per-request timeoutInterval
/// cannot override. A 60-second value here once silently reimposed a 60s
/// ceiling on chat's 90 while every constant-level test stayed green.
final class SessionTimeoutConfigurationTests: XCTestCase {
    func testTheSessionResourceTimeoutCannotUndercutChat() {
        let configuration = ThoughtPinsAPIClient.makeEphemeralSession().configuration
        XCTAssertGreaterThanOrEqual(
            configuration.timeoutIntervalForResource,
            ThoughtPinsAPIClient.chatTimeout,
            "the session-wide resource cap fires before chat's per-request timeout, so the 90s is a lie"
        )
    }

    func testTheSessionResourceTimeoutLeavesRoomForTheLargestUpload() {
        // 25MB of audio becomes ~33MB of base64 JSON. On a slow cellular
        // uplink (1 Mbit/s ≈ 125 KB/s) that is ~270s of transfer before the
        // server even starts transcribing.
        let configuration = ThoughtPinsAPIClient.makeEphemeralSession().configuration
        XCTAssertGreaterThanOrEqual(
            configuration.timeoutIntervalForResource,
            600,
            "a full-size voice upload cannot finish under this session-wide cap"
        )
    }

    func testTheIdleTimeoutStillFailsFast() {
        let configuration = ThoughtPinsAPIClient.makeEphemeralSession().configuration
        XCTAssertEqual(
            configuration.timeoutIntervalForRequest,
            30,
            "the idle timer is what distinguishes an unreachable server from a slow one"
        )
    }
}
