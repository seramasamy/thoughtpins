import SwiftUI
import ThoughtPinsApp

@main
struct ThoughtPinsNativeApp: App {
    /// Production unless the build setting supplies something usable.
    ///
    /// This was `URL(string: configured ?? fallback)!`, which reads as safe
    /// because the fallback is a literal — but the force-unwrap applies to the
    /// *configured* value too. `URL(string:)` returns nil for an empty string,
    /// so a release built with `THOUGHTPINS_API_BASE_URL` unset or mistyped
    /// crashed on launch, before any screen, on every device.
    private let apiBaseURL: URL = {
        let fallback = URL(string: "https://api.thoughtpins.com")!
        guard
            let configured = Bundle.main.object(forInfoDictionaryKey: "THOUGHTPINS_API_BASE_URL") as? String,
            let url = URL(string: configured.trimmingCharacters(in: .whitespacesAndNewlines)),
            url.scheme?.lowercased() == "https",
            url.host != nil
        else {
            return fallback
        }
        return url
    }()

    var body: some Scene {
        WindowGroup {
            ThoughtPinsRootView(
                baseURL: apiBaseURL,
                oauthTokenProvider: GoogleOAuthTokenProvider()
            )
            .onOpenURL { url in
                _ = GoogleOAuthTokenProvider.handle(url)
            }
        }
    }
}
