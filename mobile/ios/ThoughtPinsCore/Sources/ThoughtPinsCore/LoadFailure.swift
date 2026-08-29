import Foundation

/// Why reading something did not produce it.
///
/// The detail screens shipped with one sentence for every cause -- "Could not
/// load this card. Check your connection and try again." On a 500 that sends a
/// person to fiddle with their wifi over a fault that is ours. On a 404, which
/// is what a card deleted on another device looks like, it invites them to
/// retry something that will never succeed. And a cleared session showed the
/// same line while the real answer was "sign in again".
///
/// Kept beside `ThoughtPinsAuthFailure` and mapped the same way, so the two
/// cannot drift. Privacy, per AGENTS.md: nothing here reads or interpolates a
/// token or any response content. The server envelope's `message` is
/// deliberately *not* carried through -- a read failure has no safe
/// server-authored sentence the way a rejected sign-in does, and the subject
/// noun the caller supplies is app-authored.
public enum ThoughtPinsLoadFailure: Equatable, Sendable {
    /// The request never reached the server.
    case offline
    /// It reached the server but took too long.
    case timedOut
    /// The server says this no longer exists.
    case gone
    /// The server failed, not the caller.
    case serverUnavailable
    /// The session was rejected and cleared.
    case signedOut
    /// Anything else.
    case unexpected

    public init(_ error: Error) {
        if let urlError = error as? URLError {
            self = urlError.code == .timedOut ? .timedOut : .offline
            return
        }
        if case APIClientError.sessionExpired = error {
            self = .signedOut
            return
        }
        guard case let APIClientError.httpStatus(status, _) = error else {
            self = .unexpected
            return
        }
        switch status {
        case 401, 403:
            self = .signedOut
        case 404, 410:
            self = .gone
        case 500...599:
            self = .serverUnavailable
        default:
            self = .unexpected
        }
    }

    /// Whether offering "Try again" is honest.
    ///
    /// A deleted record and a cleared session do not come back from a retry,
    /// and a button that cannot work is worse than no button.
    public var isWorthRetrying: Bool {
        switch self {
        case .offline, .timedOut, .serverUnavailable, .unexpected:
            return true
        case .gone, .signedOut:
            return false
        }
    }

    /// One sentence, naming what could not be read.
    ///
    /// - Parameter subject: a lowercase noun phrase for the thing, e.g.
    ///   "this card" or "the full details". Used mid-sentence.
    public func message(subject: String) -> String {
        switch self {
        case .offline:
            return "You are offline, so \(subject) could not be loaded. It will work again once you reconnect."
        case .timedOut:
            return "Loading \(subject) took too long. Check your connection and try again."
        case .gone:
            return "This is no longer in your journal. It may have been deleted on another device."
        case .serverUnavailable:
            return "Thought Pins could not answer just now. Nothing is wrong with your connection — try again shortly."
        case .signedOut:
            return "Your session ended. Sign in again to read this."
        case .unexpected:
            return "Could not load \(subject). Try again."
        }
    }
}
