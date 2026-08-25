import Foundation

/// Why a sign-in or account-creation attempt did not produce a session.
///
/// Both paths used to collapse every cause into one string -- "Sign in failed."
/// and "Registration failed. Check credentials and try again." -- which told a
/// person nothing they could act on. It is also the worst place for that:
/// App Review starts at the sign-in screen, and a reviewer who cannot get past
/// it, cannot say why, and has only a screenshot to send us is how a
/// submission stalls. "Check credentials" was actively misleading whenever the
/// real cause was a dropped connection or a 500.
///
/// Privacy, per AGENTS.md: nothing here reads or interpolates an access token,
/// a refresh token, a password, or response content. The only server-supplied
/// text used is the error envelope's `message`, which `ThoughtPinsAPIClient`
/// has already separated from `details` and capped, and which is covered by
/// `testErrorUsesEnvelopeMessageInsteadOfReturningTheRawBody`. Decoding
/// failures deliberately carry no detail through, because a `DecodingError`
/// describing an auth response is exactly the string that should never be
/// shown or logged.
public enum ThoughtPinsAuthFailure: Equatable, Sendable {
    /// The request never reached the server.
    case unreachable
    /// The request reached the server but took too long.
    case timedOut
    /// The server understood the request and rejected the identity.
    case badCredentials
    /// Too many attempts.
    case rateLimited
    /// The server failed, not the caller.
    case serverUnavailable
    /// The server declined for a reason it explained safely.
    case rejected(String)
    /// Authentication succeeded but the session could not be stored.
    case sessionNotStored
    /// Anything else, including a malformed or undecodable response.
    case unexpected

    public init(_ error: Error) {
        if let urlError = error as? URLError {
            self = urlError.code == .timedOut ? .timedOut : .unreachable
            return
        }
        // A refused Keychain write is the one failure that looks identical to a
        // wrong password from the outside and is not one: the network call
        // succeeded and the credentials were right. An unsigned simulator
        // build, which has no application-identifier entitlement, fails here
        // on every attempt.
        if error is SessionStoreError {
            self = .sessionNotStored
            return
        }
        guard case let APIClientError.httpStatus(status, message) = error else {
            self = .unexpected
            return
        }
        switch status {
        case 401, 403:
            self = .badCredentials
        case 429:
            self = .rateLimited
        case 500...599:
            self = .serverUnavailable
        default:
            if let message, !message.isEmpty {
                self = .rejected(message)
            } else {
                self = .unexpected
            }
        }
    }

    /// What to show the person. One sentence, and where there is something they
    /// can do about it, it says so.
    public var signInMessage: String {
        switch self {
        case .unreachable:
            return "Could not reach Thought Pins. Check your connection and try again."
        case .timedOut:
            return "Signing in took too long. Check your connection and try again."
        case .badCredentials:
            return "That email, phone number, or password did not match."
        case .rateLimited:
            return "Too many sign-in attempts. Wait a minute and try again."
        case .serverUnavailable:
            return "Thought Pins is unavailable right now. Try again shortly."
        case .rejected(let message):
            return message
        case .sessionNotStored:
            return "Signed in, but this device would not save the session. Try again."
        case .unexpected:
            return "Sign in failed. Try again."
        }
    }

    /// The same cause, worded for account creation.
    public var registrationMessage: String {
        switch self {
        case .unreachable:
            return "Could not reach Thought Pins. Check your connection and try again."
        case .timedOut:
            return "Creating the account took too long. Check your connection and try again."
        case .badCredentials:
            return "That email or phone number cannot be used to create an account."
        case .rateLimited:
            return "Too many attempts. Wait a minute and try again."
        case .serverUnavailable:
            return "Thought Pins is unavailable right now. Try again shortly."
        case .rejected(let message):
            return message
        case .sessionNotStored:
            return "Account created, but this device would not save the session. Sign in to continue."
        case .unexpected:
            return "Could not create the account. Try again."
        }
    }
}
