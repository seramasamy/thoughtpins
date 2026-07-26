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
    public init() {}

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
    public init() {}

    public func payload(for destination: ThoughtPinsUploadDestination) async throws -> ThoughtPinsUploadPayload {
        throw ThoughtPinsNativeUploadError.filePickerNotConfigured(destination.rawValue)
    }
}

public enum ThoughtPinsNativeUploadError: Error, LocalizedError {
    case filePickerNotConfigured(String)
    case filePickerAlreadyActive
    case noFileSelected
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
            isImporterPresented = true
        }
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
        continuation.resume(throwing: ThoughtPinsNativeUploadError.noFileSelected)
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
