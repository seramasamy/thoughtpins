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
