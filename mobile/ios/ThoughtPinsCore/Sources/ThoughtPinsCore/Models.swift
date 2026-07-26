import Foundation

public struct ApiSession: Codable, Equatable, Sendable {
    public let accessToken: String
    public let refreshToken: String

    public init(accessToken: String, refreshToken: String) {
        self.accessToken = accessToken
        self.refreshToken = refreshToken
    }
}

public struct TokenResponse: Codable, Sendable {
    public let accessToken: String
    public let refreshToken: String
    public let tokenType: String
    public let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
    }
}

public struct ClientConfig: Codable, Sendable {
    public let appName: String
    public let apiVersion: String
    public let authRequired: Bool
    public let registrationLocked: Bool
    public let oauthGoogleEnabled: Bool?
    public let oauthAppleEnabled: Bool?
    public let voiceArchiveEnabled: Bool?
    public let memoryContextMode: String?
    public let privacyPolicyUrl: String?
    public let termsUrl: String?
    public let supportUrl: String?
    public let accountDeletionUrl: String?
    public let aiDisclosureUrl: String?
    public let legalDocumentVersion: String?
    public let minimumSupportedClients: [String: String]
    public let recommendedClients: [String: String]
    public let storeUrls: [String: String?]
    public let maintenanceMode: Bool
    public let maintenanceMessage: String?
    public let maintenanceRetryAfterSeconds: Int?
    public let maintenanceAllowReads: Bool

    enum CodingKeys: String, CodingKey {
        case appName = "app_name"
        case apiVersion = "api_version"
        case authRequired = "auth_required"
        case registrationLocked = "registration_locked"
        case oauthGoogleEnabled = "oauth_google_enabled"
        case oauthAppleEnabled = "oauth_apple_enabled"
        case voiceArchiveEnabled = "voice_archive_enabled"
        case memoryContextMode = "memory_context_mode"
        case privacyPolicyUrl = "privacy_policy_url"
        case termsUrl = "terms_url"
        case supportUrl = "support_url"
        case accountDeletionUrl = "account_deletion_url"
        case aiDisclosureUrl = "ai_disclosure_url"
        case legalDocumentVersion = "legal_document_version"
        case minimumSupportedClients = "minimum_supported_clients"
        case recommendedClients = "recommended_clients"
        case storeUrls = "store_urls"
        case maintenanceMode = "maintenance_mode"
        case maintenanceMessage = "maintenance_message"
        case maintenanceRetryAfterSeconds = "maintenance_retry_after_seconds"
        case maintenanceAllowReads = "maintenance_allow_reads"
    }
}

public struct IngestResponse: Codable, Sendable {
    public let status: String
    public let entryId: String
    public let jobId: String?
    public let userImportance: Int?

    enum CodingKeys: String, CodingKey {
        case status
        case entryId = "entry_id"
        case jobId = "job_id"
        case userImportance = "user_importance"
    }
}

public struct UploadIngestResponse: Codable, Sendable {
    public let status: String
    public let routeType: String
    public let filename: String
    public let mediaKind: String
    public let destination: String
    public let extractionStatus: String
    public let extractedChars: Int
    public let attachmentSaved: Bool
    public let attachmentRef: String?
    public let voiceAssetId: String?
    public let title: String?
    public let entryId: String?
    public let jobId: String?
    public let documentId: String?
    public let error: String?
}

public struct VaultImportResponse: Codable, Sendable {
    public let status: String
    public let format: String
    public let mode: String
    public let thoughtpinsExport: Bool
    public let dryRun: Bool
    public let archiveSha256: String
    public let filesDiscovered: Int
    public let notesDiscovered: Int
    public let attachmentsSkipped: Int
    public let structuralFilesSkipped: Int
    public let canvasesDiscovered: Int
    public let canvasDocumentsImported: Int
    public let journalNotes: Int
    public let libraryNotes: Int
    public let journalJobsQueued: Int
    public let libraryDocumentsImported: Int
    public let newNotes: Int
    public let changedNotes: Int
    public let unchangedNotes: Int
    public let conflicts: Int
    public let duplicates: Int
    public let skipped: Int
    public let imported: Int
    public let warnings: [String]
    public let errors: [String]
    public let jobIds: [String]
    public let documentIds: [String]
    public let previewItems: [VaultImportPreviewItem]
}

public struct VaultImportPreviewItem: Codable, Sendable {
    public let path: String
    public let title: String
    public let kind: String
    public let state: String
    public let action: String
}

public struct VaultImportSessionResponse: Codable, Sendable {
    public let id: String
    public let status: String
    public let operation: String?
    public let filename: String
    public let mode: String
    public let conflictPolicy: String
    public let expectedBytes: Int
    public let receivedBytes: Int
    public let archiveSha256: String?
    public let progressCurrent: Int
    public let progressTotal: Int
    public let progressPercent: Double
    public let progressStage: String
    public let cancelRequested: Bool
    public let result: VaultImportResponse?
    public let error: String?
    public let createdAtUtc: String?
    public let updatedAtUtc: String?
    public let finishedAtUtc: String?
    public let expiresAtUtc: String?
}

public struct DeviceRegistration: Codable, Sendable {
    public let installationId: String
    public let platform: String
    public let deviceName: String?
    public let appVersion: String?
    public let buildNumber: String?
    public let osVersion: String?
    public let locale: String?
    public let timezone: String?
    public let pushProvider: String?
    public let pushToken: String?
    public let notificationsEnabled: Bool

    public init(
        installationId: String,
        platform: String = "ios",
        deviceName: String?,
        appVersion: String?,
        buildNumber: String?,
        osVersion: String?,
        locale: String?,
        timezone: String?,
        pushProvider: String?,
        pushToken: String?,
        notificationsEnabled: Bool
    ) {
        self.installationId = installationId
        self.platform = platform
        self.deviceName = deviceName
        self.appVersion = appVersion
        self.buildNumber = buildNumber
        self.osVersion = osVersion
        self.locale = locale
        self.timezone = timezone
        self.pushProvider = pushProvider
        self.pushToken = pushToken
        self.notificationsEnabled = notificationsEnabled
    }

    enum CodingKeys: String, CodingKey {
        case installationId = "installation_id"
        case platform
        case deviceName = "device_name"
        case appVersion = "app_version"
        case buildNumber = "build_number"
        case osVersion = "os_version"
        case locale
        case timezone
        case pushProvider = "push_provider"
        case pushToken = "push_token"
        case notificationsEnabled = "notifications_enabled"
    }
}

public struct MemoryCardMemoryResponse: Codable, Sendable {
    public let id: String?
    public let entryId: String?
    public let date: String?
    public let type: String
    public let text: String
    public let confidence: String?
}

public struct MemoryCardRelationshipResponse: Codable, Sendable {
    public let type: String
    public let other: String
    public let confidence: String?
    public let evidenceCount: Int
}

public struct MemoryCardSourceResponse: Codable, Sendable {
    public let id: String
    public let title: String
    public let sourceType: String
    public let status: String
    public let sourceUrl: String?
    public let obsidianPath: String?
}

public struct MemoryCardTimelineResponse: Codable, Sendable {
    public let date: String?
    public let label: String
    public let source: String?
}

public struct MemoryCardProvenance: Codable, Sendable {
    public let kind: String?
    public let confidence: String?
    public let sensitivity: String?
    public let entityId: String?
    public let eventId: String?
    public let sourceEntryId: String?
    public let createdAtUtc: String?
    public let updatedAtUtc: String?
}

public struct MemoryCardResponse: Codable, Sendable {
    public let id: String
    public let name: String
    public let type: String
    public let subtitle: String?
    public let aliases: [String]
    public let memoryCount: Int
    public let mentionCount: Int
    public let relationshipCount: Int
    public let firstSeenAtUtc: String?
    public let lastSeen: String?
    public let recentMemories: [MemoryCardMemoryResponse]
    public let relationships: [MemoryCardRelationshipResponse]
    public let sourceDocuments: [MemoryCardSourceResponse]
    public let timeline: [MemoryCardTimelineResponse]
    public let provenance: MemoryCardProvenance?
    public let askPrompt: String?
    public let obsidianPath: String?
}

public struct MemoryCardsResponse: Codable, Sendable {
    public let section: String
    public let query: String
    public let sections: [String: [String]]
    public let items: [MemoryCardResponse]
    public let total: Int
}

public struct MemoryCardEntryResponse: Codable, Sendable {
    public let id: String
    public let createdAtUtc: String?
    public let localDate: String?
    public let source: String
    public let rawText: String
    public let processedStatus: String
}

public struct MemoryCardDetailResponse: Codable, Sendable {
    public let id: String
    public let name: String
    public let type: String
    public let subtitle: String?
    public let aliases: [String]
    public let memoryCount: Int
    public let mentionCount: Int
    public let relationshipCount: Int
    public let firstSeenAtUtc: String?
    public let lastSeen: String?
    public let recentMemories: [MemoryCardMemoryResponse]
    public let relationships: [MemoryCardRelationshipResponse]
    public let sourceDocuments: [MemoryCardSourceResponse]
    public let timeline: [MemoryCardTimelineResponse]
    public let provenance: MemoryCardProvenance?
    public let askPrompt: String?
    public let obsidianPath: String?
    public let allMemories: [MemoryCardMemoryResponse]
    public let entries: [MemoryCardEntryResponse]
}

public struct CaptureDraft: Codable, Equatable, Sendable {
    public enum Status: String, Codable, Sendable {
        case draft
        case queued
        case submitting
        case failed
        case synced
    }

    public let id: String
    public var text: String
    public var status: Status
    public let createdAtUtc: Date
    public var updatedAtUtc: Date
    public var attemptCount: Int
    public var lastError: String?
    public var entryId: String?
    public var jobId: String?
}

public enum JSONValue: Codable, Equatable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            self = .object(try container.decode([String: JSONValue].self))
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }
}

public struct RegisterResponse: Codable, Sendable {
    public let status: String
    public let userId: String
    public let apiKey: String?
}

public struct StatusResponse: Codable, Sendable {
    public let status: String
}

public struct MeResponse: Codable, Sendable {
    public let id: String
    public let email: String?
    public let phone: String?
    public let displayName: String?
    public let isAdmin: Bool
    public let authMethod: String
    public let createdAtUtc: String?
    public let lastLoginUtc: String?
}

public struct ChatResponse: Codable, Sendable {
    public let status: String
    public let routeType: String
    public let reply: String
    public let entryId: String?
    public let jobId: String?
    public let documentId: String?
    public let requiresConfirmation: Bool
    public let confirmationPrompt: String?
    public let contextSizeChars: Int
    public let metadata: [String: JSONValue]
}

public struct ChatConversationResponse: Codable, Sendable {
    public let id: String
    public let conversationKey: String
    public let surface: String
    public let title: String?
    public let createdAtUtc: String?
    public let updatedAtUtc: String?
    public let lastMessageAtUtc: String?
}

public struct ChatConversationsPageResponse: Codable, Sendable {
    public let items: [ChatConversationResponse]
    public let page: Int
    public let limit: Int
    public let total: Int
    public let hasNext: Bool
    public let nextCursor: String?
}

public struct ChatMessageResponse: Codable, Sendable {
    public let id: String
    public let conversationId: String
    public let role: String
    public let text: String
    public let routeType: String?
    public let status: String?
    public let entryId: String?
    public let jobId: String?
    public let documentId: String?
    public let createdAtUtc: String?
    public let metadata: [String: JSONValue]
}

public struct ChatMessagesPageResponse: Codable, Sendable {
    public let items: [ChatMessageResponse]
    public let page: Int
    public let limit: Int
    public let total: Int
    public let hasNext: Bool
    public let nextCursor: String?
}

public struct EntryResponse: Codable, Sendable {
    public let id: String
    public let createdAtUtc: String
    public let localDate: String?
    public let localTime: String?
    public let source: String
    public let rawText: String
    public let sensitivity: String
    public let processedStatus: String
    public let processingError: String?
    public let userImportance: Int?
    public let importanceSource: String?
    public let importanceUpdatedAt: String?
}

public struct EntriesPageResponse: Codable, Sendable {
    public let items: [EntryResponse]
    public let page: Int
    public let limit: Int
    public let total: Int
    public let hasNext: Bool
    public let nextCursor: String?
}

public struct EntryDeleteResponse: Codable, Sendable {
    public let status: String
    public let entryId: String
}

public struct LibraryIngestResponse: Codable, Sendable {
    public let documentId: String
    public let rawEntryId: String
    public let title: String
    public let sourceType: String
    public let status: String
    public let chunks: Int
    public let memories: Int
    public let sourceUrl: String?
    public let duplicate: Bool
    public let error: String?
    public let accessMethod: String?
    public let rightsBasis: String?
    public let paywallDetected: Bool
}

public struct LibrarySourceResponse: Codable, Sendable {
    public let id: String
    public let title: String
    public let sourceType: String
    public let status: String
    public let sourceUrl: String?
    public let originalUrl: String?
    public let canonicalUrl: String?
    public let sourceDomain: String?
    public let author: String?
    public let publishedAt: String?
    public let publisher: String?
    public let topics: [String]?
    public let keyConcepts: [String]?
    public let accessMethod: String?
    public let rightsBasis: String?
    public let fetchStatus: String?
    public let paywallDetected: Bool
    public let retrievalQualityScore: Double?
    public let summary: String?
    public let createdAtUtc: String?
    public let chunks: Int
}

public struct JobResponse: Codable, Sendable {
    public let id: String
    public let status: String
    public let entryId: String?
    public let error: String?
    public let createdAtUtc: String?
    public let startedAtUtc: String?
    public let finishedAtUtc: String?
}

public struct JobsPageResponse: Codable, Sendable {
    public let items: [JobResponse]
    public let page: Int
    public let limit: Int
    public let total: Int
    public let hasNext: Bool
    public let nextCursor: String?
}

public struct StatsResponse: Codable, Sendable {
    public let rawEntries: Int
    public let entities: Int
    public let memories: Int
    public let relationships: Int
    public let events: Int
    public let actionItems: Int
    public let expenses: Int
    public let sources: Int
    public let uptimeSeconds: Double
    public let vaultFiles: Int
}

public struct DeepHealthResponse: Codable, Sendable {
    public let status: String
    public let uptimeSeconds: Double
    public let version: String
    public let checks: [String: [String: JSONValue]]
}

public struct LegalAcceptance: Codable, Sendable {
    public let version: String
    public let acceptedAtUtc: String
}

public struct PreferencesResponse: Codable, Sendable {
    public let notificationsEnabled: Bool
    public let reminderHourLocal: Int?
    public let timezone: String?
    public let privateEntriesInAsk: Bool
    public let weeklyDigestEnabled: Bool
    public let productUpdatesEnabled: Bool
    public let preferredName: String?
    public let responseStyle: String?
    public let importancePromptsEnabled: Bool?
    public let legalAcceptances: [String: LegalAcceptance]
    public let updatedAtUtc: String?
}

public struct PreferencesUpdateRequest: Codable, Sendable {
    public let notificationsEnabled: Bool?
    public let reminderHourLocal: Int?
    public let timezone: String?
    public let privateEntriesInAsk: Bool?
    public let weeklyDigestEnabled: Bool?
    public let productUpdatesEnabled: Bool?
    public let preferredName: String?
    public let responseStyle: String?
    public let importancePromptsEnabled: Bool?

    public init(
        notificationsEnabled: Bool? = nil,
        reminderHourLocal: Int? = nil,
        timezone: String? = nil,
        privateEntriesInAsk: Bool? = nil,
        weeklyDigestEnabled: Bool? = nil,
        productUpdatesEnabled: Bool? = nil,
        preferredName: String? = nil,
        responseStyle: String? = nil,
        importancePromptsEnabled: Bool? = nil
    ) {
        self.notificationsEnabled = notificationsEnabled
        self.reminderHourLocal = reminderHourLocal
        self.timezone = timezone
        self.privateEntriesInAsk = privateEntriesInAsk
        self.weeklyDigestEnabled = weeklyDigestEnabled
        self.productUpdatesEnabled = productUpdatesEnabled
        self.preferredName = preferredName
        self.responseStyle = responseStyle
        self.importancePromptsEnabled = importancePromptsEnabled
    }
}

public struct VoiceArchiveStatusResponse: Codable, Sendable {
    public let enabled: Bool
    public let consentVersion: String?
    public let currentConsentVersion: String
    public let consentedAtUtc: String?
    public let assetCount: Int
    public let originalBytes: Int
    public let storedBytes: Int
    public let defaultProcessing: String
    public let retentionPurpose: String
    public let derivedVoiceDataCreated: Bool
}

public struct VoiceArchiveConsentRequest: Codable, Sendable {
    public let retainRecordings: Bool
    public let acknowledgeSensitiveAudio: Bool
    public let acknowledgePersonalUseOnly: Bool
    public let acknowledgeDeletionAvailable: Bool

    public init(
        retainRecordings: Bool,
        acknowledgeSensitiveAudio: Bool,
        acknowledgePersonalUseOnly: Bool,
        acknowledgeDeletionAvailable: Bool
    ) {
        self.retainRecordings = retainRecordings
        self.acknowledgeSensitiveAudio = acknowledgeSensitiveAudio
        self.acknowledgePersonalUseOnly = acknowledgePersonalUseOnly
        self.acknowledgeDeletionAvailable = acknowledgeDeletionAvailable
    }
}

public struct VoiceArchiveDeleteResponse: Codable, Sendable {
    public let status: String
    public let deleted: [String: Int]
}

struct VoiceArchiveDeleteRequest: Codable, Sendable {
    let confirm: String
}

public struct SafetyReportRequest: Codable, Sendable {
    public let category: String
    public let summary: String
    public let targetType: String?
    public let targetId: String?
    public let source: String
    public let metadata: [String: JSONValue]

    public init(
        category: String,
        summary: String,
        targetType: String? = "general",
        targetId: String? = nil,
        source: String = "ios",
        metadata: [String: JSONValue] = [:]
    ) {
        self.category = category
        self.summary = summary
        self.targetType = targetType
        self.targetId = targetId
        self.source = source
        self.metadata = metadata
    }
}

public struct SafetyReportResponse: Codable, Sendable {
    public let id: String
    public let status: String
    public let category: String
    public let createdAtUtc: String?
    public let supportChannel: String
}

public struct DeviceResponse: Codable, Sendable {
    public let id: String
    public let installationId: String
    public let platform: String
    public let deviceName: String?
    public let appVersion: String?
    public let buildNumber: String?
    public let osVersion: String?
    public let locale: String?
    public let timezone: String?
    public let pushProvider: String?
    public let pushTokenPresent: Bool
    public let notificationsEnabled: Bool
    public let createdAtUtc: String?
    public let lastSeenAtUtc: String?
    public let revokedAtUtc: String?
}

public struct DevicesPageResponse: Codable, Sendable {
    public let items: [DeviceResponse]
    public let total: Int
}

public struct SessionResponse: Codable, Sendable {
    public let id: String
    public let current: Bool
    public let createdAtUtc: String?
    public let expiresAtUtc: String?
    public let revokedAtUtc: String?
    public let userAgent: String?
    public let ipAddress: String?
}

public struct SessionsPageResponse: Codable, Sendable {
    public let items: [SessionResponse]
    public let total: Int
}

public struct SessionRevocationResponse: Codable, Sendable {
    public let status: String
    public let count: Int
}

public struct AccountExportResponse: Codable, Sendable {
    public let exportedAtUtc: String
    public let user: [String: JSONValue]
    public let tables: [String: [JSONValue]]
}

public struct AccountDeletionResponse: Codable, Sendable {
    public let status: String
    public let deleted: [String: Int]
}

public struct DraftSyncResult: Codable, Equatable, Sendable {
    public let draftId: String
    public let status: CaptureDraft.Status
    public let entryId: String?
    public let jobId: String?
    public let error: String?
}

public struct DraftSyncSummary: Codable, Equatable, Sendable {
    public let results: [DraftSyncResult]
    public var attempted: Int { results.count }
    public var synced: Int { results.filter { $0.status == .synced }.count }
    public var failed: Int { results.filter { $0.status == .failed }.count }
}
