import Foundation
import ThoughtPinsCore

// File upload, Obsidian vault import, and voice-note upload/retry. Split out of
// ThoughtPinsAppModel.swift when that file reached its size budget; these are
// the three ways content enters from the Capture screen and they share the
// upload provider, the vault-import phase, and the voice retry store.
extension ThoughtPinsAppModel {
    public func uploadSelectedFile(destination: ThoughtPinsUploadDestination = .auto) async {
        guard aiProcessingConsentAccepted else {
            showProblem("Allow AI processing before uploading personal content.")
            return
        }
        do {
            let payload = try await uploadProvider.payload(for: destination)
            if destination == .obsidianVault {
                // The preview polls the server for up to twenty minutes. Run
                // it as a cancellable task and publish a phase, so the screen
                // shows progress and a cancel control instead of a silent
                // spinner with no way out.
                let previewTask = Task {
                    try await api.previewObsidianVaultResumable(
                        filename: payload.filename,
                        contentBase64: payload.contentBase64
                    )
                }
                vaultImportPhase = .previewing
                cancelVaultWork = { previewTask.cancel() }
                defer { vaultImportPhase = .idle; cancelVaultWork = nil }
                let preview = try await previewTask.value
                pendingVaultImport = preview
                let result = preview.result
                showSuccess("Vault preview ready: \(result?.newNotes ?? 0) new, \(result?.changedNotes ?? 0) changed.")
                return
            }
            let response = try await api.uploadFile(
                filename: payload.filename,
                contentBase64: payload.contentBase64,
                mediaType: payload.mediaType,
                destination: destination.rawValue,
                caption: payload.caption,
                title: payload.title,
                sourceType: payload.sourceType,
                conversationId: "native-upload"
            )
            if response.documentId != nil {
                showSuccess("Upload saved to your library.")
            } else if response.entryId != nil {
                showSuccess("Upload saved as a journal entry.")
            } else {
                showProblem(response.error ?? "We could not read any text from that file. Paste the text you want kept.")
            }
            await refreshReadModels()
        } catch ThoughtPinsNativeUploadError.cancelled {
            // Closing the picker is a decision, not a problem to report.
        } catch is CancellationError {
            // The person cancelled a vault preview mid-poll.
            showProblem("Vault import cancelled.")
        } catch {
            showProblem(thoughtPinsPlainMessage(for: error, fallback: "That did not work. Try again."))
        }
    }

    public func applyPendingVaultImport() async {
        guard let pendingVaultImport else { return }
        // Applying polls the same up-to-twenty-minute loop as the preview.
        let applyTask = Task {
            try await api.applyPreviewedVaultImport(
                transferId: pendingVaultImport.id,
                conflictPolicy: pendingVaultImport.conflictPolicy
            )
        }
        vaultImportPhase = .applying
        cancelVaultWork = { applyTask.cancel() }
        defer { vaultImportPhase = .idle; cancelVaultWork = nil }
        do {
            let response = try await applyTask.value
            self.pendingVaultImport = nil
            showSuccess("Imported \(response.imported) notes. \(response.journalJobsQueued) are still being read.")
            await refreshReadModels()
        } catch is CancellationError {
            showProblem("Vault import cancelled. The preview is still here if you want to try again.")
        } catch {
            showProblem(thoughtPinsPlainMessage(for: error, fallback: "That did not work. Try again."))
        }
    }

    /// Stop a preview or apply that is mid-poll. The pending preview, if any,
    /// is left in place so the person can retry rather than re-upload.
    public func cancelVaultImportInProgress() {
        cancelVaultWork?()
    }

    public func discardPendingVaultImport() async {
        guard let pendingVaultImport else { return }
        do {
            _ = try await api.cancelVaultImport(transferId: pendingVaultImport.id)
            self.pendingVaultImport = nil
            showSuccess("Vault preview discarded.")
        } catch {
            showProblem(thoughtPinsPlainMessage(for: error, fallback: "That did not work. Try again."))
        }
    }


    public func uploadVoiceNote(_ data: Data) async {
        guard aiProcessingConsentAccepted else {
            showProblem("Allow AI processing before uploading a voice note.")
            return
        }
        guard !data.isEmpty else {
            showProblem("The voice note was empty.")
            return
        }
        do {
            let response = try await postVoiceNote(data)
            if response.entryId == nil {
                showProblem(response.error ?? "No speech was recognized in that voice note.")
            } else if response.voiceAssetId != nil {
                showSuccess("Voice note saved with its encrypted recording.")
            } else {
                showSuccess("Voice note saved. The recording was discarded after transcription.")
            }
            await refreshReadModels()
        } catch APIClientError.sessionExpired {
            await clearLocalAccountState()
            showProblem("Your session expired. Please sign in again.")
        } catch {
            // The banner used to promise "Your draft remains on this device"
            // while the bytes were already gone -- the recorder deletes its
            // temp file before upload even starts. Keep the recording for
            // real, then say so; if even that fails, say that instead.
            do {
                _ = try await voiceRetry.keep(data)
                showProblem("Voice note failed to upload. The recording is saved on this device and will be retried.")
            } catch {
                showProblem("Voice note failed, and the recording could not be kept. Try again.")
            }
        }
    }

    private func postVoiceNote(_ data: Data) async throws -> UploadIngestResponse {
        try await api.uploadFile(
            filename: "voice-note-\(Int(Date().timeIntervalSince1970)).m4a",
            contentBase64: data.base64EncodedString(),
            mediaType: "audio/mp4",
            destination: "journal",
            caption: "Voice note",
            title: "Voice note",
            sourceType: "voice_note",
            conversationId: "ios-voice"
        )
    }

    /// Upload recordings kept by earlier failed attempts. Runs beside the
    /// text-draft sync at bootstrap, under the same session/consent/invite
    /// conditions. A response counts as delivered whatever the transcription
    /// outcome; only a thrown transport error keeps the file for next time.
    func retryQueuedVoiceNotes() async {
        guard let pending = try? await voiceRetry.pending(), !pending.isEmpty else { return }
        var delivered = 0
        for url in pending {
            guard let data = try? Data(contentsOf: url), !data.isEmpty else {
                await voiceRetry.discard(url)
                continue
            }
            do {
                _ = try await postVoiceNote(data)
                await voiceRetry.discard(url)
                delivered += 1
            } catch {
                break
            }
        }
        if delivered > 0 {
            showSuccess(delivered == 1
                ? "A voice note from earlier was uploaded."
                : "\(delivered) voice notes from earlier were uploaded.")
        }
    }

}
