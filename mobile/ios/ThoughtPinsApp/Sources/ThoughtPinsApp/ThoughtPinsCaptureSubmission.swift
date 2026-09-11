import Foundation
import ThoughtPinsCore

extension ThoughtPinsAppModel {
    /// True only after the server or the local queue has accepted the note.
    /// Callers retain an unsaved draft and any newer text typed while awaiting.
    @discardableResult
    public func saveJournal(_ text: String) async -> Bool {
        guard !savingJournal, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        guard aiProcessingConsentAccepted else {
            showProblem("Allow AI processing before saving journal content.")
            return false
        }
        savingJournal = true
        defer { savingJournal = false }
        do {
            let response = try await api.ingest(text: text)
            showSuccess(response.jobId == nil ? "Saved." : "Saved. Still reading it for what to remember.")
            await refreshReadModels()
            return true
        } catch {
            let rateLimited: Bool
            if case APIClientError.httpStatus(429, _) = error { rateLimited = true } else { rateLimited = false }
            do {
                _ = try await drafts.enqueue(text: text)
                showSuccess(rateLimited
                    ? "You are sending faster than we can keep up. Saved on this device; sync queued drafts to send it."
                    : "Saved on this device. Reconnect and sync queued drafts to send it.")
                await refreshDraftCount()
                return true
            } catch DraftStoreError.queueFull(let limit) {
                showProblem("\(limit) drafts are waiting to send. This note is still here; sync queued drafts, then save it again.")
            } catch {
                showProblem("Could not save this offline. Keep a copy before leaving this screen.")
            }
            await refreshDraftCount()
            return false
        }
    }

    @discardableResult
    public func ingestLink(_ url: String) async -> Bool {
        guard !importingLink else { return false }
        let value = url.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parsed = URLComponents(string: value),
              ["https", "http"].contains(parsed.scheme?.lowercased() ?? ""),
              let host = parsed.host, !host.isEmpty else {
            showProblem("Enter a complete link starting with https:// or http://.")
            return false
        }
        guard aiProcessingConsentAccepted else {
            showProblem("Allow AI processing before adding a reading.")
            return false
        }
        importingLink = true
        defer { importingLink = false }
        do {
            _ = try await api.createLibrarySource(url: value, sourceType: "article")
            showSuccess("Reading saved.")
            await refreshReadModels()
            return true
        } catch {
            showProblem("Could not import that link. It is still here so you can try again.")
            return false
        }
    }
}
