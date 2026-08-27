import Foundation
import ThoughtPinsCore

// Personal voice archive: the opt-in deciding whether recordings are kept after
// transcription rather than discarded. Split out of ThoughtPinsAppModel.swift
// when that file reached its size budget. One self-contained setting with a
// three-step lifecycle -- enable, disable, delete what was kept -- and both the
// privacy policy and the microphone permission string turn on it, so it is
// worth being readable in one place.

extension ThoughtPinsAppModel {
    public func enableVoiceArchive() async {
        do {
            voiceArchiveStatus = try await api.enableVoiceArchive(
                VoiceArchiveConsentRequest(
                    retainRecordings: true,
                    acknowledgeSensitiveAudio: true,
                    acknowledgePersonalUseOnly: true,
                    acknowledgeDeletionAvailable: true
                )
            )
            showSuccess("Personal voice archive enabled.")
        } catch {
            showProblem("Could not enable the voice archive.")
        }
    }

    public func disableVoiceArchive() async {
        do {
            voiceArchiveStatus = try await api.disableVoiceArchive()
            showSuccess("Future voice retention disabled.")
        } catch {
            showProblem("Could not update voice retention.")
        }
    }

    public func deleteVoiceArchive() async {
        do {
            _ = try await api.deleteVoiceArchive()
            await refreshVoiceArchive()
            showSuccess("Retained voice recordings deleted.")
        } catch {
            showProblem("Could not delete the voice archive.")
        }
    }
}
