import Foundation
import Security

public protocol SessionStore: Sendable {
    func load() throws -> ApiSession?
    func save(_ session: ApiSession?) throws
}

public final class KeychainSessionStore: SessionStore, @unchecked Sendable {
    private let service: String
    private let account: String

    public init(service: String = "com.thoughtpins.session", account: String = "default") {
        self.service = service
        self.account = account
    }

    public func load() throws -> ApiSession? {
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
        return try JSONDecoder().decode(ApiSession.self, from: data)
    }

    public func save(_ session: ApiSession?) throws {
        if let session {
            let data = try JSONEncoder().encode(session)
            var attributes = baseQuery()
            attributes[kSecValueData as String] = data
            attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let status = SecItemAdd(attributes as CFDictionary, nil)
            if status == errSecDuplicateItem {
                let updateStatus = SecItemUpdate(baseQuery() as CFDictionary, [kSecValueData as String: data] as CFDictionary)
                guard updateStatus == errSecSuccess else {
                    throw SessionStoreError.keychain(updateStatus)
                }
            } else if status != errSecSuccess {
                throw SessionStoreError.keychain(status)
            }
        } else {
            let status = SecItemDelete(baseQuery() as CFDictionary)
            if status != errSecSuccess && status != errSecItemNotFound {
                throw SessionStoreError.keychain(status)
            }
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
