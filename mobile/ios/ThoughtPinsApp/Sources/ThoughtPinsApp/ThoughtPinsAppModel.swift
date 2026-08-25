import Foundation
import AuthenticationServices
import AVFoundation
import Security
import SwiftUI
import ThoughtPinsCore
import UIKit
import UniformTypeIdentifiers

@MainActor
public final class ThoughtPinsAppModel: ObservableObject {
    @Published public private(set) var config: ClientConfig?
    @Published public private(set) var me: MeResponse?
    @Published public private(set) var maintenanceMessage: String?
    @Published public private(set) var chatReply: String = ""
    @Published public private(set) var routeLabel: String = "chat"
    @Published public private(set) var isThinking: Bool = false
    @Published public private(set) var responseStyle: String = "friendly"
    @Published public private(set) var importancePromptsEnabled: Bool = false
    @Published public private(set) var usePrivateMemories: Bool = false
    @Published public private(set) var aiProcessingConsentAccepted: Bool = false
    // Nil until the gate has been asked about. Distinguishing "not yet known"
    // from "admitted" keeps the shell from flashing the gate at an admitted
    // account on every cold start.
    @Published public private(set) var inviteStatus: InviteStatusResponse?
    @Published public private(set) var inviteBusy: Bool = false
    /// A sign-in or account-creation request is in flight.
    ///
    /// The API session sets waitsForConnectivity, with a 60s resource timeout.
    /// An unreachable server therefore does not fail fast: it can sit for up to
    /// a minute. Without this the buttons stayed enabled and nothing on screen
    /// changed, so the app looked broken exactly where App Review starts.
    @Published public private(set) var authBusy: Bool = false
    @Published public private(set) var voiceArchiveStatus: VoiceArchiveStatusResponse?
    @Published public private(set) var librarySources: [LibrarySourceResponse] = []
    @Published public private(set) var memoryCards: [MemoryCardResponse] = []
    @Published public private(set) var placeCards: [MemoryCardResponse] = []
    @Published public private(set) var recentEntries: [EntryResponse] = []
    @Published public private(set) var pendingVaultImport: VaultImportSessionResponse?
    @Published public private(set) var draftCount: Int = 0
    @Published public var banner: String?

    public let api: ThoughtPinsAPIClient
    private let drafts: FileDraftStore
    private let oauthTokenProvider: any ThoughtPinsOAuthTokenProvider
    private let uploadProvider: any ThoughtPinsUploadProvider
    private var currentAppleNonce: String?
    private var currentAppleState: String?

    public init(
        baseURL: URL,
        sessionStore: SessionStore = KeychainSessionStore(),
        draftDirectory: URL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0],
        oauthTokenProvider: any ThoughtPinsOAuthTokenProvider = UnconfiguredThoughtPinsOAuthTokenProvider(),
        uploadProvider: any ThoughtPinsUploadProvider = UnconfiguredThoughtPinsUploadProvider()
    ) {
        self.api = ThoughtPinsAPIClient(baseURL: baseURL, sessionStore: sessionStore)
        self.drafts = FileDraftStore(directory: draftDirectory.appendingPathComponent("ThoughtPins", isDirectory: true))
        self.oauthTokenProvider = oauthTokenProvider
        self.uploadProvider = uploadProvider
    }


    public func legalURL(configured: String?, fallbackPath: String) -> URL {
        let fallback = "https://thoughtpins.com\(fallbackPath)"
        guard let configured, !configured.isEmpty else {
            return URL(string: fallback)!
        }
        if configured.hasPrefix("/") {
            return URL(string: "https://thoughtpins.com\(configured)") ?? URL(string: fallback)!
        }
        return URL(string: configured) ?? URL(string: fallback)!
    }

    public func acceptLegal(document: String) async {
        do {
            let version = config?.legalDocumentVersion ?? "2026-07-13"
            let preferences = try await api.acceptLegalDocument(document, version: version)
            aiProcessingConsentAccepted = preferences.legalAcceptances["ai_disclosure"] != nil
            banner = document == "ai_disclosure" ? "AI processing permission saved." : "Legal acknowledgement saved."
        } catch {
            banner = "Could not save legal acknowledgement."
        }
    }

    public var isAuthenticated: Bool {
        me != nil
    }

    /// Nil status means "not asked yet", which must not read as blocked.
    public var isBlockedByInviteGate: Bool {
        guard let inviteStatus else { return false }
        return inviteStatus.inviteRequired && !inviteStatus.admitted
    }

    public func supportsOAuth(_ provider: ThoughtPinsOAuthProvider) -> Bool {
        oauthTokenProvider.supports(provider)
    }

    public func bootstrap() async {
        do {
            let config = try await api.clientConfig()
            self.config = config
            self.maintenanceMessage = config.maintenanceMode ? (config.maintenanceMessage ?? "Maintenance currently in progress.") : nil
            self.me = try? await api.me()
            await refreshPreferences()
            // Ask the gate before loading anything it would refuse. Without
            // this the shell rendered a signed-in app whose every request came
            // back 403, which reads as broken rather than as a closed beta.
            await refreshInviteStatus()
            await refreshVoiceArchive()
            // Only sync under a live session. Signed out, every draft posts
            // into a 401, comes back marked failed and burns an attempt, so a
            // few cold launches on the sign-in screen were enough to exhaust
            // work the user had not lost.
            if me != nil {
                try? await syncDrafts()
            }
            await refreshReadModels()
        } catch {
            banner = "Could not reach Thought Pins. You can keep drafting locally."
        }
        await refreshDraftCount()
    }

    public func register(email: String?, phone: String?, password: String, consentToAIProcessing: Bool) async {
        guard consentToAIProcessing else {
            banner = "Review and accept the privacy, terms, and AI processing disclosure to create an account."
            return
        }
        // Checked before the account exists. Registering first and discovering
        // afterwards that there is nothing to sign in with leaves an orphan.
        guard let identifier = [email, phone].compactMap({ $0 }).first(where: { !$0.isEmpty }) else {
            banner = "Add an email address or phone number."
            return
        }
        authBusy = true
        defer { authBusy = false }
        do {
            _ = try await api.register(email: email, phone: phone, password: password)
            _ = try await api.login(identifier: identifier, password: password)
            me = try await api.me()
        } catch {
            // "Check credentials" was wrong for most of what lands here -- a
            // dropped connection, a 500, a Keychain that refused the write.
            banner = ThoughtPinsAuthFailure(error).registrationMessage
            return
        }
        // A brand new account is exactly the one the closed beta has not
        // admitted, so this cannot wait for the next cold start.
        await refreshInviteStatus()
        // The account exists and the session is live from here down. A failure
        // recording consent is not a failed registration, and saying it was
        // sends people back to a Create account button that now collides with
        // the account they just made.
        do {
            let version = config?.legalDocumentVersion ?? "2026-07-13"
            for document in ["privacy", "terms", "ai_disclosure"] {
                _ = try await api.acceptLegalDocument(document, version: version)
            }
            banner = "Account created."
        } catch {
            banner = "Account created, but your consent was not recorded. You will be asked again."
        }
        await refreshPreferences()
        await refreshVoiceArchive()
        await refreshReadModels()
    }


    public func oauthLogin(provider: ThoughtPinsOAuthProvider) async {
        do {
            let credential = try await oauthTokenProvider.credential(for: provider)
            _ = try await api.oauthLogin(
                provider: provider.rawValue,
                idToken: credential.idToken,
                displayName: credential.displayName,
                authorizationCode: credential.authorizationCode,
                redirectUri: credential.redirectUri,
                nonce: credential.nonce
            )
            me = try await api.me()
            await refreshPreferences()
            await refreshInviteStatus()
            banner = "Signed in with \(provider.label)."
            await refreshReadModels()
        } catch {
            banner = error.localizedDescription
        }
    }

    public func completeAppleSignIn(_ result: Result<ASAuthorization, Error>) async {
        let expectedNonce = currentAppleNonce
        let expectedState = currentAppleState
        defer {
            currentAppleNonce = nil
            currentAppleState = nil
        }
        do {
            let authorization = try result.get()
            guard
                let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                let tokenData = credential.identityToken,
                let idToken = String(data: tokenData, encoding: .utf8),
                let codeData = credential.authorizationCode,
                let authorizationCode = String(data: codeData, encoding: .utf8)
            else {
                banner = "Apple did not return a usable sign-in credential."
                return
            }
            guard
                let expectedNonce,
                let expectedState,
                credential.state == expectedState
            else {
                banner = "Apple sign-in could not be verified. Please try again."
                return
            }
            let displayName = credential.fullName.map { PersonNameComponentsFormatter().string(from: $0) }
            _ = try await api.oauthLogin(
                provider: "apple",
                idToken: idToken,
                displayName: displayName,
                authorizationCode: authorizationCode,
                nonce: expectedNonce
            )
            me = try await api.me()
            await refreshPreferences()
            await refreshInviteStatus()
            banner = "Signed in with Apple."
            await refreshReadModels()
        } catch {
            banner = "Sign in with Apple was not completed."
        }
    }

    public func configureAppleSignInRequest(_ request: ASAuthorizationAppleIDRequest) {
        let nonce = Self.secureOAuthValue()
        let state = Self.secureOAuthValue()
        currentAppleNonce = nonce
        currentAppleState = state
        request.requestedScopes = [.fullName, .email]
        request.nonce = nonce
        request.state = state
    }

    private static func secureOAuthValue() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        let status = bytes.withUnsafeMutableBytes { buffer in
            SecRandomCopyBytes(kSecRandomDefault, buffer.count, buffer.baseAddress!)
        }
        if status == errSecSuccess {
            return Data(bytes)
                .base64EncodedString()
                .replacingOccurrences(of: "+", with: "-")
                .replacingOccurrences(of: "/", with: "_")
                .replacingOccurrences(of: "=", with: "")
        }
        return UUID().uuidString + UUID().uuidString
    }

    public func login(identifier: String, password: String) async {
        authBusy = true
        defer { authBusy = false }
        do {
            _ = try await api.login(identifier: identifier, password: password)
            me = try await api.me()
            await refreshPreferences()
            await refreshInviteStatus()
            banner = "Signed in."
            await refreshReadModels()
        } catch {
            banner = ThoughtPinsAuthFailure(error).signInMessage
        }
    }

    public func sendChat(_ text: String) async {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard aiProcessingConsentAccepted else {
            banner = "Allow AI processing before sending personal content."
            return
        }
        if let maintenanceMessage {
            banner = maintenanceMessage
            return
        }
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
        } catch APIClientError.httpStatus(403, let message) where usePrivateMemories {
            // The deployment can refuse to put private entries in front of the
            // model at all (PRIVATE_ALLOW_LLM). The toggle cannot know that
            // ahead of time -- client-config does not report it -- so the first
            // send is where it surfaces. Turning the switch back off is the
            // honest thing to show: leaving it on advertises a setting the
            // server will refuse every time, and "Chat failed" made a policy
            // decision look like a broken build.
            usePrivateMemories = false
            banner = message ?? "Private memories cannot be used for replies on this server."
        } catch {
            banner = "Chat failed. Your account and drafts are still safe."
        }
    }

    public func saveJournal(_ text: String) async {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard aiProcessingConsentAccepted else {
            banner = "Allow AI processing before saving journal content."
            return
        }
        do {
            let response = try await api.ingest(text: text)
            banner = response.jobId == nil ? "Journal saved." : "Journal queued for memory extraction."
            await refreshReadModels()
        } catch {
            _ = try? await drafts.enqueue(text: text)
            banner = "Saved as an offline draft."
            await refreshDraftCount()
        }
    }

    public func ingestLink(_ url: String) async {
        guard !url.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard aiProcessingConsentAccepted else {
            banner = "Allow AI processing before adding a reading."
            return
        }
        do {
            _ = try await api.createLibrarySource(url: url, sourceType: "article")
            banner = "Reading saved."
            await refreshReadModels()
        } catch {
            banner = "Could not import that link."
        }
    }

    public func uploadSelectedFile(destination: ThoughtPinsUploadDestination = .auto) async {
        guard aiProcessingConsentAccepted else {
            banner = "Allow AI processing before uploading personal content."
            return
        }
        do {
            let payload = try await uploadProvider.payload(for: destination)
            if destination == .obsidianVault {
                let preview = try await api.previewObsidianVaultResumable(
                    filename: payload.filename,
                    contentBase64: payload.contentBase64
                )
                pendingVaultImport = preview
                let result = preview.result
                banner = "Vault preview ready: \(result?.newNotes ?? 0) new, \(result?.changedNotes ?? 0) changed."
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
                banner = "Upload saved to your library."
            } else if response.entryId != nil {
                banner = "Upload saved as a journal entry."
            } else {
                banner = "Upload processed: \(response.extractionStatus)."
            }
            await refreshReadModels()
        } catch {
            banner = error.localizedDescription
        }
    }

    public func applyPendingVaultImport() async {
        guard let pendingVaultImport else { return }
        do {
            let response = try await api.applyPreviewedVaultImport(
                transferId: pendingVaultImport.id,
                conflictPolicy: pendingVaultImport.conflictPolicy
            )
            self.pendingVaultImport = nil
            banner = "Vault imported: \(response.imported) notes; \(response.journalJobsQueued) queued."
            await refreshReadModels()
        } catch {
            banner = error.localizedDescription
        }
    }

    public func discardPendingVaultImport() async {
        guard let pendingVaultImport else { return }
        do {
            _ = try await api.cancelVaultImport(transferId: pendingVaultImport.id)
            self.pendingVaultImport = nil
            banner = "Vault preview discarded."
        } catch {
            banner = error.localizedDescription
        }
    }

    public func syncDrafts() async throws {
        let summary = try await api.syncQueuedDrafts(from: drafts)
        banner = summary.attempted == 0 ? banner : "Synced \(summary.synced) of \(summary.attempted) drafts."
        await refreshDraftCount()
    }

    public func updateResponseStyle(_ style: String) async {
        guard ["friendly", "clear", "mirror"].contains(style) else { return }
        do {
            let preferences = try await api.updatePreferences(PreferencesUpdateRequest(responseStyle: style))
            responseStyle = preferences.responseStyle ?? style
            banner = "Response voice updated."
        } catch {
            banner = "Could not update the response voice."
        }
    }

    public func uploadVoiceNote(_ data: Data) async {
        guard aiProcessingConsentAccepted else {
            banner = "Allow AI processing before uploading a voice note."
            return
        }
        guard !data.isEmpty else {
            banner = "The voice note was empty."
            return
        }
        do {
            let response = try await api.uploadFile(
                filename: "voice-note-\(Int(Date().timeIntervalSince1970)).m4a",
                contentBase64: data.base64EncodedString(),
                mediaType: "audio/mp4",
                destination: "journal",
                caption: "Voice note",
                title: "Voice note",
                sourceType: "voice_note",
                conversationId: "ios-voice"
            )
            if response.entryId == nil {
                banner = response.error ?? "No speech was recognized in that voice note."
            } else if response.voiceAssetId != nil {
                banner = "Voice note saved with its encrypted recording."
            } else {
                banner = "Voice note saved. The recording was discarded after transcription."
            }
            await refreshReadModels()
        } catch {
            banner = "Voice note failed. Your draft remains on this device."
        }
    }

    public func updateEntryImportance(entryId: String, value: Int?) async {
        do {
            let updated = try await api.updateEntryImportance(id: entryId, value: value)
            if let index = recentEntries.firstIndex(where: { $0.id == entryId }) {
                recentEntries[index] = updated
            }
            banner = value.map { "Importance set to \($0) of 5." } ?? "Importance cleared."
        } catch {
            banner = "Could not update importance."
        }
    }

    public func updateImportancePrompts(_ enabled: Bool) async {
        do {
            let preferences = try await api.updatePreferences(
                PreferencesUpdateRequest(importancePromptsEnabled: enabled)
            )
            importancePromptsEnabled = preferences.importancePromptsEnabled ?? enabled
            banner = enabled ? "Importance prompts enabled." : "Importance prompts disabled."
        } catch {
            banner = "Could not update importance prompts."
        }
    }

    public func setUsePrivateMemories(_ enabled: Bool) {
        usePrivateMemories = enabled
    }

    public func updatePrivateRecallDefault(_ enabled: Bool) async {
        do {
            let preferences = try await api.updatePreferences(
                PreferencesUpdateRequest(privateEntriesInAsk: enabled)
            )
            usePrivateMemories = preferences.privateEntriesInAsk
            banner = enabled ? "Private memories may inform replies." : "Private memories stay out of replies."
        } catch {
            banner = "Could not update private-memory recall."
        }
    }

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
            banner = "Personal voice archive enabled."
        } catch {
            banner = "Could not enable the voice archive."
        }
    }

    public func disableVoiceArchive() async {
        do {
            voiceArchiveStatus = try await api.disableVoiceArchive()
            banner = "Future voice retention disabled."
        } catch {
            banner = "Could not update voice retention."
        }
    }

    public func deleteVoiceArchive() async {
        do {
            _ = try await api.deleteVoiceArchive()
            await refreshVoiceArchive()
            banner = "Retained voice recordings deleted."
        } catch {
            banner = "Could not delete the voice archive."
        }
    }

    private func refreshPreferences() async {
        guard me != nil, let preferences = try? await api.preferences() else { return }
        responseStyle = preferences.responseStyle ?? "friendly"
        importancePromptsEnabled = preferences.importancePromptsEnabled ?? false
        usePrivateMemories = preferences.privateEntriesInAsk
        aiProcessingConsentAccepted = preferences.legalAcceptances["ai_disclosure"] != nil
    }

    private func refreshInviteStatus() async {
        guard me != nil else {
            inviteStatus = nil
            return
        }
        inviteStatus = try? await api.inviteStatus()
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
                banner = "Invite accepted. Welcome to Thought Pins."
                await refreshPreferences()
                await refreshReadModels()
            }
        } catch {
            // The server never says which part was wrong, and neither does this.
            banner = "That code is not valid. Check it and try again."
            await refreshInviteStatus()
        }
    }

    private func refreshVoiceArchive() async {
        guard me != nil, config?.voiceArchiveEnabled == true else {
            voiceArchiveStatus = nil
            return
        }
        voiceArchiveStatus = try? await api.voiceArchive()
    }

    public func exportAccount() async {
        do {
            let export = try await api.exportAccount()
            banner = "Export ready with \(export.tables.count) data groups."
        } catch {
            banner = "Export failed."
        }
    }

    public func deleteAccount() async {
        do {
            _ = try await api.deleteAccount()
            await clearLocalAccountState()
            banner = "Account deleted."
        } catch {
            banner = "Deletion failed."
        }
    }

    public func logout() async {
        try? await api.logout()
        await clearLocalAccountState()
        banner = "Signed out."
    }

    /// Drops everything the departing account left on this device.
    ///
    /// Queued drafts matter most. They are raw journal text, the store is keyed
    /// by device rather than by account, and `bootstrap` syncs them under
    /// whichever session is current — so a draft surviving sign-out or deletion
    /// is posted into the next account that opens the app here.
    private func clearLocalAccountState() async {
        try? await drafts.purge()
        me = nil
        chatReply = ""
        routeLabel = "chat"
        librarySources = []
        memoryCards = []
        placeCards = []
        recentEntries = []
        voiceArchiveStatus = nil
        pendingVaultImport = nil
        aiProcessingConsentAccepted = false
        inviteStatus = nil
        usePrivateMemories = false
        await refreshDraftCount()
    }

    public func refreshReadModels() async {
        librarySources = (try? await api.librarySources(limit: 20)) ?? librarySources
        memoryCards = (try? await api.memoryCards(section: "people", limit: 12).items) ?? memoryCards
        placeCards = (try? await api.memoryCards(section: "places", limit: 12).items) ?? placeCards
        recentEntries = (try? await api.entries(page: 1, limit: 40).items) ?? recentEntries
    }

    private func refreshDraftCount() async {
        draftCount = ((try? await drafts.list()) ?? []).count
    }
}
