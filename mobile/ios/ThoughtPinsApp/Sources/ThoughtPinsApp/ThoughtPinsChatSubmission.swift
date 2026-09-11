import Foundation
import ThoughtPinsCore

// The view needs an explicit result: a banner may describe an earlier action
// or a read-model refresh, neither of which says whether this turn succeeded.
extension ThoughtPinsAppModel {
    @discardableResult
    public func sendChat(_ text: String) async -> Bool {
        guard !isThinking else { return false }
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        guard aiProcessingConsentAccepted else {
            showProblem("Allow AI processing before sending personal content.")
            return false
        }
        if let maintenanceMessage {
            showProblem(maintenanceMessage)
            return false
        }
        dismissBanner()
        isThinking = true
        defer { isThinking = false }
        do {
            let response = try await api.chat(
                text: text,
                surface: "ios",
                includePrivate: usePrivateMemories
            )
            chatReply = response.reply
            routeLabel = response.routeType
            await refreshReadModels()
            return true
        } catch APIClientError.httpStatus(403, let message) where usePrivateMemories {
            // The deployment can refuse to put private entries in front of the
            // model at all (PRIVATE_ALLOW_LLM). The toggle cannot know that
            // ahead of time -- client-config does not report it -- so the first
            // send is where it surfaces. Turning the switch back off is the
            // honest thing to show: leaving it on advertises a setting the
            // server will refuse every time, and "Chat failed" made a policy
            // decision look like a broken build.
            usePrivateMemories = false
            _ = message  // deliberately not shown; see the constant's note
            showProblem(thoughtPinsPrivateMemoryRefusal)
        } catch {
            // 20 requests a minute is a limit a real person can reach, and
            // "Chat failed" tells them nothing to do about it. The mapping
            // that already turns a 429 into a sentence is three lines away.
            showProblem(
                thoughtPinsPlainMessage(
                    for: error,
                    fallback: "Chat failed. Your account and drafts are still safe."
                )
            )
        }
        return false
    }
}
