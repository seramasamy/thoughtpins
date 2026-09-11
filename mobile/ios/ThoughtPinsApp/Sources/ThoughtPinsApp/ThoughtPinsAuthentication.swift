import Foundation
import AuthenticationServices
import Security
import ThoughtPinsCore

extension ThoughtPinsAppModel {
    public func register(email: String?, phone: String?, password: String, consentToAIProcessing: Bool) async {
        guard !authBusy else { return }
        let email = email?.trimmingCharacters(in: .whitespacesAndNewlines)
        let phone = phone?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard consentToAIProcessing else {
            showProblem("Review and accept the privacy, terms, and AI processing disclosure to create an account.")
            return
        }
        // Checked before the account exists. Registering first and discovering
        // afterwards that there is nothing to sign in with leaves an orphan.
        guard let identifier = [email, phone].compactMap({ $0 }).first(where: { !$0.isEmpty }) else {
            showProblem("Add an email address or phone number.")
            return
        }
        authBusy = true
        defer { authBusy = false }
        do {
            _ = try await api.register(email: email, phone: phone, password: password)
            _ = try await api.login(identifier: identifier, password: password)
            refreshStoredSessionFlag()
            me = try await api.me()
        } catch {
            // "Check credentials" was wrong for most of what lands here -- a
            // dropped connection, a 500, a Keychain that refused the write.
            showProblem(ThoughtPinsAuthFailure(error).registrationMessage)
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
            showSuccess("Account created.")
        } catch {
            showProblem("Account created, but your consent was not recorded. You will be asked again.")
        }
        await refreshPreferences()
        await refreshVoiceArchive()
        await refreshReadModels()
    }

    public func oauthLogin(provider: ThoughtPinsOAuthProvider) async {
        guard !authBusy else { return }
        authBusy = true
        defer { authBusy = false }
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
            refreshStoredSessionFlag()
            me = try await api.me()
            await refreshPreferences()
            await refreshInviteStatus()
            showSuccess("Signed in with \(provider.label).")
            await refreshReadModels()
        } catch {
            showProblem(
                thoughtPinsPlainMessage(
                    for: error,
                    fallback: "\(provider.label) was not completed. Try again."
                )
            )
        }
    }

    public func completeAppleSignIn(_ result: Result<ASAuthorization, Error>) async {
        guard !authBusy else { return }
        authBusy = true
        defer { authBusy = false }
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
                showProblem("Apple did not return a usable sign-in credential.")
                return
            }
            guard
                let expectedNonce,
                let expectedState,
                credential.state == expectedState
            else {
                showProblem("Apple sign-in could not be verified. Please try again.")
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
            refreshStoredSessionFlag()
            me = try await api.me()
            await refreshPreferences()
            await refreshInviteStatus()
            showSuccess("Signed in with Apple.")
            await refreshReadModels()
        } catch {
            showProblem("Sign in with Apple was not completed.")
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
        guard !authBusy else { return }
        let identifier = identifier.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !identifier.isEmpty, !password.isEmpty else {
            showProblem("Enter your account details to sign in.")
            return
        }
        authBusy = true
        defer { authBusy = false }
        do {
            _ = try await api.login(identifier: identifier, password: password)
            refreshStoredSessionFlag()
            me = try await api.me()
            await refreshPreferences()
            await refreshInviteStatus()
            showSuccess("Signed in.")
            await refreshReadModels()
        } catch {
            showProblem(ThoughtPinsAuthFailure(error).signInMessage)
        }
    }

}
