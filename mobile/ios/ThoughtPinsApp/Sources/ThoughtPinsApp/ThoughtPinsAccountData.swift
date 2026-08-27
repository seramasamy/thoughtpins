import Foundation
import ThoughtPinsCore

// Taking your data out, and taking your account away. Split out of
// ThoughtPinsAppModel.swift when that file reached its size budget; the two
// belong together because they are the pair the privacy policy promises and the
// pair an App Store reviewer is sent to check.

extension ThoughtPinsAppModel {
    public func exportAccount() async {
        do {
            let export = try await api.exportAccount()
            // This used to bind the payload to `let export` and never use it.
            // The person was told "Your export is ready." and received
            // nothing -- no share sheet, no file, no screen. The privacy
            // policy says data can be exported "from the app", and the review
            // notes send a reviewer here as step 6, so a success banner over an
            // export that goes nowhere is the plainest possible version of not
            // doing what we say.
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(export)
            let stamp = ISO8601DateFormatter().string(from: Date()).prefix(10)
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("thought-pins-export-\(stamp).json")
            try data.write(to: destination, options: .atomic)
            exportedFile = destination
            showSuccess("Your export is ready. Choose where to keep it.")
        } catch {
            showProblem(
                thoughtPinsPlainMessage(for: error, fallback: "Could not build your export. Try again.")
            )
        }
    }

    public func deleteAccount() async {
        do {
            _ = try await api.deleteAccount()
            await clearLocalAccountState()
            showSuccess("Account deleted.")
        } catch {
            showProblem("Deletion failed.")
        }
    }

    public func redeemInvite(_ code: String) async {
        let trimmed = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !inviteBusy else { return }
        inviteBusy = true
        defer { inviteBusy = false }
        do {
            let status = try await api.redeemInvite(code: trimmed)
            inviteStatus = status
            if status.admitted {
                showSuccess("Invite accepted. Welcome to Thought Pins.")
                await refreshPreferences()
                await refreshReadModels()
            }
        } catch {
            // The server never says which part was wrong, and neither does this.
            showProblem("That code is not valid. Check it and try again.")
            await refreshInviteStatus()
        }
    }
}
