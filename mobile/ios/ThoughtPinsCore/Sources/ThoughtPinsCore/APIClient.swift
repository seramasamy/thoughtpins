import CryptoKit
import Foundation

public actor ThoughtPinsAPIClient {
    private let baseURL: URL
    private let sessionStore: SessionStore
    private let urlSession: URLSession
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    private var refreshTask: Task<ApiSession?, Error>?

    public init(baseURL: URL, sessionStore: SessionStore, urlSession: URLSession? = nil) {
        self.baseURL = baseURL
        self.sessionStore = sessionStore
        self.urlSession = urlSession ?? Self.makeEphemeralSession()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    public func clientConfig() async throws -> ClientConfig {
        try await request(path: "/v1/client-config", method: "GET", auth: false, body: Optional<String>.none)
    }

    public func register(email: String? = nil, phone: String? = nil, password: String) async throws -> RegisterResponse {
        try await request(
            path: "/v1/auth/register",
            method: "POST",
            auth: false,
            body: RegisterRequest(email: email, phone: phone, password: password)
        )
    }

    public func login(identifier: String, password: String) async throws -> ApiSession {
        let response: TokenResponse = try await request(
            path: "/v1/auth/login",
            method: "POST",
            auth: false,
            body: LoginRequest(identifier: identifier, password: password)
        )
        let session = ApiSession(accessToken: response.accessToken, refreshToken: response.refreshToken)
        try sessionStore.save(session)
        return session
    }

    public func login(email: String, password: String) async throws -> ApiSession {
        try await login(identifier: email, password: password)
    }

    public func login(phone: String, password: String) async throws -> ApiSession {
        try await login(identifier: phone, password: password)
    }

    public func oauthLogin(
        provider: String,
        idToken: String,
        displayName: String? = nil,
        authorizationCode: String? = nil,
        redirectUri: String? = nil,
        nonce: String? = nil
    ) async throws -> ApiSession {
        let response: TokenResponse = try await request(
            path: "/v1/auth/oauth",
            method: "POST",
            auth: false,
            body: OAuthLoginRequest(
                provider: provider,
                idToken: idToken,
                displayName: displayName,
                authorizationCode: authorizationCode,
                redirectUri: redirectUri,
                nonce: nonce
            )
        )
        let session = ApiSession(accessToken: response.accessToken, refreshToken: response.refreshToken)
        try sessionStore.save(session)
        return session
    }

    public func logout() async throws {
        guard let current = try sessionStore.load() else {
            return
        }
        let serverResult: Result<StatusResponse, Error>
        do {
            let response: StatusResponse = try await request(
                path: "/v1/auth/logout",
                method: "POST",
                auth: false,
                body: RefreshRequest(refreshToken: current.refreshToken)
            )
            serverResult = .success(response)
        } catch {
            serverResult = .failure(error)
        }
        // A network outage must not leave a user signed in on a shared device.
        try sessionStore.save(nil)
        _ = try serverResult.get()
    }

    public func me() async throws -> MeResponse {
        try await request(path: "/v1/me", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func chat(
        text: String,
        conversationId: String = "main",
        surface: String = "ios",
        messageId: String? = nil,
        includePrivate: Bool? = nil,
        confirmAction: Bool? = nil,
        pendingActionId: String? = nil
    ) async throws -> ChatResponse {
        let resolvedMessageId = messageId ?? UUID().uuidString
        return try await request(
            path: "/v1/chat",
            method: "POST",
            auth: true,
            body: ChatRequest(
                text: text,
                conversationId: conversationId,
                surface: surface,
                messageId: resolvedMessageId,
                includePrivate: includePrivate,
                confirmAction: confirmAction,
                pendingActionId: pendingActionId
            ),
            idempotencyKey: resolvedMessageId,
            // A model round trip is not an ordinary request. Measured against
            // production: 13.3s, 12.6s, 21.8s. The 30s default left so little
            // headroom that a Release run of the feature sweep timed out on a
            // question that worked; on a phone network it would be routine.
            timeout: ThoughtPinsAPIClient.chatTimeout
        )
    }

    /// How long a model round trip is allowed to take.
    ///
    /// Deliberately generous, and deliberately not the global timeout: the
    /// 30-second default is what lets the app tell an unreachable server from a
    /// slow one, which is what the offline draft queue depends on.
    public static let chatTimeout: TimeInterval = 90

    public func chatConversations(page: Int = 1, limit: Int = 20) async throws -> ChatConversationsPageResponse {
        try await request(
            path: "/v1/chat/conversations",
            method: "GET",
            auth: true,
            queryItems: [URLQueryItem(name: "page", value: String(page)), URLQueryItem(name: "limit", value: String(limit))],
            body: Optional<String>.none
        )
    }

    public func chatMessages(conversationId: String, page: Int = 1, limit: Int = 80) async throws -> ChatMessagesPageResponse {
        try await request(
            path: "/v1/chat/conversations/\(conversationId)/messages",
            method: "GET",
            auth: true,
            queryItems: [URLQueryItem(name: "page", value: String(page)), URLQueryItem(name: "limit", value: String(limit))],
            body: Optional<String>.none
        )
    }

    public func ingest(
        text: String,
        userImportance: Int? = nil,
        idempotencyKey: String? = nil
    ) async throws -> IngestResponse {
        let messageId = idempotencyKey ?? UUID().uuidString
        return try await request(
            path: "/v1/entries",
            method: "POST",
            auth: true,
            body: IngestRequest(text: text, userImportance: userImportance, messageId: messageId),
            idempotencyKey: messageId
        )
    }

    public func entries(page: Int = 1, limit: Int = 20) async throws -> EntriesPageResponse {
        try await request(
            path: "/v1/entries",
            method: "GET",
            auth: true,
            queryItems: [URLQueryItem(name: "page", value: String(page)), URLQueryItem(name: "limit", value: String(limit))],
            body: Optional<String>.none
        )
    }

    public func updateEntryImportance(id: String, value: Int?) async throws -> EntryResponse {
        try await request(
            path: "/v1/entries/\(id)/importance",
            method: "PATCH",
            auth: true,
            body: EntryImportanceRequest(userImportance: value)
        )
    }

    public func deleteEntry(id: String) async throws -> EntryDeleteResponse {
        try await request(path: "/v1/entries/\(id)", method: "DELETE", auth: true, body: Optional<String>.none)
    }

    public func jobs(status: String = "", page: Int = 1, limit: Int = 20) async throws -> JobsPageResponse {
        var query = [URLQueryItem(name: "page", value: String(page)), URLQueryItem(name: "limit", value: String(limit))]
        if !status.isEmpty {
            query.append(URLQueryItem(name: "status", value: status))
        }
        return try await request(path: "/v1/jobs", method: "GET", auth: true, queryItems: query, body: Optional<String>.none)
    }

    public func job(id: String) async throws -> JobResponse {
        try await request(path: "/v1/jobs/\(id)", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func retryJob(id: String) async throws -> JobResponse {
        try await request(path: "/v1/jobs/\(id)/retry", method: "POST", auth: true, body: Optional<String>.none)
    }

    public func cancelJob(id: String) async throws -> JobResponse {
        try await request(path: "/v1/jobs/\(id)/cancel", method: "POST", auth: true, body: Optional<String>.none)
    }

    public func createLibrarySource(
        text: String? = nil,
        url: String? = nil,
        title: String? = nil,
        author: String? = nil,
        sourceType: String = "text"
    ) async throws -> LibraryIngestResponse {
        try await request(
            path: "/v1/library",
            method: "POST",
            auth: true,
            body: LibraryIngestRequest(text: text, url: url, title: title, author: author, sourceType: sourceType)
        )
    }

    public func librarySources(limit: Int = 50) async throws -> [LibrarySourceResponse] {
        try await request(
            path: "/v1/library",
            method: "GET",
            auth: true,
            queryItems: [URLQueryItem(name: "limit", value: String(limit))],
            body: Optional<String>.none
        )
    }

    public func librarySource(sourceRef: String) async throws -> LibrarySourceResponse {
        try await request(path: "/v1/library/\(sourceRef)", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func memoryCards(section: String = "people", query: String = "", limit: Int = 24) async throws -> MemoryCardsResponse {
        try await request(
            path: "/v1/memory/cards",
            method: "GET",
            auth: true,
            queryItems: [
                URLQueryItem(name: "section", value: section),
                URLQueryItem(name: "q", value: query),
                URLQueryItem(name: "limit", value: String(limit)),
            ],
            body: Optional<String>.none
        )
    }

    public func memoryCard(id: String) async throws -> MemoryCardDetailResponse {
        try await request(path: "/v1/memory/cards/\(id)", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func status() async throws -> StatsResponse {
        try await request(path: "/v1/status", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func deepHealth() async throws -> DeepHealthResponse {
        try await request(path: "/v1/health/deep", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func uploadFile(
        filename: String,
        contentBase64: String,
        mediaType: String? = nil,
        destination: String = "auto",
        caption: String? = nil,
        title: String? = nil,
        sourceType: String? = nil,
        conversationId: String = "uploads"
    ) async throws -> UploadIngestResponse {
        try await request(
            path: "/v1/uploads",
            method: "POST",
            auth: true,
            body: UploadRequest(
                filename: filename,
                contentBase64: contentBase64,
                mediaType: mediaType,
                destination: destination,
                caption: caption,
                title: title,
                sourceType: sourceType,
                surface: "ios",
                conversationId: conversationId
            )
        )
    }

    public func importObsidianVault(
        filename: String,
        contentBase64: String,
        mode: String = "auto",
        dryRun: Bool = false
    ) async throws -> VaultImportResponse {
        try await request(
            path: "/v1/import/obsidian",
            method: "POST",
            auth: true,
            body: VaultImportRequest(
                filename: filename,
                contentBase64: contentBase64,
                mode: mode,
                dryRun: dryRun
            )
        )
    }

    public func importObsidianVaultResumable(
        filename: String,
        contentBase64: String,
        mode: String = "auto",
        conflictPolicy: String = "skip"
    ) async throws -> VaultImportResponse {
        let preview = try await previewObsidianVaultResumable(
            filename: filename,
            contentBase64: contentBase64,
            mode: mode,
            conflictPolicy: conflictPolicy
        )
        return try await applyPreviewedVaultImport(
            transferId: preview.id,
            conflictPolicy: preview.conflictPolicy
        )
    }

    public func previewObsidianVaultResumable(
        filename: String,
        contentBase64: String,
        mode: String = "auto",
        conflictPolicy: String = "skip"
    ) async throws -> VaultImportSessionResponse {
        guard let archive = Data(base64Encoded: contentBase64), !archive.isEmpty else {
            throw APIClientError.invalidResponse
        }
        var transfer = try await createVaultImportUpload(
            filename: filename,
            expectedBytes: archive.count,
            mode: mode,
            conflictPolicy: conflictPolicy
        )
        do {
            let chunkBytes = 512 * 1024
            while transfer.receivedBytes < archive.count {
                try Task.checkCancellation()
                let start = transfer.receivedBytes
                let end = min(archive.count, start + chunkBytes)
                let chunk = archive.subdata(in: start..<end)
                let digest = SHA256.hash(data: chunk).map { String(format: "%02x", $0) }.joined()
                transfer = try await appendVaultImportChunk(
                    transferId: transfer.id,
                    offset: start,
                    contentBase64: chunk.base64EncodedString(),
                    chunkSha256: digest
                )
            }
            transfer = try await previewVaultImport(transferId: transfer.id, conflictPolicy: conflictPolicy)
            return try await waitForVaultImport(transfer.id, target: "preview_ready")
        } catch {
            _ = try? await cancelVaultImport(transferId: transfer.id)
            throw error
        }
    }

    public func applyPreviewedVaultImport(
        transferId: String,
        conflictPolicy: String
    ) async throws -> VaultImportResponse {
        _ = try await applyVaultImport(transferId: transferId, conflictPolicy: conflictPolicy)
        let transfer = try await waitForVaultImport(transferId, target: "completed")
        guard let result = transfer.result else { throw APIClientError.invalidResponse }
        return result
    }

    public func createVaultImportUpload(
        filename: String,
        expectedBytes: Int,
        mode: String = "auto",
        conflictPolicy: String = "skip"
    ) async throws -> VaultImportSessionResponse {
        try await request(
            path: "/v1/import/obsidian/uploads",
            method: "POST",
            auth: true,
            body: VaultUploadCreateRequest(
                filename: filename,
                expectedBytes: expectedBytes,
                mode: mode,
                conflictPolicy: conflictPolicy
            )
        )
    }

    public func appendVaultImportChunk(
        transferId: String,
        offset: Int,
        contentBase64: String,
        chunkSha256: String
    ) async throws -> VaultImportSessionResponse {
        try await request(
            path: "/v1/import/obsidian/uploads/\(transferId)/chunks",
            method: "PUT",
            auth: true,
            body: VaultUploadChunkRequest(offset: offset, contentBase64: contentBase64, chunkSha256: chunkSha256),
            idempotencyKey: "vault-chunk-\(transferId)-\(offset)-\(chunkSha256.prefix(16))"
        )
    }

    public func vaultImportSession(transferId: String) async throws -> VaultImportSessionResponse {
        try await request(
            path: "/v1/import/obsidian/uploads/\(transferId)",
            method: "GET",
            auth: true,
            body: Optional<String>.none
        )
    }

    public func previewVaultImport(
        transferId: String,
        conflictPolicy: String
    ) async throws -> VaultImportSessionResponse {
        try await request(
            path: "/v1/import/obsidian/uploads/\(transferId)/preview",
            method: "POST",
            auth: true,
            body: VaultImportOperationRequest(conflictPolicy: conflictPolicy)
        )
    }

    public func applyVaultImport(
        transferId: String,
        conflictPolicy: String
    ) async throws -> VaultImportSessionResponse {
        try await request(
            path: "/v1/import/obsidian/uploads/\(transferId)/apply",
            method: "POST",
            auth: true,
            body: VaultImportOperationRequest(conflictPolicy: conflictPolicy)
        )
    }

    public func cancelVaultImport(transferId: String) async throws -> VaultImportSessionResponse {
        try await request(
            path: "/v1/import/obsidian/uploads/\(transferId)/cancel",
            method: "POST",
            auth: true,
            body: Optional<String>.none
        )
    }

    private func waitForVaultImport(_ transferId: String, target: String) async throws -> VaultImportSessionResponse {
        for _ in 0..<2_400 {
            try Task.checkCancellation()
            let transfer = try await vaultImportSession(transferId: transferId)
            if transfer.status == target { return transfer }
            if ["failed", "canceled", "expired"].contains(transfer.status) {
                throw APIClientError.httpStatus(409, transfer.error ?? "Vault import ended with status \(transfer.status)")
            }
            try await Task.sleep(nanoseconds: 500_000_000)
        }
        throw APIClientError.httpStatus(408, "Vault import did not finish before the client timeout")
    }

    // Both stay reachable for an account the gate has not admitted: the server
    // exempts /v1/invites/* precisely so somebody who cannot use the product yet
    // can still find out why and redeem a code.
    public func inviteStatus() async throws -> InviteStatusResponse {
        try await request(path: "/v1/invites/status", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func redeemInvite(code: String) async throws -> InviteStatusResponse {
        try await request(
            path: "/v1/invites/redeem",
            method: "POST",
            auth: true,
            body: InviteRedeemRequest(code: code.trimmingCharacters(in: .whitespacesAndNewlines))
        )
    }

    public func preferences() async throws -> PreferencesResponse {
        try await request(path: "/v1/preferences", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func updatePreferences(_ preferences: PreferencesUpdateRequest) async throws -> PreferencesResponse {
        try await request(path: "/v1/preferences", method: "PATCH", auth: true, body: preferences)
    }

    public func voiceArchive() async throws -> VoiceArchiveStatusResponse {
        try await request(path: "/v1/voice-archive", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func enableVoiceArchive(_ consent: VoiceArchiveConsentRequest) async throws -> VoiceArchiveStatusResponse {
        try await request(path: "/v1/voice-archive/consent", method: "POST", auth: true, body: consent)
    }

    public func disableVoiceArchive() async throws -> VoiceArchiveStatusResponse {
        try await request(path: "/v1/voice-archive/consent", method: "DELETE", auth: true, body: Optional<String>.none)
    }

    public func deleteVoiceArchive() async throws -> VoiceArchiveDeleteResponse {
        try await request(
            path: "/v1/voice-archive",
            method: "DELETE",
            auth: true,
            body: VoiceArchiveDeleteRequest(confirm: "DELETE VOICE ARCHIVE")
        )
    }

    public func acceptLegalDocument(_ document: String, version: String) async throws -> PreferencesResponse {
        try await request(path: "/v1/legal/acceptances", method: "POST", auth: true, body: LegalAcceptanceRequest(document: document, version: version))
    }

    public func createSafetyReport(_ report: SafetyReportRequest) async throws -> SafetyReportResponse {
        try await request(path: "/v1/safety/reports", method: "POST", auth: true, body: report)
    }

    public func devices() async throws -> DevicesPageResponse {
        try await request(path: "/v1/devices", method: "GET", auth: true, body: Optional<String>.none)
    }

    @discardableResult
    public func registerDevice(_ device: DeviceRegistration) async throws -> DeviceResponse {
        try await request(path: "/v1/devices", method: "POST", auth: true, body: device)
    }

    public func revokeDevice(installationId: String) async throws -> DeviceResponse {
        try await request(path: "/v1/devices/\(installationId)", method: "DELETE", auth: true, body: Optional<String>.none)
    }

    public func sessions() async throws -> SessionsPageResponse {
        try await request(path: "/v1/sessions", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func revokeSession(id: String) async throws -> SessionResponse {
        try await request(path: "/v1/sessions/\(id)", method: "DELETE", auth: true, body: Optional<String>.none)
    }

    public func revokeOtherSessions() async throws -> SessionRevocationResponse {
        try await request(path: "/v1/sessions/revoke-others", method: "POST", auth: true, body: Optional<String>.none)
    }

    public func exportAccount() async throws -> AccountExportResponse {
        try await request(path: "/v1/export", method: "GET", auth: true, body: Optional<String>.none)
    }

    public func deleteAccount() async throws -> AccountDeletionResponse {
        let response: AccountDeletionResponse = try await request(path: "/v1/me", method: "DELETE", auth: true, body: DeleteAccountRequest(confirm: "DELETE"))
        try sessionStore.save(nil)
        return response
    }

    public func syncQueuedDrafts(from store: FileDraftStore) async throws -> DraftSyncSummary {
        let allDrafts = try await store.list()
        let pending = allDrafts.filter { $0.status == .queued || $0.status == .failed }
        var results: [DraftSyncResult] = []
        for var draft in pending {
            draft.status = .submitting
            draft.attemptCount += 1
            draft.lastError = nil
            draft.updatedAtUtc = Date()
            try await store.update(draft)
            do {
                let response = try await ingest(text: draft.text, idempotencyKey: draft.id)
                draft.status = .synced
                draft.entryId = response.entryId
                draft.jobId = response.jobId
                draft.updatedAtUtc = Date()
                try await store.update(draft)
                results.append(DraftSyncResult(draftId: draft.id, status: .synced, entryId: response.entryId, jobId: response.jobId, error: nil))
            } catch {
                draft.status = .failed
                draft.lastError = String(describing: error)
                draft.updatedAtUtc = Date()
                try await store.update(draft)
                results.append(DraftSyncResult(draftId: draft.id, status: .failed, entryId: nil, jobId: nil, error: draft.lastError))
            }
        }
        return DraftSyncSummary(results: results)
    }

    private func request<T: Decodable, Body: Encodable>(
        path: String,
        method: String,
        auth: Bool,
        queryItems: [URLQueryItem] = [],
        body: Body?,
        idempotencyKey: String? = nil,
        allowRefresh: Bool = true,
        timeout: TimeInterval? = nil
    ) async throws -> T {
        let mutationMethods = ["POST", "PUT", "PATCH", "DELETE"]
        let resolvedIdempotencyKey = idempotencyKey ?? (auth && mutationMethods.contains(method) ? UUID().uuidString : nil)
        var request = URLRequest(url: makeURL(path: path, queryItems: queryItems))
        request.httpMethod = method
        if let timeout {
            request.timeoutInterval = timeout
        }
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        request.setValue("no-cache", forHTTPHeaderField: "Pragma")
        request.setValue(UUID().uuidString, forHTTPHeaderField: "X-Request-ID")
        if auth, let session = try sessionStore.load() {
            request.setValue("Bearer \(session.accessToken)", forHTTPHeaderField: "Authorization")
        }
        if let resolvedIdempotencyKey {
            request.setValue(resolvedIdempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        }
        if let body {
            request.httpBody = try encoder.encode(body)
        }

        let (data, response) = try await urlSession.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }
        if http.statusCode == 401, auth {
            if allowRefresh {
                let refreshed: Bool
                do {
                    refreshed = try await refreshSession()
                } catch APIClientError.httpStatus(let refreshStatus, _)
                    where refreshStatus == 401 || refreshStatus == 403 {
                    // The server has rejected the refresh token itself. Nothing
                    // this session holds will ever work again, and leaving it in
                    // the Keychain left the app in a signed-in shell where every
                    // request failed and the only way out was finding Sign out.
                    // A 5xx during refresh is transient and deliberately not
                    // caught here: that session may still be good.
                    try? sessionStore.save(nil)
                    throw APIClientError.sessionExpired
                }
                if refreshed {
                    return try await self.request(
                        path: path,
                        method: method,
                        auth: auth,
                        queryItems: queryItems,
                        body: body,
                        idempotencyKey: resolvedIdempotencyKey,
                        allowRefresh: false
                    )
                }
            } else {
                // A 401 while carrying a token we refreshed moments ago. The
                // refresh succeeded and the result is still unauthorised, so the
                // account is gone or revoked server-side.
                try? sessionStore.save(nil)
                throw APIClientError.sessionExpired
            }
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIClientError.httpStatus(http.statusCode, sanitizedErrorMessage(from: data))
        }
        if T.self == EmptyResponse.self {
            return EmptyResponse() as! T
        }
        return try decoder.decode(T.self, from: data)
    }

    private func makeURL(path: String, queryItems: [URLQueryItem] = []) -> URL {
        let resourcePath = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let url = baseURL.appendingPathComponent(resourcePath)
        guard !queryItems.isEmpty, var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return url
        }
        components.queryItems = queryItems
        return components.url ?? url
    }

    private func refreshSession() async throws -> Bool {
        if let refreshTask {
            return try await refreshTask.value != nil
        }
        guard let current = try sessionStore.load() else {
            return false
        }
        let task = Task<ApiSession?, Error> {
            var request = URLRequest(url: self.makeURL(path: "/v1/auth/refresh"))
            request.httpMethod = "POST"
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
            request.setValue(UUID().uuidString, forHTTPHeaderField: "X-Request-ID")
            let encoder = JSONEncoder()
            encoder.keyEncodingStrategy = .convertToSnakeCase
            request.httpBody = try encoder.encode(RefreshRequest(refreshToken: current.refreshToken))
            let (data, response) = try await self.urlSession.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw APIClientError.invalidResponse
            }
            guard (200..<300).contains(http.statusCode) else {
                throw APIClientError.httpStatus(http.statusCode, self.sanitizedErrorMessage(from: data))
            }
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            let tokens = try decoder.decode(TokenResponse.self, from: data)
            let session = ApiSession(accessToken: tokens.accessToken, refreshToken: tokens.refreshToken)
            // Stored here, inside the task, and not by whoever happens to be
            // awaiting it. When the task finishes, the owner and every waiter
            // become runnable in an unspecified order, and a waiter resuming
            // first went straight back into request() -- a same-actor call, so
            // no suspension -- and read the old access token for its retry.
            // That retry carries allowRefresh: false, so it could not recover:
            // one concurrent 401 out of several surfaced as a spurious auth
            // failure. Saving before the task returns removes the window.
            try self.sessionStore.save(session)
            return session
        }
        refreshTask = task
        do {
            let refreshed = try await task.value
            refreshTask = nil
            return refreshed != nil
        } catch {
            refreshTask = nil
            throw error
        }
    }

    private func sanitizedErrorMessage(from data: Data) -> String? {
        guard
            data.count <= 64 * 1024,
            let envelope = try? decoder.decode(APIErrorEnvelope.self, from: data)
        else {
            return nil
        }
        let message = envelope.error.message.trimmingCharacters(in: .whitespacesAndNewlines)
        return message.isEmpty ? nil : String(message.prefix(512))
    }

    private nonisolated static func makeEphemeralSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        // Fail fast rather than wait for the network to come back.
        //
        // waitsForConnectivity made an unreachable server indistinguishable from
        // a slow one for a full minute: sign-in sat with no result, and after
        // launch the app showed empty screens with nothing saying why, which is
        // the app implying it has loaded when it has not. Queueing is this app's
        // answer to no network -- a draft is written locally and sent later --
        // and that only works if the request admits it failed.
        configuration.waitsForConnectivity = false
        // 30s suits the ordinary reads and writes. It does not suit a model
        // round trip: measured against production on 2026-08-27, /v1/chat took
        // 13.3s, 12.6s and 21.8s on a healthy desktop connection, and a Release
        // build of the feature sweep hit the timeout on a normal question. Add
        // a phone's network on top and "That took too long" becomes a routine
        // answer to a working request.
        //
        // Raising it globally is the wrong fix: this timeout is what makes an
        // unreachable server distinguishable from a slow one, which is what the
        // offline draft queue depends on. So chat asks for more, per request.
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 60
        return URLSession(configuration: configuration)
    }
}

public struct EmptyResponse: Codable, Sendable {
    public init() {}
}

public enum APIClientError: Error, Equatable {
    case invalidResponse
    case httpStatus(Int, String?)
    /// The stored session was rejected and has been cleared.
    ///
    /// Distinct from a plain 401 so the app can drop to sign-in instead of
    /// showing a signed-in shell in which everything fails.
    case sessionExpired
}

private struct InviteRedeemRequest: Encodable {
    let code: String
}

private struct RegisterRequest: Encodable {
    let email: String?
    let phone: String?
    let password: String
}

private struct LoginRequest: Encodable {
    let identifier: String
    let password: String
}

private struct OAuthLoginRequest: Encodable {
    let provider: String
    let idToken: String
    let displayName: String?
    let authorizationCode: String?
    let redirectUri: String?
    let nonce: String?
}

private struct RefreshRequest: Encodable {
    let refreshToken: String
}

private struct APIErrorEnvelope: Decodable {
    let error: APIErrorBody
}

private struct APIErrorBody: Decodable {
    let message: String
}

private struct IngestRequest: Encodable {
    let text: String
    let userImportance: Int?
    let messageId: String
}

private struct EntryImportanceRequest: Encodable {
    let userImportance: Int?
}

private struct ChatRequest: Encodable {
    let text: String
    let conversationId: String
    let surface: String
    let messageId: String?
    let includePrivate: Bool?
    let confirmAction: Bool?
    let pendingActionId: String?
}

private struct LibraryIngestRequest: Encodable {
    let text: String?
    let url: String?
    let title: String?
    let author: String?
    let sourceType: String
}

private struct LegalAcceptanceRequest: Encodable {
    let document: String
    let version: String
}

private struct DeleteAccountRequest: Encodable {
    let confirm: String
}

private struct UploadRequest: Encodable {
    let filename: String
    let contentBase64: String
    let mediaType: String?
    let destination: String
    let caption: String?
    let title: String?
    let sourceType: String?
    let surface: String
    let conversationId: String
}

private struct VaultImportRequest: Encodable {
    let filename: String
    let contentBase64: String
    let mode: String
    let dryRun: Bool
}

private struct VaultUploadCreateRequest: Encodable {
    let filename: String
    let expectedBytes: Int
    let mode: String
    let conflictPolicy: String
}

private struct VaultUploadChunkRequest: Encodable {
    let offset: Int
    let contentBase64: String
    let chunkSha256: String
}

private struct VaultImportOperationRequest: Encodable {
    let conflictPolicy: String
}
