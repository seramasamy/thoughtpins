import Foundation
import AuthenticationServices
import AVFoundation
import SwiftUI
import ThoughtPinsCore
import UIKit
import UniformTypeIdentifiers

public enum ThoughtPinsOAuthProvider: String, CaseIterable, Sendable {
    case apple
    case google

    public var label: String {
        switch self {
        case .apple: return "Sign in with Apple"
        case .google: return "Sign in with Google"
        }
    }
}

public struct ThoughtPinsOAuthCredential: Sendable {
    public let idToken: String
    public let displayName: String?
    public let authorizationCode: String?
    public let redirectUri: String?
    public let nonce: String?

    public init(
        idToken: String,
        displayName: String? = nil,
        authorizationCode: String? = nil,
        redirectUri: String? = nil,
        nonce: String? = nil
    ) {
        self.idToken = idToken
        self.displayName = displayName
        self.authorizationCode = authorizationCode
        self.redirectUri = redirectUri
        self.nonce = nonce
    }
}

@MainActor
public protocol ThoughtPinsOAuthTokenProvider: Sendable {
    func supports(_ provider: ThoughtPinsOAuthProvider) -> Bool
    func credential(for provider: ThoughtPinsOAuthProvider) async throws -> ThoughtPinsOAuthCredential
}

public struct UnconfiguredThoughtPinsOAuthTokenProvider: ThoughtPinsOAuthTokenProvider {
    // `nonisolated` because this is used as a default argument value, and on
    // Swift 5.9 a default argument expression is type-checked as nonisolated
    // regardless of the enclosing function's isolation (SE-0411, which allows
    // isolated default values, is not available until Swift 6). Conforming to
    // the @MainActor protocol above would otherwise make this init main-actor
    // isolated and unusable as a default. The type is stateless, so there is
    // nothing for the isolation to protect.
    public nonisolated init() {}

    public func supports(_ provider: ThoughtPinsOAuthProvider) -> Bool { false }

    public func credential(for provider: ThoughtPinsOAuthProvider) async throws -> ThoughtPinsOAuthCredential {
        throw ThoughtPinsNativeOAuthError.providerNotConfigured(provider.rawValue)
    }
}

public enum ThoughtPinsNativeOAuthError: Error, LocalizedError {
    case providerNotConfigured(String)

    public var errorDescription: String? {
        switch self {
        case .providerNotConfigured(let provider):
            return "The \(provider) sign-in SDK is not configured in this build."
        }
    }
}

public enum ThoughtPinsUploadDestination: String, CaseIterable, Identifiable, Sendable {
    case auto
    case library
    case journal
    case obsidianVault = "obsidian_vault"

    public var id: String { rawValue }

    public var label: String {
        switch self {
        case .auto: return "Auto"
        case .library: return "Library"
        case .journal: return "Journal"
        case .obsidianVault: return "Obsidian Vault"
        }
    }
}

public struct ThoughtPinsUploadPayload: Sendable {
    public let filename: String
    public let contentBase64: String
    public let mediaType: String?
    public let caption: String?
    public let title: String?
    public let sourceType: String?

    public init(
        filename: String,
        contentBase64: String,
        mediaType: String? = nil,
        caption: String? = nil,
        title: String? = nil,
        sourceType: String? = nil
    ) {
        self.filename = filename
        self.contentBase64 = contentBase64
        self.mediaType = mediaType
        self.caption = caption
        self.title = title
        self.sourceType = sourceType
    }
}

@MainActor
public protocol ThoughtPinsUploadProvider: Sendable {
    func payload(for destination: ThoughtPinsUploadDestination) async throws -> ThoughtPinsUploadPayload
}

public struct UnconfiguredThoughtPinsUploadProvider: ThoughtPinsUploadProvider {
    // nonisolated for the same reason as
    // UnconfiguredThoughtPinsOAuthTokenProvider.init above.
    public nonisolated init() {}

    public func payload(for destination: ThoughtPinsUploadDestination) async throws -> ThoughtPinsUploadPayload {
        throw ThoughtPinsNativeUploadError.filePickerNotConfigured(destination.rawValue)
    }
}

public enum ThoughtPinsNativeUploadError: Error, LocalizedError {
    case filePickerNotConfigured(String)
    case filePickerAlreadyActive
    case noFileSelected
    /// The person cancelled the picker on purpose. Distinct from
    /// `noFileSelected` so callers can stay silent instead of showing a
    /// problem banner for a deliberate choice.
    case cancelled
    case fileAccessDenied(String)
    case fileTooLarge(String)

    public var errorDescription: String? {
        switch self {
        case .filePickerNotConfigured(let destination):
            return "The native file picker or share extension is not configured for \(destination) uploads in this build."
        case .filePickerAlreadyActive:
            return "A file import is already in progress."
        case .noFileSelected:
            return "No file was selected."
        case .cancelled:
            return "The file picker was closed."
        case .fileAccessDenied(let filename):
            return "Thought Pins could not read \(filename)."
        case .fileTooLarge(let filename):
            return "\(filename) exceeds the 25 MB upload limit."
        }
    }
}

@MainActor
public final class ThoughtPinsDocumentPickerUploadProvider: ObservableObject, ThoughtPinsUploadProvider, @unchecked Sendable {
    @Published public var isImporterPresented = false
    /// Offered alongside Files, because the document picker cannot reach the
    /// photo library at all. `.image` in `allowedContentTypes` only ever meant
    /// "an image *file*", so a photo taken on the phone — the most obvious
    /// thing to attach to a journal entry — was unreachable.
    @Published public var isPhotoPickerPresented = false
    /// Which of the two to open. Presented first because only the person knows
    /// whether the thing they want is a photo or a file.
    @Published public var isSourceChoicePresented = false
    private var pendingContinuation: CheckedContinuation<ThoughtPinsUploadPayload, Error>?
    private var pendingDestination: ThoughtPinsUploadDestination = .auto

    public init() {}

    public func payload(for destination: ThoughtPinsUploadDestination) async throws -> ThoughtPinsUploadPayload {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<ThoughtPinsUploadPayload, Error>) in
            guard pendingContinuation == nil else {
                continuation.resume(throwing: ThoughtPinsNativeUploadError.filePickerAlreadyActive)
                return
            }
            pendingDestination = destination
            pendingContinuation = continuation
            isSourceChoicePresented = true
        }
    }

    /// Open Files. Called from the source dialog.
    public func chooseFiles() {
        isSourceChoicePresented = false
        isImporterPresented = true
    }

    /// Open the photo library. Called from the source dialog.
    public func choosePhotos() {
        isSourceChoicePresented = false
        isPhotoPickerPresented = true
    }

    /// Dismissing the source dialog has to resume the continuation, for the
    /// same reason `onCancellation` does on the file importer: an abandoned
    /// continuation wedges every later attempt as "already in progress".
    public func cancelSourceChoice() {
        isSourceChoicePresented = false
        guard let continuation = pendingContinuation else { return }
        pendingContinuation = nil
        continuation.resume(throwing: ThoughtPinsNativeUploadError.cancelled)
    }

    /// True between a photo being chosen and its bytes arriving.
    ///
    /// PhotosPicker has no cancellation callback: dismissing it only flips the
    /// `isPresented` binding, and that same flip happens after a successful
    /// pick. Without this flag, treating dismissal as cancellation would cancel
    /// the good path too — and *not* treating it as cancellation strands the
    /// continuation, which wedges every later upload as "already in progress".
    /// That is the same defect `onCancellation` exists to prevent on the file
    /// importer.
    private var photoSelectionInFlight = false

    /// A photo was chosen; its bytes are loading. Called before the await.
    public func beginPhotoSelection() {
        photoSelectionInFlight = true
    }

    /// The picker closed. Cancels only if nothing was chosen.
    public func photoPickerDismissed() {
        isPhotoPickerPresented = false
        guard !photoSelectionInFlight else { return }
        guard let continuation = pendingContinuation else { return }
        pendingContinuation = nil
        continuation.resume(throwing: ThoughtPinsNativeUploadError.cancelled)
    }

    /// Finish a photo-library pick. `data` is nil when the bytes could not be
    /// loaded, which PhotosPicker reports no differently from success.
    public func completePhotoImport(data: Data?, filename: String, mediaType: String?) {
        photoSelectionInFlight = false
        guard let continuation = pendingContinuation else { return }
        pendingContinuation = nil
        isPhotoPickerPresented = false

        guard let data else {
            continuation.resume(throwing: ThoughtPinsNativeUploadError.cancelled)
            return
        }
        // Same ceiling the file path enforces, checked here too: a photo from a
        // modern phone camera is comfortably capable of exceeding it.
        guard data.count <= 25 * 1024 * 1024 else {
            continuation.resume(throwing: ThoughtPinsNativeUploadError.fileTooLarge(filename))
            return
        }
        continuation.resume(
            returning: ThoughtPinsUploadPayload(
                filename: filename,
                contentBase64: data.base64EncodedString(),
                mediaType: mediaType,
                caption: nil,
                title: filename,
                sourceType: pendingDestination == .journal ? "journal_upload" : "file_upload"
            )
        )
    }

    public func completeFileImport(_ result: Result<[URL], Error>) {
        guard let continuation = pendingContinuation else { return }
        pendingContinuation = nil
        isImporterPresented = false

        switch result {
        case .success(let urls):
            guard let url = urls.first else {
                continuation.resume(throwing: ThoughtPinsNativeUploadError.noFileSelected)
                return
            }
            do {
                continuation.resume(returning: try makePayload(from: url, destination: pendingDestination))
            } catch {
                continuation.resume(throwing: error)
            }
        case .failure(let error):
            continuation.resume(throwing: error)
        }
    }

    public func cancelFileImport() {
        guard let continuation = pendingContinuation else { return }
        pendingContinuation = nil
        isImporterPresented = false
        continuation.resume(throwing: ThoughtPinsNativeUploadError.cancelled)
    }

    private func makePayload(from url: URL, destination: ThoughtPinsUploadDestination) throws -> ThoughtPinsUploadPayload {
        let startedAccess = url.startAccessingSecurityScopedResource()
        defer {
            if startedAccess {
                url.stopAccessingSecurityScopedResource()
            }
        }

        let filename = filename(for: url)
        let fileSize = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize
        if let fileSize, fileSize > 25 * 1024 * 1024 {
            throw ThoughtPinsNativeUploadError.fileTooLarge(filename)
        }
        guard let data = try? Data(contentsOf: url) else {
            throw ThoughtPinsNativeUploadError.fileAccessDenied(filename)
        }
        if data.count > 25 * 1024 * 1024 {
            throw ThoughtPinsNativeUploadError.fileTooLarge(filename)
        }
        let contentType = (try? url.resourceValues(forKeys: [.contentTypeKey]).contentType)
        return ThoughtPinsUploadPayload(
            filename: filename,
            contentBase64: data.base64EncodedString(),
            mediaType: contentType?.preferredMIMEType,
            caption: nil,
            title: filename,
            sourceType: destination == .journal ? "journal_upload" : "file_upload"
        )
    }

    private func filename(for url: URL) -> String {
        let values = try? url.resourceValues(forKeys: [.localizedNameKey])
        if let name = values?.localizedName, !name.isEmpty {
            return name
        }
        return url.lastPathComponent.isEmpty ? "thoughtpins-upload" : url.lastPathComponent
    }
}
