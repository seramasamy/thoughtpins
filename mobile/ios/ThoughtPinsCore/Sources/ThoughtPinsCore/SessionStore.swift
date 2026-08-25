import Foundation
import Security

public protocol SessionStore: Sendable {
    func load() throws -> ApiSession?
    func save(_ session: ApiSession?) throws
}

/// Where the session bytes actually live.
///
/// Split out so the decode-and-heal behaviour in `KeychainSessionStore` can be
/// tested. The Keychain is unavailable to an unsigned test bundle -- it answers
/// every call with errSecMissingEntitlement -- so without a seam the only path
/// that could be covered was the one that never runs.
protocol SessionBlobStore: Sendable {
    func read() throws -> Data?
    func write(_ data: Data?) throws
}

public final class KeychainSessionStore: SessionStore, @unchecked Sendable {
    private let blobs: any SessionBlobStore

    public init(service: String = "com.thoughtpins.session", account: String = "default") {
        self.blobs = KeychainBlobStore(service: service, account: account)
    }

    init(blobs: any SessionBlobStore) {
        self.blobs = blobs
    }

    public func load() throws -> ApiSession? {
        // A Keychain failure still throws: that is the device saying no, not the
        // data being unreadable, and silently signing someone out for it would
        // hide a real fault.
        guard let data = try blobs.read() else {
            return nil
        }
        do {
            return try JSONDecoder().decode(ApiSession.self, from: data)
        } catch {
            // A blob we cannot read is not a session, and rethrowing here wedged
            // the app permanently: every launch called load(), every launch threw
            // the same decode error, and nothing ever cleared the item. A
            // truncated write or a session written by an older schema left
            // deleting the app as the only way back in.
            //
            // So clear it and report "signed out", which is the truth. The clear
            // is best effort on purpose: if the Keychain also refuses to remove
            // it, returning nil still leaves the person at sign-in rather than
            // stuck behind an error they cannot clear.
            try? blobs.write(nil)
            return nil
        }
    }

    public func save(_ session: ApiSession?) throws {
        guard let session else {
            try blobs.write(nil)
            return
        }
        try blobs.write(try JSONEncoder().encode(session))
    }
}

struct KeychainBlobStore: SessionBlobStore {
    let service: String
    let account: String

    func read() throws -> Data? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess, let data = item as? Data else {
            throw SessionStoreError.keychain(status)
        }
        return data
    }

    func write(_ data: Data?) throws {
        guard let data else {
            let status = SecItemDelete(baseQuery() as CFDictionary)
            if status != errSecSuccess && status != errSecItemNotFound {
                throw SessionStoreError.keychain(status)
            }
            return
        }
        var attributes = baseQuery()
        attributes[kSecValueData as String] = data
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(attributes as CFDictionary, nil)
        if status == errSecDuplicateItem {
            let updateStatus = SecItemUpdate(
                baseQuery() as CFDictionary,
                [kSecValueData as String: data] as CFDictionary
            )
            guard updateStatus == errSecSuccess else {
                throw SessionStoreError.keychain(updateStatus)
            }
        } else if status != errSecSuccess {
            throw SessionStoreError.keychain(status)
        }
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }
}

public enum SessionStoreError: Error, Equatable {
    case keychain(OSStatus)
}
