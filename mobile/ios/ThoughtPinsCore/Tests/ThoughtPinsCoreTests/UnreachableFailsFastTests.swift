import XCTest

@testable import ThoughtPinsCore

/// A long timeout must buy patience for slowness, never for absence.
///
/// Chat is allowed 90 seconds because production genuinely answers in 13-22.
/// The danger in that number is the other case: someone on a plane, or in a
/// tunnel, must be told there is no signal straight away rather than watching a
/// spinner for a minute and a half. `waitsForConnectivity` is false precisely so
/// an unreachable host fails immediately, and the offline draft queue depends on
/// that distinction -- but the per-request timeout was added afterwards, so this
/// checks the two still coexist.
final class UnreachableFailsFastTests: XCTestCase {
    /// Reserved, discard-protocol port. Nothing listens; connection is refused.
    private let unreachable = URL(string: "https://127.0.0.1:9")!

    func testChatToAnUnreachableHostFailsInSecondsNotMinutes() async throws {
        let store = TestSessionStore(ApiSession(accessToken: "probe", refreshToken: "probe"))
        let api = ThoughtPinsAPIClient(baseURL: unreachable, sessionStore: store)

        let started = Date()
        do {
            _ = try await api.chat(text: "anything")
            XCTFail("a refused connection should not have produced a reply")
        } catch {
            let elapsed = Date().timeIntervalSince(started)
            print("UNREACHABLE_CHAT_SECONDS=\(elapsed)")
            XCTAssertLessThan(
                elapsed, 15,
                "a refused connection took \(elapsed)s. Someone with no signal must be told "
                + "immediately, not held for the 90s chat window."
            )
            // And it must read as a transport failure, so the app queues a draft
            // rather than reporting a server error.
            XCTAssertEqual(ThoughtPinsLoadFailure(error), .offline)
        }
    }

    func testTheLongWindowIsStillAvailableForSlowness() {
        // The two properties this test pair protects, stated together: chat may
        // wait a long time, and waitsForConnectivity must stay off so that
        // waiting only ever happens against a host that answered.
        XCTAssertEqual(ThoughtPinsAPIClient.chatTimeout, 90)
    }
}
