import GoogleSignIn
import ThoughtPinsApp
import UIKit

@MainActor
final class GoogleOAuthTokenProvider: ThoughtPinsOAuthTokenProvider, @unchecked Sendable {
    func supports(_ provider: ThoughtPinsOAuthProvider) -> Bool {
        guard provider == .google else { return false }
        let clientID = Bundle.main.object(forInfoDictionaryKey: "GIDClientID") as? String
        let serverClientID = Bundle.main.object(forInfoDictionaryKey: "GIDServerClientID") as? String
        return [clientID, serverClientID].allSatisfy { value in
            guard let value else { return false }
            return !value.isEmpty && !value.contains("$(")
        }
    }

    func credential(for provider: ThoughtPinsOAuthProvider) async throws -> ThoughtPinsOAuthCredential {
        guard supports(provider) else {
            throw ThoughtPinsNativeOAuthError.providerNotConfigured(provider.rawValue)
        }
        guard let presenter = Self.presentingViewController() else {
            throw GoogleOAuthProviderError.presentationUnavailable
        }
        let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: presenter)
        guard let idToken = result.user.idToken?.tokenString, !idToken.isEmpty else {
            throw GoogleOAuthProviderError.identityTokenMissing
        }
        return ThoughtPinsOAuthCredential(
            idToken: idToken,
            displayName: result.user.profile?.name
        )
    }

    static func handle(_ url: URL) -> Bool {
        GIDSignIn.sharedInstance.handle(url)
    }

    private static func presentingViewController() -> UIViewController? {
        let root = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows)
            .first(where: \.isKeyWindow)?
            .rootViewController
        return topViewController(from: root)
    }

    private static func topViewController(from controller: UIViewController?) -> UIViewController? {
        if let navigation = controller as? UINavigationController {
            return topViewController(from: navigation.visibleViewController)
        }
        if let tabs = controller as? UITabBarController {
            return topViewController(from: tabs.selectedViewController)
        }
        if let presented = controller?.presentedViewController {
            return topViewController(from: presented)
        }
        return controller
    }
}

private enum GoogleOAuthProviderError: LocalizedError {
    case presentationUnavailable
    case identityTokenMissing

    var errorDescription: String? {
        switch self {
        case .presentationUnavailable:
            return "Google sign-in cannot open from the current screen."
        case .identityTokenMissing:
            return "Google did not return a usable sign-in credential."
        }
    }
}
