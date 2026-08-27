import Foundation
import ThoughtPinsCore

// Wording the app shows a person, kept apart from the model that decides when
// to show it. Extracted when ThoughtPinsAppModel.swift reached its size budget:
// these are pure functions of their input and have no business sitting inside
// an ObservableObject.

/// A message fit to show a person, from an arbitrary Swift error.
///
/// `error.localizedDescription` on a bare Swift enum reads
/// "The operation couldn't be completed. (ThoughtPinsCore.APIClientError
/// error 1.)" — a type name, on screens including sign-in, which is where App
/// Review starts. Provider SDKs conform to LocalizedError and already say
/// something plain, so those are preferred; transport and server failures go
/// through the mapping the app already has; anything else gets the caller's
/// own sentence rather than Foundation's.
func thoughtPinsPlainMessage(for error: Error, fallback: String) -> String {
    if let described = (error as? LocalizedError)?.errorDescription, !described.isEmpty {
        return described
    }
    switch ThoughtPinsAuthFailure(error) {
    case .unreachable:
        return "Could not reach Thought Pins. Check your connection and try again."
    case .timedOut:
        return "That took too long. Check your connection and try again."
    case .rateLimited:
        return "Too many attempts. Wait a minute and try again."
    case .serverUnavailable:
        return "Thought Pins is unavailable right now. Try again shortly."
    case .rejected(let message):
        return message
    case .sessionNotStored, .badCredentials, .unexpected:
        return fallback
    }
}

/// What the router did, said to the person rather than to the log.
///
/// `route_type` is the router's own classification, in snake_case: the badge
/// above a reply read "JOURNAL_ENTRY", "NATURAL_COMMAND", "UPLOAD_NEEDS_TEXT".
/// Returns nil where nothing happened beyond the reply already on screen, so
/// the badge disappears rather than announcing which code path ran.
public func thoughtPinsRouteLabel(_ routeType: String) -> String? {
    switch routeType {
    case "journal_entry", "private_entry":
        return "Saved to your journal"
    case "document_link", "document_text", "library_upload":
        return "Saved to your library"
    case "query", "report_request", "search":
        return "Answered from your memories"
    case "correction":
        return "Updated an earlier note"
    case "natural_command", "command":
        return "Account action"
    default:
        // chat, conversation, mixed, ambiguous, and anything new the server
        // starts sending: nothing worth a badge.
        return nil
    }
}

/// What to say when the deployment refuses to put private entries in front of
/// the model.
///
/// `PRIVATE_ALLOW_LLM` is off in production, deliberately: an entry marked
/// private is never sent to a third-party model. The server's own sentence for
/// this is "Private-entry LLM context is disabled by server policy" -- a phrase
/// for whoever configured the deployment, not for the person holding the phone,
/// and the string an App Store reviewer is most likely to be shown. Two screens
/// can reach this refusal, so the wording lives in one place.
let thoughtPinsPrivateMemoryRefusal =
    "Entries you marked private are never sent to the model, so they cannot inform replies here."

/// Whether this account has accepted the AI disclosure *that is current now*.
///
/// The check used to be `legalAcceptances["ai_disclosure"] != nil` -- does an
/// acceptance exist, of any version. The web client has always compared the
/// stored version against the served one. So the day LEGAL_DOCUMENT_VERSION
/// moves, every web user is re-prompted and no iOS user ever is: the app would
/// go on treating a signature on a superseded document as consent to the new
/// one. That is the wrong direction for a consent record to fail in.
///
/// A missing served version means we could not ask; existing consent stands
/// rather than the app locking someone out of their journal over a field it
/// could not read.
func thoughtPinsHasAcceptedCurrentDisclosure(
    _ preferences: PreferencesResponse,
    currentVersion: String?
) -> Bool {
    guard let acceptance = preferences.legalAcceptances["ai_disclosure"] else { return false }
    guard let currentVersion, !currentVersion.isEmpty else { return true }
    return acceptance.version == currentVersion
}
