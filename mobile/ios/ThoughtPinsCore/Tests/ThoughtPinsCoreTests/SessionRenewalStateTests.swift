import XCTest
@testable import ThoughtPinsCore

final class SessionRenewalStateTests: XCTestCase {
    private let original = ApiSession(accessToken: "original", refreshToken: "original-refresh")
    private let renewed = ApiSession(accessToken: "renewed", refreshToken: "renewed-refresh")

    func testLateResponseCanReuseItsOwnRenewedSession() throws {
        var state = SessionRenewalState()
        let request = try XCTUnwrap(state.capture(original))
        state.didRenew(renewed)
        let current = try XCTUnwrap(state.current(for: request, stored: renewed))
        XCTAssertEqual(current.session, renewed)
        XCTAssertEqual(current.generation, request.generation)
    }

    func testAnotherLoginInvalidatesTheEarlierRequest() throws {
        var state = SessionRenewalState()
        let request = try XCTUnwrap(state.capture(original))
        XCTAssertNil(state.current(for: request, stored: renewed))
    }

    func testLogoutInvalidatesTheEarlierRequest() throws {
        var state = SessionRenewalState()
        let request = try XCTUnwrap(state.capture(original))
        XCTAssertNil(state.current(for: request, stored: nil))
    }

    func testCapturingTheSameSessionPreservesIdentity() {
        var state = SessionRenewalState()
        XCTAssertEqual(state.capture(original), state.capture(original))
        XCTAssertNil(state.capture(nil))
    }
}
